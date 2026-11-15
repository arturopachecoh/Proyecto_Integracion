"""OC de canal mercado, ya cumplida. No llama a SOAP ni al sistema de ordenes.

La factura la emite otro proceso cuando ve estado=cumplida y el rol no es
comprador. decision.rol distingue al proveedor (vendedor) del comprador.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from app.db import SessionLocal
from app.models import OrdenCompra


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def registrar(order_id: str, sku: str, cantidad: int, precio: int,
              contraparte: int | None, rol: str, venta_id: int | None = None,
              offer_id: str | None = None) -> bool:
    """Inserta la OC si no existe. Devuelve True solo la primera vez."""
    with SessionLocal.begin() as s:
        if s.get(OrdenCompra, order_id) is not None:
            return False
        s.add(OrdenCompra(
            id=order_id,
            canal="mercado",
            origen_ref=offer_id,
            sku=sku,
            cantidad=cantidad,
            cliente=None if contraparte is None else str(contraparte),
            estado="cumplida",
            estado_remoto="cumplida",
            despachado_remoto=cantidad or 0,
            venta_id=venta_id,
            decision={"rol": rol, "contraparte": contraparte, "precio_unitario": precio},
            decidida_en=_ahora(),
        ))
        return True


def canal_de(oc_id: str) -> str | None:
    if not oc_id:
        return None
    with SessionLocal() as s:
        canal = s.scalar(select(OrdenCompra.canal).where(OrdenCompra.id == oc_id))
        return canal


def es_notificable(canal: str | None) -> bool:
    """Una venta de mercado se reporta como entrega y no se notifica.

    Si no hay OC local (None), se notifica: es el comportamiento de la E2.
    """
    return canal != "mercado"
