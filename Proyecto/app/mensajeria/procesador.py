"""Procesador de mensajes: interpreta, valida y responde cada mensaje una vez.

Estados (tabla mensajes):
  pendiente     -> recibido, falta decidir (o el modelo fallo y se reintenta)
  respondiendo  -> decision y cuerpo anotados, falta que la plataforma confirme
  pedido / descartado / sin_respuesta -> finales

La decision se anota ANTES de llamar a la plataforma. Si el proceso cae entre
la anotacion y la respuesta, el mensaje queda en respondiendo y se reenvia el
mismo cuerpo; un 409 indica que el primer envio si llego.

Plazos (desde receivedAt): la plataforma acepta la respuesta hasta los 30 min.
Si a los 25 min el modelo aun no dio algo usable, se descarta para no dejar
el mensaje sin respuesta (que cuenta como error).
"""
import logging
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from app import config, messaging_client, salud
from app.db import engine
from app.mensajeria import interprete, registro, validacion
from app.operaciones import catalogo
from app.pedidos import bandeja

log = logging.getLogger("mensajeria")

LOCK_MENSAJERIA = 4_000_011  # candado de Postgres (retiros usa 4_000_010)
# Mensajes que se interpretan por tick. Uno: el gateway admite ~1 prompt por
# minuto (1.000 tokens/min por grupo) y un segundo intento seguido solo recibe 429
POR_TICK = 1
# Separacion entre llamadas al modelo para no pasar el cupo por minuto del gateway
ENTRE_LLAMADAS = timedelta(seconds=60)
_ultima_llamada: datetime | None = None
VENTANA = timedelta(minutes=30)  # la plataforma acepta la respuesta hasta aqui
CORTE_INTERPRETACION = timedelta(minutes=25)
ESPERA_BASE_S = 10
ESPERA_MAX_S = 60
MOTIVO_SIN_INTERPRETAR = "No se pudo interpretar el mensaje a tiempo"
SALUD_MODELO = "mensajeria_modelo"  # se ve en /api/salud/pedidos


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _espera(intentos: int) -> timedelta:
    """Espera creciente tras un fallo: 10, 20, 40, 60, 60... segundos."""
    if intentos <= 0:
        return timedelta(0)
    return timedelta(seconds=min(ESPERA_BASE_S * 2 ** (intentos - 1), ESPERA_MAX_S))


def _toca(m, ahora: datetime) -> bool:
    return m.intentos == 0 or m.actualizado_en + _espera(m.intentos) <= ahora


@contextmanager
def _candado():
    """Un solo procesador a la vez (si hubiera dos, ambos llamarian al modelo
    y a la plataforma por el mismo mensaje). Se libera solo si el proceso muere."""
    with engine.connect() as conn:
        ok = conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": LOCK_MENSAJERIA}).scalar()
        try:
            yield bool(ok)
        finally:
            if ok:
                conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": LOCK_MENSAJERIA})


def procesar_pendientes(por_tick: int = POR_TICK) -> int:
    """Funcion de tick. Primero termina lo que ya se decidio, despues interpreta
    hasta por_tick mensajes nuevos. Devuelve cuantos mensajes trabajo."""
    with _candado() as ok:
        if not ok:
            log.info("Otro procesador de mensajes esta corriendo; se salta este tick")
            return 0
        hechos = 0
        ahora = _ahora()
        for m in registro.en_estado("respondiendo"):
            if _toca(m, ahora):
                _seguro(_enviar, m.id)
                hechos += 1
        interpretados = 0
        if _ultima_llamada is not None and _ahora() < _ultima_llamada + ENTRE_LLAMADAS:
            return hechos
        for m in registro.en_estado("pendiente", limite=50):
            if interpretados >= por_tick:
                break
            if _toca(m, _ahora()):
                _seguro(_decidir, m.id)
                interpretados += 1
        return hechos + interpretados


def _salud_modelo(error: str | None) -> None:
    """Deja visible si el modelo esta respondiendo: si falla, todos los mensajes
    terminan descartados a los 25 min y el resto del worker igual se ve sano."""
    try:
        if error is None:
            salud.ok(SALUD_MODELO)
        else:
            salud.fallo(SALUD_MODELO, error)
    except Exception:
        log.exception("No se pudo registrar la salud del modelo")


