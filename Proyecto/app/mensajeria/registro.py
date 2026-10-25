"""Registro de mensajes del canal de mensajeria.

Unico modulo que escribe la tabla mensajes. La clave es el messageId: un
mensaje repetido no se procesa dos veces. Cada paso queda anotado (que texto
se interpreto, que respondio el modelo, que decidio el sistema y que se envio)
para poder revisar cada decision despues.
"""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.db import SessionLocal
from app.models import Mensaje


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def guardar(message_id: str, remitente: str | None, telefono: str | None, texto: str,
            recibido_en: datetime) -> bool:
    """Anota un mensaje recibido. Devuelve False si ya estaba (duplicado)."""
    with SessionLocal.begin() as s:
        r = s.execute(
            insert(Mensaje)
            .values(id=message_id, remitente=remitente, telefono=telefono, texto=texto,
                    recibido_en=recibido_en, estado="pendiente", intentos=0)
            .on_conflict_do_nothing(index_elements=["id"])
            .returning(Mensaje.id)
        )
        # Con este driver rowcount no es confiable (-1): se mira si devolvio la fila
        return r.first() is not None


def get(message_id: str) -> Mensaje | None:
    with SessionLocal() as s:
        return s.get(Mensaje, message_id)


def en_estado(estado: str, limite: int = 50) -> list[Mensaje]:
    """Mensajes en un estado, el mas antiguo primero."""
    with SessionLocal() as s:
        return list(s.scalars(select(Mensaje).where(Mensaje.estado == estado)
                              .order_by(Mensaje.recibido_en).limit(limite)))


def registrar_fallo(message_id: str, error: str, evento: dict | None = None) -> None:
    with SessionLocal.begin() as s:
        m = s.get(Mensaje, message_id)
        if m is None:
            return
        m.intentos += 1
        m.ultimo_error = error[:2000]
        if evento:
            m.decision = _con_evento(m.decision, evento)


def _con_evento(decision: dict | None, evento: dict) -> dict:
    """Copia de decision con un evento mas (el JSON se reemplaza entero para que
    SQLAlchemy note el cambio)."""
    nueva = dict(decision or {})
    nueva["eventos"] = list(nueva.get("eventos") or []) + [
        {"en": _ahora().isoformat(), **evento}]
    return nueva


def preparar_respuesta(message_id: str, interpretacion: dict | None, decision: dict,
                       respuesta: dict) -> bool:
    """Anota la decision y el cuerpo a enviar ANTES de llamar a la plataforma.
    Solo si el mensaje sigue pendiente. Devuelve True si lo anoto."""
    with SessionLocal.begin() as s:
        m = s.get(Mensaje, message_id, with_for_update=True)
        if m is None or m.estado != "pendiente":
            return False
        m.interpretacion = interpretacion
        m.decision = _con_evento({**(m.decision or {}), **decision},
                                 {"paso": "decidido", "status": respuesta.get("status")})
        m.respuesta = respuesta
        m.estado = "respondiendo"
        return True


def reemplazar_respuesta(message_id: str, respuesta: dict, evento: dict) -> None:
    """Cambia el cuerpo a enviar (la plataforma rechazo el anterior con 422)."""
    with SessionLocal.begin() as s:
        m = s.get(Mensaje, message_id)
        if m is not None and m.estado == "respondiendo":
            m.respuesta = respuesta
            m.decision = _con_evento(m.decision, evento)


def anotar_oc(message_id: str, oc_id: str, evento: dict) -> None:
    """Guarda el orderId apenas lo devuelve la plataforma, antes de seguir."""
    with SessionLocal.begin() as s:
        m = s.get(Mensaje, message_id)
        if m is not None:
            m.oc_id = oc_id
            m.decision = _con_evento(m.decision, evento)


def cerrar(message_id: str, estado: str, evento: dict, error: str | None = None) -> None:
    """Estado final: pedido, descartado o sin_respuesta."""
    with SessionLocal.begin() as s:
        m = s.get(Mensaje, message_id)
        if m is None:
            return
        m.estado = estado
        m.decision = _con_evento(m.decision, evento)
        if error:
            m.ultimo_error = error[:2000]
