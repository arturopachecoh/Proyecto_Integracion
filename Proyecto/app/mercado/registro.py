"""Lectura y escritura de ofertas_mercado. Las unidades las mueve custodia."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select, text

from app.db import SessionLocal
from app.mercado.modelos import FaltanteMercado, OfertaMercado

ABIERTAS = ("publicando", "abierta", "aceptando", "cancelando")


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def existe(oferta_id: str) -> bool:
    with SessionLocal() as s:
        return s.get(OfertaMercado, oferta_id) is not None


def ids_remotos() -> set[str]:
    with SessionLocal() as s:
        return set(s.scalars(select(OfertaMercado.id)))


def por_refrescar() -> list[OfertaMercado]:
    with SessionLocal() as s:
        return list(s.scalars(
            select(OfertaMercado).where(OfertaMercado.estado.in_(ABIERTAS))
            .order_by(OfertaMercado.publicada_en)
        ))


def hay_abierta(sku: str, side: str) -> bool:
    with SessionLocal() as s:
        fila = s.scalar(
            select(OfertaMercado.id).where(
                OfertaMercado.sku == sku,
                OfertaMercado.side == side,
                OfertaMercado.estado.in_(("publicando", "abierta", "aceptando")),
            ).limit(1)
        )
        return fila is not None


def crear(oferta_id: str, side: str, sku: str, cantidad: int, precio: int, estado: str,
          rol: str, contraparte: int | None = None, order_id: str | None = None) -> None:
    with SessionLocal.begin() as s:
        if s.get(OfertaMercado, oferta_id) is not None:
            return
        s.add(OfertaMercado(
            id=oferta_id, side=side, sku=sku, cantidad=cantidad, precio_unitario=precio,
            estado=estado, rol=rol, contraparte_grupo=contraparte, order_id=order_id,
        ))


def marcar(oferta_id: str, **campos) -> None:
    with SessionLocal.begin() as s:
        oferta = s.get(OfertaMercado, oferta_id)
        if oferta is None:
            return
        for clave, valor in campos.items():
            setattr(oferta, clave, valor)
        oferta.actualizada_en = _ahora()


def renombrar(local_id: str, remoto_id: str) -> None:
    """Cambia la PK. oferta_unidades sigue el cambio por ON UPDATE CASCADE."""
    if local_id == remoto_id:
        return
    with SessionLocal.begin() as s:
        if s.get(OfertaMercado, remoto_id) is not None:
            return
        s.execute(
            text("UPDATE ofertas_mercado SET id = :nuevo WHERE id = :viejo"),
            {"nuevo": remoto_id, "viejo": local_id},
        )


def expiradas_seguidas(sku: str) -> int:
    """Cuantas ventas de este SKU expiraron al hilo, mirando las mas recientes."""
    with SessionLocal() as s:
        estados = list(s.scalars(
            select(OfertaMercado.estado)
            .where(OfertaMercado.sku == sku, OfertaMercado.side == "sell",
                   OfertaMercado.rol == "vendedor")
            .order_by(OfertaMercado.actualizada_en.desc())
            .limit(8)
        ))
    n = 0
    for estado in estados:
        if estado != "expirada":
            break
        n += 1
    return n


def contar_cierres() -> tuple[int, int]:
    """(ventas cerradas, compras cerradas) con order_id. Cada oferta cuenta una vez."""
    with SessionLocal() as s:
        filas = s.execute(
            select(OfertaMercado.rol).where(
                OfertaMercado.estado == "cerrada",
                OfertaMercado.order_id.is_not(None),
            )
        ).all()
    ventas = sum(1 for (rol,) in filas if rol == "vendedor")
    compras = sum(1 for (rol,) in filas if rol == "comprador")
    return ventas, compras


def pendiente_parecida(sku: str, side: str, cantidad: int, precio: int) -> str | None:
    with SessionLocal() as s:
        return s.scalar(
            select(OfertaMercado.id).where(
                OfertaMercado.estado == "publicando",
                OfertaMercado.sku == sku,
                OfertaMercado.side == side,
                OfertaMercado.cantidad == cantidad,
                OfertaMercado.precio_unitario == precio,
            ).limit(1)
        )


def faltante_desde(sku: str, ahora: datetime) -> datetime:
    with SessionLocal.begin() as s:
        fila = s.get(FaltanteMercado, sku)
        if fila is None:
            s.add(FaltanteMercado(sku=sku, desde=ahora))
            return ahora
        return fila.desde


def olvidar_faltante(sku: str) -> None:
    with SessionLocal.begin() as s:
        fila = s.get(FaltanteMercado, sku)
        if fila is not None:
            s.delete(fila)