def _seguro(fn, message_id: str) -> None:
    """Un mensaje que falla no frena a los demas: queda anotado y se reintenta."""
    try:
        fn(message_id)
    except Exception as e:
        log.exception("Mensaje %s: error inesperado", message_id)
        registro.registrar_fallo(message_id, repr(e))


# ---------------------------------------------------------------------------
# Decidir
# ---------------------------------------------------------------------------

def _decidir(message_id: str) -> None:
    m = registro.get(message_id)
    if m is None or m.estado != "pendiente":
        return
    ahora = _ahora()
    if ahora >= m.recibido_en + CORTE_INTERPRETACION:
        _preparar_descarte_por_plazo(m)
        return _enviar(message_id)

    global _ultima_llamada
    try:
        cat = catalogo()
        _ultima_llamada = _ahora()
        salida, crudo = interprete.interpretar(m.texto, m.recibido_en, cat)
    except Exception as e:
        # Modelo caido, presupuesto agotado, JSON invalido o catalogo no disponible
        log.warning("Mensaje %s: no se pudo interpretar (intento %d): %r",
                    message_id, m.intentos + 1, e)
        registro.registrar_fallo(message_id, f"interpretacion: {e!r}",
                                 {"paso": "fallo_interpretacion", "error": repr(e)[:500]})
        _salud_modelo(f"mensaje {message_id}: {e!r}")
        if _ahora() >= m.recibido_en + CORTE_INTERPRETACION:
            _preparar_descarte_por_plazo(registro.get(message_id))
            _enviar(message_id)
        return

    _salud_modelo(None)
    salida = interprete.revisar_cantidad(m.texto, interprete.desempatar(m.texto, salida, cat))
    salida = interprete.revisar_plazo_pasado(m.texto, interprete.revisar_suelto(m.texto, salida))
    resultado = validacion.validar(salida, validacion.skus_kit(cat), m.recibido_en, _ahora())
    log.info("Mensaje %s: %s (%s)", message_id, resultado.cuerpo["status"],
             resultado.motivo or resultado.cuerpo.get("interpretation"))
    registro.preparar_respuesta(
        message_id,
        interpretacion={"modelo": config.LLM_MODEL, "crudo": crudo, "salida": salida},
        decision={"resultado": resultado.cuerpo["status"], "motivo": resultado.motivo,
                  "pasos": resultado.pasos, "decidido_en": _ahora().isoformat()},
        respuesta=resultado.cuerpo,
    )
    _enviar(message_id)


def _preparar_descarte_por_plazo(m) -> None:
    cuerpo = {"status": "discarded", "reason": MOTIVO_SIN_INTERPRETAR}
    log.error("Mensaje %s: se descarta sin interpretar (ultimo error: %s)", m.id, m.ultimo_error)
    registro.preparar_respuesta(
        m.id, interpretacion=m.interpretacion,
        decision={"resultado": "discarded", "motivo": MOTIVO_SIN_INTERPRETAR,
                  "pasos": [f"sin interpretacion usable tras {m.intentos} intentos",
                            f"descartar: {MOTIVO_SIN_INTERPRETAR}"],
                  "decidido_en": _ahora().isoformat()},
        respuesta=cuerpo,
    )


# ---------------------------------------------------------------------------
# Responder
# ---------------------------------------------------------------------------

