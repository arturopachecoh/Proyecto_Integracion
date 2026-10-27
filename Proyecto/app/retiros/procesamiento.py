"""Procesamiento de los retiros de lote (lo corre el worker en cada tick).

Cada paso es idempotente y se puede re-correr tras una caida:
1. Investigar el lote (solo Postgres) y anotar las unidades afectadas en stock
   con el espacio donde estan, ANTES de moverlas.
2. Sacarlas de circulacion en custodia: dejan de ser vendibles y se sueltan
   sus reservas sin despachar.
3. Reportar a Farma Central (es lo que tiene plazo). Se reenvia solo si el
   contenido cambio; vale el ultimo reporte recibido dentro del plazo.
4. Notificar cada OC afectada: se anota antes y se marca enviada despues.
5. Mover las unidades al area de cuarentena, con tope de requests por tick
   (el limite de 250/min lo comparten todos los workers).

Primero se hacen los pasos 1 a 4 de todos los retiros y despues la cuarentena.
Pasado el plazo, el reporte y las notificaciones ya no cuentan: no se envian.
Se sigue re-investigando y aislando hasta REINTENTAR_HASTA despues del plazo,
por si aparece algo del lote (p. ej. un derivado de una fabricacion en camino).

Los reintentos tras un error esperan 10, 20, 40 y luego 60 s. Esa espera vive
en memoria del proceso: si el worker se reinicia, se reintenta de inmediato.
"""
import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import text

from app import custodia, farma_client, stock
from app import espacios as esp
from app.db import engine
from app.retiros import investigacion, registro

log = logging.getLogger("retiros")

MAX_REQUESTS_POR_TICK = 25  # movimientos y consultas de espacios a Farma Central
LOCK_RETIROS = 4_000_010  # candado de Postgres: un solo proceso trabaja los retiros
ESPERA_CANDADO_STOCK_S = 30
ESPERAS_S = (10, 20, 40, 60)
# Pausa maxima del despacho por un retiro que no se ha podido investigar
PAUSA_MAXIMA_DESPACHO = timedelta(minutes=10)

_reloj = time.monotonic
_fallos: dict[tuple, tuple[int, float]] = {}  # clave -> (fallos seguidos, proximo intento)
_no_movibles: dict[str, str] = {}  # unidad_id -> motivo (Farma rechazo moverla)
_investigados: set[str] = set()  # retiros ya sacados de circulacion en este proceso


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


@contextmanager
def _candado():
    with engine.connect() as conn:
        obtenido = conn.execute(text("SELECT pg_try_advisory_lock(:k)"),
                                {"k": LOCK_RETIROS}).scalar()
        try:
            yield obtenido
        finally:
            if obtenido:
                conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": LOCK_RETIROS})


def _error(e: Exception) -> str:
    if isinstance(e, httpx.HTTPStatusError):
        return f"{e.response.status_code}: {e.response.text[:300]}"
    return f"{type(e).__name__}: {e}"


# --- espera entre reintentos ---

def _toca(clave: tuple) -> bool:
    f = _fallos.get(clave)
    return f is None or _reloj() >= f[1]


def _fallo(clave: tuple) -> None:
    n = _fallos.get(clave, (0, 0.0))[0] + 1
    _fallos[clave] = (n, _reloj() + ESPERAS_S[min(n, len(ESPERAS_S)) - 1])


def _exito(clave: tuple) -> None:
    _fallos.pop(clave, None)


@dataclass
class _Presupuesto:
    restante: int
    cortado: bool = False  # Farma respondio 429: no mas requests este tick

    def gastar(self) -> bool:
        if self.cortado or self.restante <= 0:
            return False
        self.restante -= 1
        return True


# ---------------------------------------------------------------------------
# Respaldo por polling
# ---------------------------------------------------------------------------

def sincronizar_activos() -> int:
    """Registra los retiros activos de GET /farma-central/recalls que no hayan
    llegado por webhook. Devuelve cuantos eran nuevos."""
    activos = farma_client.recalls_activos() or []
    if isinstance(activos, dict):
        activos = activos.get("recalls") or activos.get("items") or []
    nuevos = 0
    for item in activos:
        try:
            aviso = registro.aviso_desde_farma(item)
        except ValueError as e:
            log.error("Retiro activo invalido %r: %s", item, e)
            continue
        if registro.recibir(aviso):
            nuevos += 1
            log.warning("Retiro %s del lote %s registrado por polling", aviso["id"], aviso["lote"])
    return nuevos


def hay_retiro_sin_investigar() -> bool:
    """True si hay un retiro recien llegado cuyas unidades aun no se sacan de
    circulacion en este proceso: mientras tanto el despacho de OC espera, para
    no entregar producto retirado. La pausa tiene tope (PAUSA_MAXIMA_DESPACHO)."""
    pendientes = registro.pendientes_recientes(_ahora() - PAUSA_MAXIMA_DESPACHO)
    return any(rid not in _investigados for rid in pendientes)


