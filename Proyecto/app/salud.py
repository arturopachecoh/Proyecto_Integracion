"""Salud de las piezas de pedidos: ultima ejecucion correcta y ultimo error.

Lo escriben los workers y lo lee GET /api/salud/pedidos. Sirve para notar
durante la evaluacion que un lector dejo de funcionar antes de perder OC.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app import custodia
from app.db import SessionLocal
from app.models import OrdenCompra, SaludComponente
from app.pedidos import bandeja


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def ok(nombre: str) -> None:
    with SessionLocal.begin() as s:
        s.execute(insert(SaludComponente).values(nombre=nombre, ultimo_ok=_ahora())
                  .on_conflict_do_update(index_elements=["nombre"],
                                         set_={"ultimo_ok": _ahora()}))


def fallo(nombre: str, error: str) -> None:
    valores = {"ultimo_error_en": _ahora(), "ultimo_error": error[:2000]}
    with SessionLocal.begin() as s:
        s.execute(insert(SaludComponente).values(nombre=nombre, **valores)
                  .on_conflict_do_update(index_elements=["nombre"], set_=valores))


def resumen() -> dict:
    with SessionLocal() as s:
        componentes = {
            c.nombre: {"ultimo_ok": c.ultimo_ok, "ultimo_error_en": c.ultimo_error_en,
                       "ultimo_error": c.ultimo_error}
            for c in s.scalars(select(SaludComponente))
        }
        pronto = list(s.scalars(
            select(OrdenCompra)
            .where(OrdenCompra.estado == "aceptada",
                   OrdenCompra.vencimiento < _ahora() + timedelta(minutes=30))
            .order_by(OrdenCompra.vencimiento)))
    return {
        "componentes": componentes,
        "ordenes": bandeja.contar_por_estado(),
        "proximas_a_vencer": [
            {"id": o.id, "sku": o.sku, "cantidad": o.cantidad, "vencimiento": o.vencimiento,
             "despachadas": custodia.despachadas_de_venta(o.venta_id) if o.venta_id else 0}
            for o in pronto
        ],
    }
