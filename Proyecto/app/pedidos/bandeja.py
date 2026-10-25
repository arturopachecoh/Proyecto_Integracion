"""Bandeja de OC recibidas.

Unico modulo que escribe ordenes_compra y archivos_sftp. La clave primaria
de ordenes_compra es el id de la OC: recibir dos veces la misma OC, por el
mismo canal o por otro, no hace nada la segunda vez.
"""
import re
from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert

from app.db import SessionLocal
from app.models import ArchivoSftp, OrdenCompra

# Patron de los ids de OC y de producto (el de POST /farma-central/dispatch)
ID_OC = re.compile(r"^[0-9a-fA-F]{24}$")


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _fecha(iso: str | None) -> datetime | None:
    """Fecha ISO de la API. Si viene sin zona horaria se asume UTC."""
    if not iso:
        return None
    f = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return f if f.tzinfo is not None else f.replace(tzinfo=timezone.utc)


def _insertar(s, oc_id: str, canal: str, origen_ref: str | None) -> bool:
    r = s.execute(
        insert(OrdenCompra)
        .values(id=oc_id, canal=canal, origen_ref=origen_ref, estado="nueva",
                despachado_remoto=0, intentos=0)
        .on_conflict_do_nothing(index_elements=["id"])
        .returning(OrdenCompra.id)
    )
    # Con un INSERT ORM rowcount no es confiable (-1): se mira si devolvio la fila
    return r.first() is not None


def recibir(oc_id: str, canal: str, origen_ref: str | None) -> bool:
    """Anota una OC recibida. Devuelve False si ya estaba."""
    with SessionLocal.begin() as s:
        return _insertar(s, oc_id, canal, origen_ref)


def recibir_archivo(nombre: str, oc_id: str | None, error: str | None = None) -> bool:
    """Anota un archivo de la casilla y su OC en una sola transaccion.
    Un archivo invalido (oc_id None) queda anotado con su error para no
    leerlo de nuevo en cada revision. Devuelve True si la OC es nueva."""
    with SessionLocal.begin() as s:
        s.execute(insert(ArchivoSftp).values(nombre=nombre, oc_id=oc_id, error=error)
                  .on_conflict_do_nothing(index_elements=["nombre"]))
        return _insertar(s, oc_id, "sftp", nombre) if oc_id else False


def archivos_no_leidos(nombres: list[str]) -> list[str]:
    if not nombres:
        return []
    with SessionLocal() as s:
        leidos = set(s.scalars(select(ArchivoSftp.nombre).where(ArchivoSftp.nombre.in_(nombres))))
    return [n for n in nombres if n not in leidos]


def nuevas(limite: int = 20) -> list[str]:
    """OC por decidir. Primero las que menos han fallado: unas pocas OC que
    fallan siempre no deben tapar a las que llegan despues."""
    with SessionLocal() as s:
        return list(s.scalars(select(OrdenCompra.id).where(OrdenCompra.estado == "nueva")
                              .order_by(OrdenCompra.intentos, OrdenCompra.recibida_en)
                              .limit(limite)))


def get(oc_id: str) -> OrdenCompra | None:
    with SessionLocal() as s:
        return s.get(OrdenCompra, oc_id)


def en_estado(*estados: str) -> list[OrdenCompra]:
    with SessionLocal() as s:
        return list(s.scalars(select(OrdenCompra).where(OrdenCompra.estado.in_(estados))
                              .order_by(OrdenCompra.vencimiento.asc().nulls_last())))


def aceptadas_por_vencimiento() -> list[OrdenCompra]:
    """OC aceptadas que aun no vencen, la que vence primero adelante."""
    with SessionLocal() as s:
        return list(s.scalars(select(OrdenCompra)
                              .where(OrdenCompra.estado == "aceptada",
                                     OrdenCompra.vencimiento > _ahora())
                              .order_by(OrdenCompra.vencimiento)))


def cumplidas_sin_confirmar() -> list[OrdenCompra]:
    """Cumplidas segun custodia que el sistema de ordenes aun no muestra cumplidas."""
    with SessionLocal() as s:
        return list(s.scalars(select(OrdenCompra).where(
            OrdenCompra.estado == "cumplida",
            OrdenCompra.estado_remoto.is_distinct_from("cumplida"))))


def guardar_detalle(oc_id: str, oc: dict) -> None:
    """Copia lo que dice la OC oficial (la fuente de verdad del pedido)."""
    with SessionLocal.begin() as s:
        o = s.get(OrdenCompra, oc_id)
        if o is None:
            return
        o.sku = oc.get("sku")
        o.cantidad = oc.get("cantidad")
        o.vencimiento = _fecha(oc.get("vencimiento"))
        o.cliente = (oc.get("nombreCliente") or str(oc.get("cliente") or "")) or None
        o.estado_remoto = oc.get("estado")
        o.despachado_remoto = int(oc.get("despachado") or 0)


def reclamar(oc_id: str, desde: str, hacia: str, decision: dict | None = None) -> bool:
    """Cambia el estado solo si sigue en `desde`. Si dos procesos lo intentan
    a la vez, uno solo gana. Devuelve True si gano este."""
    valores = {"estado": hacia, "decidida_en": _ahora()}
    if decision is not None:
        valores["decision"] = decision
    with SessionLocal.begin() as s:
        r = s.execute(update(OrdenCompra)
                      .where(OrdenCompra.id == oc_id, OrdenCompra.estado == desde)
                      .values(**valores))
        return r.rowcount == 1


def marcar(oc_id: str, estado: str, error: str | None = None) -> None:
    with SessionLocal.begin() as s:
        o = s.get(OrdenCompra, oc_id)
        if o is None:
            return
        o.estado = estado
        if error:
            o.ultimo_error = error[:2000]


def registrar_error(oc_id: str, error: str) -> None:
    with SessionLocal.begin() as s:
        o = s.get(OrdenCompra, oc_id)
        if o is not None:
            o.intentos += 1
            o.ultimo_error = error[:2000]


def enlazar_venta(oc_id: str, venta_id: int) -> None:
    with SessionLocal.begin() as s:
        s.get(OrdenCompra, oc_id).venta_id = venta_id


def contar_por_estado() -> dict[str, int]:
    with SessionLocal() as s:
        return dict(s.execute(select(OrdenCompra.estado, func.count())
                              .group_by(OrdenCompra.estado)).all())