# ---------------------------------------------------------------------------
# Procesamiento
# ---------------------------------------------------------------------------

def procesar_pendientes() -> int:
    """Devuelve cuantos requests de cuarentena se hicieron en este tick."""
    with _candado() as obtenido:
        if not obtenido:
            log.info("Otro proceso esta trabajando los retiros")
            return 0
        retiros = registro.por_procesar()
        al_dia = {r.id: _investigar_reportar_notificar(r) for r in retiros}
        pres = _Presupuesto(MAX_REQUESTS_POR_TICK)
        for r in retiros:
            _aislar(r.id, pres)
            terminado = al_dia[r.id] and not _sin_aislar(r.id)
            registro.marcar_completo(r.id, terminado)
            if terminado and r.estado != "completo":
                log.warning("Retiro %s completo", r.id)
        return MAX_REQUESTS_POR_TICK - pres.restante


def _vencido(r) -> bool:
    return r.plazo is not None and _ahora() >= r.plazo


def _investigar_reportar_notificar(r) -> bool:
    """Pasos 1 a 4. Devuelve True si no queda reporte ni notificacion por enviar
    (pasado el plazo no queda nada: ya no cuentan)."""
    try:
        inv = investigacion.investigar(r.lote)
        nuevas = registro.anotar_unidades(r.id, inv["en_stock"])
        if nuevas:
            log.warning("Retiro %s (%s): %d unidades afectadas en stock", r.id, r.lote, nuevas)
        if _retirar_de_circulacion(r.id):
            _investigados.add(r.id)
        cuerpo = _reporte(r.id, inv)
    except Exception as e:
        log.exception("Retiro %s: fallo la investigacion", r.id)
        registro.registrar_error(r.id, f"investigacion: {_error(e)}")
        return False

    if _vencido(r):
        return True

    al_dia = True
    if r.reportado_en is None or r.reporte != cuerpo:
        clave = (r.id, "reporte")
        if not _toca(clave):
            al_dia = False
        else:
            try:
                farma_client.reportar_retiro(r.id, cuerpo)
                registro.guardar_reporte(r.id, cuerpo)
                _exito(clave)
                log.warning("Retiro %s reportado: %d en stock, %d derivados, %d entregas", r.id,
                            len(cuerpo["inStock"]), len(cuerpo["derivedBatches"]),
                            len(cuerpo["deliveries"]))
            except Exception as e:
                _fallo(clave)
                log.error("Retiro %s: no se pudo enviar el reporte: %s", r.id, _error(e))
                registro.registrar_error(r.id, f"reporte: {_error(e)}")
                al_dia = False

    registro.anotar_notificaciones(r.id, [_notificacion(r, e) for e in inv["entregas"]])
    for oc_id, cuerpo_notif in registro.notificaciones_pendientes(r.id):
        clave = (r.id, "notificacion", oc_id)
        if not _toca(clave):
            al_dia = False
            continue
        try:
            farma_client.notificar_retiro(r.id, cuerpo_notif)
            registro.marcar_notificada(r.id, oc_id)
            _exito(clave)
            log.warning("Retiro %s: OC %s notificada", r.id, oc_id)
        except Exception as e:
            _fallo(clave)
            log.error("Retiro %s: no se pudo notificar la OC %s: %s", r.id, oc_id, _error(e))
            registro.registrar_error(r.id, f"notificacion {oc_id}: {_error(e)}")
            al_dia = False
    return al_dia


def _retirar_de_circulacion(retiro_id: str) -> bool:
    """Devuelve True si no queda ninguna unidad anotada en circulacion."""
    ids = registro.ids_por_retirar(retiro_id)
    if not ids:
        return True
    try:
        # Mismo candado que usan el portal y las OC para reservar stock
        with stock.candado_stock(esperar_s=ESPERA_CANDADO_STOCK_S):
            soltadas = custodia.retirar_de_circulacion(ids)
    except RuntimeError:
        # El despacho sigue en pausa (hay_retiro_sin_investigar) hasta lograrlo
        log.error("Retiro %s: stock ocupado %d s, se sacan de circulacion en el proximo tick",
                  retiro_id, ESPERA_CANDADO_STOCK_S)
        registro.registrar_error(retiro_id, "candado de stock ocupado")
        return False
    for unidad_id, venta_id in soltadas:
        log.warning("Retiro %s: %s quitada de la venta %d (no habia salido)",
                    retiro_id, unidad_id, venta_id)
    return True


def _reporte(retiro_id: str, inv: dict) -> dict:
    """inStock sale de retiro_unidades (el espacio donde estaba cada unidad al
    detectarla), no del estado actual: una vez aislada sigue en el reporte.
    Se excluyen las que se confirmaron inexistentes o vencieron sin aislarse."""
    in_stock = [{"productId": u.unidad_id, "batch": u.lote_codigo,
                 "store": esp.store_id(u.espacio_original) if u.espacio_original else ""}
                for u in registro.unidades_reportables(retiro_id)]
    return {"inStock": sorted(in_stock, key=lambda i: i["productId"]),
            "derivedBatches": inv["derivados"],
            "deliveries": inv["entregas"]}


