"""Banda de precio del mercado: entre 0,5 y 1,5 veces el precio vigente.

El precio del portal (Entrega 1) no rige aca. Si no hay precio vigente no se
publica ni se acepta: Farma rechaza lo que cae fuera de la banda.
"""
from __future__ import annotations


def _redondear(valor: float) -> int:
    """Medio hacia arriba, solo para precios positivos."""
    return int(valor + 0.5)


def banda(vigente: int) -> tuple[int, int]:
    if vigente <= 0:
        raise ValueError(f"precio vigente invalido: {vigente}")
    bajo = max(1, _redondear(vigente * 0.5))
    alto = max(bajo, _redondear(vigente * 1.5))
    return bajo, alto


def dentro_de_banda(precio: int, vigente: int) -> bool:
    if vigente <= 0 or precio <= 0:
        return False
    bajo, alto = banda(vigente)
    return bajo <= int(precio) <= alto


def siguiente_precio_venta(vigente: int, expiradas_seguidas: int) -> int:
    """Parte en 1,0x y baja 0,1x por cada oferta de venta seguida que expiro.

    No baja de 0,5x ni sube de 1,5x.
    """
    bajo, alto = banda(vigente)
    factor = max(0.5, 1.0 - 0.1 * max(0, expiradas_seguidas))
    return min(alto, max(bajo, _redondear(vigente * factor)))


def precio_compra(vigente: int) -> int:
    """Oferta de compra al piso de la banda, para no regalar margen."""
    return banda(vigente)[0]


def vigente(sku: str) -> int | None:
    """Precio de mercado del SKU, con el mismo lector que el portal."""
    from app.catalogo import _mapa_precios

    precio = _mapa_precios().get(sku)
    return precio if precio and precio > 0 else None
