"""Una vuelta del mercado. No factura y no despacha OC de clientes.

Cada tick: refresca las ofertas propias (no hay webhook), compra lo que Farma
no le vende al grupo y vende lo que si puede comprar: acepta compras de otros
grupos, publica ofertas chicas y le compra a Farma para tener que revender.
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone

from app import config, custodia, operaciones
from app import espacios as esp
from app.mercado import acciones, escasez, precio, registro
from app import trades_client

log = logging.getLogger("mercado")

# No se acepta una venta ajena sobre 1,6x el precio vigente. El bot 998 vende a ~1,4-1,5x
# y sin esos insumos escasos (lactosa, jarabe) se rechaza la mitad de las OC.
TOPE_COMPRA = 1.6


def tick(ahora: datetime | None = None) -> dict:
    ahora = ahora or datetime.now(timezone.utc)
    stats = {"aceptadas": [], "publicadas": [], "cierres_vendedor": 0, "cierres_comprador": 0}
    presupuesto = config.MERCADO_MAX_REQUESTS

    def gastar() -> bool:
        nonlocal presupuesto
        if presupuesto <= 0:
            return False
        presupuesto -= 1
        return True

    if gastar():
        try:
            acciones.reconciliar(trades_client.listar_ofertas())
        except Exception:
            log.exception("No se pudieron reconciliar las ofertas")

    for oferta in registro.por_refrescar():
        if not gastar():
            break
        try:
            acciones.refrescar(oferta)
        except Exception:
            log.exception("No se pudo refrescar la oferta %s", oferta.id)

    for sku in escasez.debe_conseguir_en_mercado(config.FARMA_GROUP):
        if not gastar():
            break
        try:
            if _comprar(sku, ahora, gastar, stats):
                continue
        except Exception:
            log.exception("Fallo comprando %s en el mercado", sku)

    for sku in escasez.puede_revender(config.FARMA_GROUP):
        if not gastar():
            break
        try:
            _vender(sku, gastar, stats)
        except Exception:
            log.exception("Fallo vendiendo %s en el mercado", sku)

    ventas, compras = registro.contar_cierres()
    stats["cierres_vendedor"] = ventas
    stats["cierres_comprador"] = compras
    log.info("Mercado: cierres vendedor=%d comprador=%d", ventas, compras)
    return stats


def _comprar(sku: str, ahora: datetime, gastar, stats: dict) -> bool:
    falta = _faltante(sku)
    if falta <= 0:
        registro.olvidar_faltante(sku)
        return False
    desde = registro.faltante_desde(sku, ahora)
    vigente = precio.vigente(sku)
    if not vigente:
        return False
    ofertas = [
        o for o in trades_client.listar_ofertas(sku=sku, side="sell", estado="abierta")
        if o.get("group") != config.FARMA_GROUP
        and not registro.existe(o.get("id") or "")
        and 0 < int(o.get("quantity") or 0) <= config.MERCADO_MAX_ACEPTAR
        and precio.dentro_de_banda(int(o.get("unitPrice") or 0), vigente)
        and int(o.get("unitPrice") or 0) <= vigente * TOPE_COMPRA
    ]
    if ofertas:
        mejor = min(ofertas, key=lambda o: int(o["unitPrice"]))
        if gastar() and acciones.aceptar_ajena(mejor):
            stats["aceptadas"].append(mejor["id"])
        return True
    espera = timedelta(minutes=config.MERCADO_ESPERA_MIN)
    if ahora - desde < espera or registro.hay_abierta(sku, "buy"):
        return False
    pedido = min(falta, config.MERCADO_LOTE)
    valor = precio.precio_compra(vigente)
    if not precio.dentro_de_banda(valor, vigente):
        return False
    if gastar() and acciones.publicar_compra(sku, pedido, valor):
        stats["publicadas"].append(sku)
    return True


def _vender(sku: str, gastar, stats: dict) -> None:
    # Nunca vender bajo costo: Farma cobra ~1,2x el "cost" del catalogo (visto en sus facturas)
    minimo = math.ceil(operaciones.catalogo()[sku]["cost"] * 1.2)
    # 1. Otro grupo quiere comprar: es la venta mas segura
    compras = [
        o for o in trades_client.listar_ofertas(sku=sku, side="buy", estado="abierta")
        if o.get("group") != config.FARMA_GROUP
        and not registro.existe(o.get("id") or "")
        and 0 < int(o.get("quantity") or 0) <= _excedente(sku)  # sin tocar la reserva para fabricar
        and (o.get("unitPrice") or 0) >= minimo
    ]
    if compras:
        # Despacho tiene poca capacidad (25 en dev): las unidades tienen que caber
        # y siempre quedan 5 lugares para despachar las OC de los clientes
        cupo = esp.libres("checkOut") - 5
        compras = [o for o in compras if int(o["quantity"]) <= cupo]
    if compras and gastar():
        mejor = max(compras, key=lambda o: int(o["unitPrice"]))
        if acciones.aceptar_compra_ajena(mejor):
            stats["aceptadas"].append(mejor["id"])
    # 2. Tener stock para revender: si baja de la reserva + un lote, se le compra uno a Farma
    lote = operaciones.tamano_lote(sku)
    if custodia.stock_disponible(sku) + custodia.en_camino(sku) < _reserva(sku) + lote:
        operaciones.comprar(sku, lote)
        log.info("Compre %d x %s a Farma para revender", lote, sku)
    # 3. Publicar una venta chica, una abierta por SKU
    if registro.hay_abierta(sku, "sell") or not gastar():
        return
    if _excedente(sku) < config.MERCADO_LOTE or esp.libres("checkOut") - 5 < config.MERCADO_LOTE:
        return
    vigente = precio.vigente(sku)
    if not vigente:
        return
    valor = max(minimo, precio.siguiente_precio_venta(vigente, registro.expiradas_seguidas(sku)))
    if not precio.dentro_de_banda(valor, vigente):
        return
    if acciones.publicar_venta(sku, config.MERCADO_LOTE, valor):
        stats["publicadas"].append(sku)


def _faltante(sku: str) -> int:
    """Cuanto falta para MERCADO_OBJETIVO. El comprometido de OC es de kits, no de este insumo."""
    tengo = custodia.stock_disponible(sku) + custodia.en_camino(sku)
    return max(0, config.MERCADO_OBJETIVO - tengo)


def _reserva(sku: str) -> int:
    """Lo que se guarda para fabricar: 3 tandas de la receta que mas usa este insumo."""
    tanda = max((c["req"] * d["production"]["batch"] for d in operaciones.catalogo().values()
                 for c in d["components"] if c["sku"] == sku), default=0)
    return max(config.MERCADO_LOTE, 3 * tanda)


def _excedente(sku: str) -> int:
    """Solo se vende lo que sobra despues de la reserva para fabricar."""
    return max(0, custodia.stock_disponible(sku) - _reserva(sku))
