"""Reposicion automatica: mantiene un minimo de cada kit para cumplir las OC.

faltan = minimo + comprometido - (stock vendible + en camino)

El stock vendible no cuenta lo reservado: al reservar para una OC el stock
baja y el reponedor fabrica mas.
"""
from app import custodia, stock
from app.operaciones import catalogo


def faltantes() -> dict[str, int]:
    faltan: dict[str, int] = {}
    for sku, prod in catalogo().items():
        if not prod.get("sellable"):
            continue
        n = (stock.minimo(sku) + stock.comprometido(sku)
             - custodia.stock_disponible(sku) - custodia.en_camino(sku))
        if n > 0:
            faltan[sku] = n
    return faltan
