"""Catálogo de kits para el portal: stock local + precio vigente.

Si Farma no está configurada se usa un catálogo mock (KIT-RESP-ADULTO)
para poder terminar el portal sin pegarle a la universidad.
"""
from __future__ import annotations

import logging

from app import custodia, farma_client
from app.config import FARMA_BASE_URL
from app.operaciones import catalogo as farma_catalogo

log = logging.getLogger("catalogo")

MOCK_KITS = (
    {
        "sku": "KIT-RESP-ADULTO",
        "nombre": "Kit respiratorio adulto",
        "imagen": None,
        "precio": 18990,
        "frio": False,
    },
)


def _sin_farma() -> bool:
    return not FARMA_BASE_URL


def _precio_de(raw) -> int | None:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return int(round(raw))
    if isinstance(raw, dict):
        for k in ("price", "precio", "unitPrice", "unit_price", "value"):
            if k in raw:
                return _precio_de(raw[k])
    return None


def _mapa_precios() -> dict[str, int]:
    if _sin_farma():
        return {k["sku"]: k["precio"] for k in MOCK_KITS}
    try:
        raw = farma_client.market_prices()
    except Exception:
        log.exception("No se pudo leer el sistema de precios")
        return {}
    precios: dict[str, int] = {}
    if isinstance(raw, dict):
        items = raw.get("prices") or raw.get("precios") or raw.get("items") or raw
        if isinstance(items, dict):
            for sku, val in items.items():
                p = _precio_de(val)
                if p is not None:
                    precios[str(sku)] = p
            return precios
        raw = items
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            sku = item.get("sku") or item.get("SKU")
            p = _precio_de(item)
            if sku and p is not None:
                precios[str(sku)] = p
    return precios


def _es_kit(sku: str, cat: dict[str, dict]) -> bool:
    prod = cat.get(sku) or {}
    if "sellable" in prod:
        return bool(prod["sellable"])
    if sku.startswith("KIT"):
        return True
    comps = prod.get("components") or []
    if not comps:
        return False
    return any((cat.get(c.get("sku"), {}) or {}).get("components") for c in comps)


def _nombre(prod: dict, sku: str) -> str:
    return prod.get("name") or prod.get("nombre") or prod.get("title") or sku


def _imagen(prod: dict) -> str | None:
    return prod.get("image") or prod.get("imagen") or prod.get("img")


def listar_kits() -> list[dict]:
    precios = _mapa_precios()
    if _sin_farma():
        cat_src = MOCK_KITS
        kits = []
        for k in cat_src:
            sku = k["sku"]
            kits.append({
                "sku": sku,
                "nombre": k["nombre"],
                "imagen": k["imagen"],
                "precio": precios.get(sku),
                "stock": custodia.stock_disponible(sku),
                "frio": k["frio"],
            })
        return kits

    cat = farma_catalogo()
    kits = []
    for sku, prod in cat.items():
        if not _es_kit(sku, cat):
            continue
        kits.append({
            "sku": sku,
            "nombre": _nombre(prod, sku),
            "imagen": _imagen(prod),
            "precio": precios.get(sku),
            "stock": custodia.stock_disponible(sku),
            "frio": bool((prod.get("storage") or {}).get("cold")),
        })
    kits.sort(key=lambda x: x["sku"])
    return kits


def validar_carrito(items: list[dict]) -> dict:
    """items: [{sku, cantidad}]. No reserva; solo valida stock y precio vigente."""
    por_sku = listar_kits()
    indice = {k["sku"]: k for k in por_sku}
    lineas = []
    errores = []
    total = 0
    for item in items:
        sku = str(item.get("sku") or "")
        try:
            cantidad = int(item.get("cantidad") or 0)
        except (TypeError, ValueError):
            cantidad = 0
        kit = indice.get(sku)
        if kit is None:
            errores.append(f"{sku} no es un kit vendible")
            continue
        if cantidad <= 0:
            errores.append(f"{sku}: cantidad inválida")
            continue
        if kit["precio"] is None:
            errores.append(f"{sku}: no hay precio vigente")
            continue
        if cantidad > kit["stock"]:
            errores.append(f"{sku}: stock insuficiente (hay {kit['stock']})")
        subtotal = kit["precio"] * cantidad
        total += subtotal
        lineas.append({
            "sku": sku,
            "nombre": kit["nombre"],
            "cantidad": cantidad,
            "stock": kit["stock"],
            "precio": kit["precio"],
            "subtotal": subtotal,
        })
    return {"ok": not errores, "items": lineas, "total": total, "errores": errores}
