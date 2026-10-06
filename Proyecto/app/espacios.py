"""Identificacion de los espacios de la distribuidora.

Los IDs de los espacios son distintos en dev y en prod, asi que nunca se
escriben a mano: se obtienen de GET /spaces y se reconocen por sus campos.

Tipos: checkIn, checkOut, packaging, quarantine, buffer, cold, bodega
"""
from app import farma_client

REFRIGERADOS = {"cold", "buffer"}

_cache: dict[str, dict] | None = None


def tipo_espacio(espacio: dict) -> str:
    """Traduce un espacio de la API a su tipo.
    El buffer va primero porque tambien viene marcado como cold."""
    if espacio.get("buffer"):
        return "buffer"
    for campo in ("checkIn", "checkOut", "packaging", "quarantine"):
        if espacio.get(campo):
            return campo
    if espacio.get("cold"):
        return "cold"
    return "bodega"


def espacios(refrescar: bool = False) -> dict[str, dict]:
    """Devuelve {tipo: espacio}. Se consulta a la API una sola vez por proceso,
    porque los espacios y sus capacidades no cambian."""
    global _cache
    if _cache is None or refrescar:
        _cache = {tipo_espacio(e): e for e in farma_client.spaces()}
    return _cache


def store_id(tipo: str) -> str:
    """ID del espacio de ese tipo. Ej: store_id("cold")"""
    return espacios()[tipo]["_id"]


def capacidad(tipo: str) -> int:
    return espacios()[tipo]["totalSpace"]


def ocupacion(tipo: str) -> int:
    """Espacio ocupado. usedSpace incluye lo reservado para compras y
    fabricaciones en camino; por si acaso se compara con el inventario real."""
    usado = next(e["usedSpace"] for e in farma_client.spaces() if tipo_espacio(e) == tipo)
    inventario = sum(i["quantity"] for i in farma_client.space_inventory(store_id(tipo)))
    return max(usado, inventario)


def libres(tipo: str) -> int:
    return capacidad(tipo) - ocupacion(tipo)