def _enviar(message_id: str, rehecho: bool = False) -> None:
    m = registro.get(message_id)
    if m is None or m.estado != "respondiendo":
        return
    if m.oc_id:
        # La plataforma ya registro el pedido; falto anotarlo en la bandeja
        return _cerrar_pedido(m, m.oc_id, {})
    if _ahora() > m.recibido_en + VENTANA + timedelta(minutes=5):
        registro.cerrar(m.id, "sin_respuesta", {"paso": "abandonado"},
                        error="no se pudo responder dentro de la ventana de 30 minutos")
        log.error("Mensaje %s: quedo sin respuesta (ultimo error: %s)", m.id, m.ultimo_error)
        return

    enviado = m.respuesta or {}
    try:
        codigo, cuerpo = messaging_client.responder(m.id, enviado)
    except Exception as e:
        log.warning("Mensaje %s: la plataforma no respondio: %r", m.id, e)
        registro.registrar_fallo(m.id, f"responder: {e!r}")
        return
    cuerpo = cuerpo if isinstance(cuerpo, dict) else {}
    evento = {"paso": "respuesta_plataforma", "codigo": codigo, "cuerpo": cuerpo}
    if cuerpo.get("test") or m.id.startswith("test_"):
        evento["test"] = True
    es_pedido = enviado.get("status") == "order"

    if codigo == 200:
        if not es_pedido:
            registro.cerrar(m.id, "descartado", evento)
        elif cuerpo.get("orderId"):
            registro.anotar_oc(m.id, str(cuerpo["orderId"]), evento)
            _cerrar_pedido(m, str(cuerpo["orderId"]), {})
        else:
            # Los mensajes de prueba no crean OC
            error = None if evento.get("test") else "la plataforma registro el pedido sin orderId"
            if error:
                log.error("Mensaje %s: %s", m.id, error)
            registro.cerrar(m.id, "pedido", evento, error=error)
    elif codigo == 409:
        # Ya tenia respuesta: el envio anterior llego aunque no se alcanzo a anotar
        if not es_pedido:
            registro.cerrar(m.id, "descartado", evento)
        else:
            error = ("la plataforma ya tenia registrado el pedido (409) y no se conoce su "
                     "orderId: revisar la OC en el portal")
            log.error("Mensaje %s: %s", m.id, error)
            registro.cerrar(m.id, "pedido", evento, error=error)
    elif codigo == 410:
        registro.cerrar(m.id, "sin_respuesta", evento, error="410: paso la ventana de respuesta")
        log.error("Mensaje %s: la plataforma ya no acepta respuesta (410)", m.id)
    elif codigo == 404:
        registro.cerrar(m.id, "sin_respuesta", evento,
                        error="404: la plataforma no conoce el mensaje (otro grupo o ambiente)")
        log.error("Mensaje %s: la plataforma no lo conoce (404)", m.id)
    elif codigo == 422:
        _rechazo_422(m, enviado, cuerpo, evento, rehecho)
    else:
        registro.registrar_fallo(m.id, f"responder: HTTP {codigo} {str(cuerpo)[:300]}", evento)


def _rechazo_422(m, enviado: dict, cuerpo: dict, evento: dict, rehecho: bool) -> None:
    """La plataforma no acepto la interpretacion. Si era un pedido y aun hay
    plazo, se descarta con el motivo que dio la plataforma."""
    detalle = cuerpo.get("details") or cuerpo.get("message") or cuerpo
    if enviado.get("status") == "order" and not rehecho and _ahora() < m.recibido_en + VENTANA:
        motivo = f"La interpretacion no es valida para la plataforma: {str(detalle)[:300]}"
        registro.reemplazar_respuesta(m.id, {"status": "discarded", "reason": motivo},
                                      {**evento, "paso": "rechazo_422_se_descarta"})
        log.warning("Mensaje %s: 422 al registrar el pedido, se descarta", m.id)
        return _enviar(m.id, rehecho=True)
    registro.cerrar(m.id, "sin_respuesta", evento, error=f"422: {str(detalle)[:500]}")
    log.error("Mensaje %s: 422 sin alternativa: %s", m.id, detalle)


def _cerrar_pedido(m, oc_id: str, evento: dict) -> None:
    """La OC entra a la bandeja como cualquier otra: el procesador de OC la
    acepta o la rechaza segun stock y el despachador la despacha."""
    nueva = bandeja.recibir(oc_id, "mensajeria", m.id)
    registro.cerrar(m.id, "pedido", {**evento, "paso": "oc_en_bandeja", "oc_id": oc_id,
                                     "nueva": nueva})
    log.info("Mensaje %s: pedido registrado como OC %s", m.id, oc_id)