def _notificacion(r, entrega: dict) -> dict:
    motivo = f" Motivo: {r.motivo}." if r.motivo else ""
    return {**entrega,
            "message": (f"Retiro de lote {r.lote}: las unidades indicadas no deben usarse "
                        f"ni distribuirse.{motivo}")}


# ---------------------------------------------------------------------------
# Cuarentena
# ---------------------------------------------------------------------------

def _sin_aislar(retiro_id: str) -> list:
    return [p for p in registro.por_aislar(retiro_id) if p[0] not in _no_movibles]


def _aislar(retiro_id: str, pres: _Presupuesto) -> None:
    """Mueve a cuarentena las unidades anotadas que faltan, sin pasar el tope."""
    ahora = _ahora()
    for unidad_id, sku, espacio, estado, vence_en in _sin_aislar(retiro_id):
        if estado != "cuarentena":
            continue  # aun en circulacion: primero se saca (proximo tick)
        if espacio == "quarantine":
            custodia.poner_en_cuarentena(unidad_id)
            registro.marcar_aislada(unidad_id)
            continue
        if vence_en is not None and vence_en <= ahora:
            # Farma ya no la tiene: moverla fallaria y no cuenta como stock
            log.warning("Retiro %s: %s vencio antes de aislarse, queda vencida",
                        retiro_id, unidad_id)
            custodia.registrar_vencidas([unidad_id])
            continue
        clave = ("mover", unidad_id)
        if not _toca(clave):
            continue
        if not pres.gastar():
            return
        try:
            farma_client.move_product(unidad_id, esp.store_id("quarantine"))
        except httpx.HTTPStatusError as e:
            codigo = e.response.status_code
            if codigo == 429:
                pres.cortado = True
                registro.registrar_error(retiro_id, f"cuarentena {unidad_id}: 429")
                return
            if codigo >= 500:
                _fallo(clave)
                registro.registrar_error(retiro_id, f"cuarentena {unidad_id}: {_error(e)}")
                continue
            _rechazo_definitivo(retiro_id, unidad_id, sku, espacio, e, pres)
            continue
        except httpx.HTTPError as e:
            _fallo(clave)
            registro.registrar_error(retiro_id, f"cuarentena {unidad_id}: {_error(e)}")
            continue
        _exito(clave)
        custodia.poner_en_cuarentena(unidad_id)
        registro.marcar_aislada(unidad_id)
        log.info("Retiro %s: %s (%s) %s -> quarantine", retiro_id, unidad_id, sku, espacio)


def _rechazo_definitivo(retiro_id, unidad_id, sku, espacio, e, pres) -> None:
    """Farma rechazo el movimiento con un 4xx: no se reintenta igual."""
    clave = ("mover", unidad_id)
    en_cuarentena = _esta_en(unidad_id, sku, "quarantine", pres)
    if en_cuarentena:
        # Un move anterior llego pero no alcanzo a anotarse
        log.warning("Retiro %s: %s ya estaba en cuarentena", retiro_id, unidad_id)
        _exito(clave)
        custodia.poner_en_cuarentena(unidad_id)
        registro.marcar_aislada(unidad_id)
        return
    en_origen = _esta_en(unidad_id, sku, espacio, pres) if en_cuarentena is False else None
    if en_cuarentena is None or en_origen is None:
        _fallo(clave)  # no se pudo confirmar: se vuelve a intentar mas tarde
        registro.registrar_error(retiro_id, f"cuarentena {unidad_id}: {_error(e)}")
        return
    _exito(clave)
    if not en_origen:
        log.error("Retiro %s: %s ya no existe en Farma Central (%s), queda vencida y sale "
                  "del reporte", retiro_id, unidad_id, _error(e))
        custodia.registrar_vencidas([unidad_id])
        return
    _no_movibles[unidad_id] = _error(e)
    log.error("Retiro %s: Farma rechaza mover %s a cuarentena (%s); no se reintenta",
              retiro_id, unidad_id, _error(e))
    registro.registrar_error(retiro_id, f"cuarentena {unidad_id} no movible: {_error(e)}")


def _esta_en(unidad_id: str, sku: str, tipo: str | None, pres: _Presupuesto) -> bool | None:
    """True/False si la unidad esta o no en ese espacio; None si no se pudo saber."""
    if not tipo:
        return False
    if not pres.gastar():
        return None
    try:
        productos = farma_client.space_products(esp.store_id(tipo), sku, limit=200)
    except Exception:
        log.exception("No se pudo revisar el espacio %s", tipo)
        return None
    return any(p.get("_id") == unidad_id for p in productos or [])
