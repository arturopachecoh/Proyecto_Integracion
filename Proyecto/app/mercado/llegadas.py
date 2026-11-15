"""Cuando una unidad comprada en el mercado aparece en un espacio.

La llama custodia.registrar_llegadas, dentro de su transaccion. No abre otra
sesion y no escribe unidades: solo dice que origen ponerle al lote y avanza
el contador de la oferta de compra para no atribuirle llegadas de mas.
"""
from __future__ import annotations

from sqlalchemy import select

from app.mercado.modelos import OfertaMercado

_CLAVES_GRUPO = ("sellerGroup", "group", "fromGroup", "ownerGroup", "providerGroup", "grupo")
_CLAVES_BATCH = ("originalBatch", "sourceBatch", "lotId", "lote")


def atributos_compra(s, sku: str, codigo: str, unidades: list[dict]) -> dict | None:
    """{origen_grupo, lote_proveedor} si esta llegada es una compra de mercado.

    None si parece una recepcion normal de Farma (nadie la compro en el mercado).
    """
    grupo_json = _grupo(unidades)
    oferta = _oferta_por_cubrir(s, sku)
    if grupo_json is None and oferta is None:
        return None
    if oferta is not None:
        oferta.recibidas = (oferta.recibidas or 0) + len(unidades)
    grupo = grupo_json if grupo_json is not None else oferta.contraparte_grupo
    return {
        "origen_grupo": None if grupo is None else int(grupo),
        "lote_proveedor": _batch(unidades, codigo),
    }


def _oferta_por_cubrir(s, sku: str) -> OfertaMercado | None:
    return s.scalar(
        select(OfertaMercado)
        .where(
            OfertaMercado.sku == sku,
            OfertaMercado.rol == "comprador",
            OfertaMercado.estado.in_(("cerrada", "aceptando")),
            OfertaMercado.recibidas < OfertaMercado.cantidad,
        )
        .order_by(OfertaMercado.publicada_en)
        .limit(1)
    )


def _grupo(unidades: list[dict]) -> int | None:
    vistos = set()
    for producto in unidades:
        for clave in _CLAVES_GRUPO:
            if producto.get(clave) is None:
                continue
            try:
                vistos.add(int(producto[clave]))
            except (TypeError, ValueError):
                continue
            break
    if len(vistos) == 1:
        return vistos.pop()
    return None


def _batch(unidades: list[dict], codigo: str) -> str:
    for producto in unidades:
        for clave in _CLAVES_BATCH:
            if producto.get(clave):
                return str(producto[clave])
    return codigo
