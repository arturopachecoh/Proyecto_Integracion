"""Una vuelta del mercado. No factura y no despacha OC de clientes.

Cada tick: refresca las ofertas propias (no hay webhook), compra lo que Farma
no le vende al grupo y publica el excedente de lo que si puede comprar.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from app import config, custodia
from app.mercado import acciones, escasez, precio, registro
from app import trades_client

log = logging.getLogger("mercado")


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
            _vender(sku, stats)
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
        and 0 < int(o.get("quantity") or 0) <= min(falta, config.MERCADO_LOTE)
        and precio.dentro_de_banda(int(o.get("unitPrice") or 0), vigente)
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


def _vender(sku: str, stats: dict) -> None:
    if registro.hay_abierta(sku, "sell"):
        return
    if _excedente(sku) < config.MERCADO_LOTE:
        return
    vigente = precio.vigente(sku)
    if not vigente:
        return
    valor = precio.siguiente_precio_venta(vigente, registro.expiradas_seguidas(sku))
    if not precio.dentro_de_banda(valor, vigente):
        return
    if acciones.publicar_venta(sku, config.MERCADO_LOTE, valor):
        stats["publicadas"].append(sku)


def _faltante(sku: str) -> int:
    """Piso = MERCADO_LOTE. El comprometido de OC es de kits, no de este insumo."""
    tengo = custodia.stock_disponible(sku) + custodia.en_camino(sku)
    return max(0, config.MERCADO_LOTE - tengo)


def _excedente(sku: str) -> int:
    """Deja un lote para fabricar antes de publicar una venta."""
    return max(0, custodia.stock_disponible(sku) - config.MERCADO_LOTE)
