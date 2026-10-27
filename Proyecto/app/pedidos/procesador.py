"""Procesador de OC: decide cada OC nueva y avisa la decision.

Cada paso se anota en la base ANTES de llamar a la API externa. Si el proceso
cae entre la anotacion y la respuesta, reintentar_decisiones() consulta la OC
oficial y sigue desde lo que diga ella (seccion 5 del diseno, docs/04).
"""
import logging
from datetime import datetime, timezone

import httpx

from app import custodia, ordenes_client, stock
from app.operaciones import catalogo
from app.pedidos import bandeja, cierre, regla

log = logging.getLogger("pedidos")

ESPERA_CANDADO_S = 30
# Tras tantos errores seguidos una OC nueva se descarta para no gastar requests
MAX_INTENTOS = 10
ESTADO_OBJETIVO = {"aceptando": "aceptada", "rechazando": "rechazada"}


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _es_kit(sku: str | None) -> bool:
    return bool(sku) and bool(catalogo().get(sku, {}).get("sellable"))


def procesar_nuevas(limite: int = 20) -> int:
    hechas = 0
    for oc_id in bandeja.nuevas(limite):
        try:
            procesar(oc_id)
            hechas += 1
        except Exception as e:
            # Queda "nueva" (o en aceptando/rechazando): se reintenta en el proximo tick
            log.exception("OC %s: error procesando", oc_id)
            bandeja.registrar_error(oc_id, repr(e))
            o = bandeja.get(oc_id)
            if o is not None and o.intentos >= MAX_INTENTOS and bandeja.reclamar(
                    oc_id, "nueva", "descartada",
                    {"motivo": f"fallo {o.intentos} veces, ultimo error: {e!r}"[:500]}):
                log.error("OC %s descartada tras %d errores, ultimo: %r", oc_id, o.intentos, e)
    return hechas


def procesar(oc_id: str) -> None:
    try:
        oc = ordenes_client.obtener(oc_id)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            bandeja.reclamar(oc_id, "nueva", "descartada",
                             {"motivo": "la OC no existe en el sistema de ordenes"})
            log.warning("OC %s no existe: descartada", oc_id)
            return
        raise
    bandeja.guardar_detalle(oc_id, oc)

    accion, motivo = regla.validar_oc(oc, _ahora(), es_kit=_es_kit)
    if accion == "descartar":
        bandeja.reclamar(oc_id, "nueva", "descartada", {"motivo": motivo})
        log.info("OC %s descartada: %s", oc_id, motivo)
        return
    if accion == "rechazar":
        bandeja.reclamar(oc_id, "nueva", "rechazando", {"motivo": motivo})
    else:
        _decidir_por_stock(oc_id, oc)
    enviar_decision(oc_id)


def _decidir_por_stock(oc_id: str, oc: dict) -> None:
    vencimiento = regla._fecha(oc["vencimiento"])
    with stock.candado_stock(esperar_s=ESPERA_CANDADO_S):
        ev = regla.evaluar(oc["sku"], oc["cantidad"], vencimiento)
        decision = ev.como_dict()
        decision["precio_unitario"] = oc.get("precioUnitario")  # para la Venta de la OC
        if not ev.acepta:
            decision["motivo"] = "no hay stock ni produccion que llegue a tiempo"
            bandeja.reclamar(oc_id, "nueva", "rechazando", decision)
            log.info("OC %s se rechazara: %s", oc_id, decision)
            return
        if not bandeja.reclamar(oc_id, "nueva", "aceptando", decision):
            return  # otro proceso ya la tomo
        venta_id = asegurar_venta(oc_id)
        if ev.reservar_ahora:
            ids = [u.id for u in custodia.unidades_disponibles(oc["sku"])][: ev.reservar_ahora]
            custodia.asignar_unidades_a_venta(venta_id, ids)
        log.info("OC %s se aceptara: %s", oc_id, decision)


def asegurar_venta(oc_id: str) -> int:
    """La Venta de una OC aceptada (la crea si una caida la dejo sin venta).
    Es lo que deja la OC en el modelo de custodia: unidades, lote y cliente."""
    o = bandeja.get(oc_id)
    if o.venta_id is not None:
        return o.venta_id
    precio = int(round((o.decision or {}).get("precio_unitario") or 0))
    venta_id = custodia.crear_venta(
        comprador_nombre=o.cliente or "", comprador_email=None,
        total=precio * (o.cantidad or 0), canal=o.canal, orden_externa_id=o.id,
        items=[{"sku": o.sku, "cantidad": o.cantidad, "precio_unitario": precio}],
        estado="orden_compra",
    )
    bandeja.enlazar_venta(oc_id, venta_id)
    return venta_id


def _enviar(oc_id: str, objetivo: str) -> None:
    ordenes_client.actualizar_estado(oc_id, objetivo)
    bandeja.marcar(oc_id, objetivo)
    log.info("OC %s %s en el sistema de ordenes", oc_id, objetivo)


def enviar_decision(oc_id: str) -> None:
    o = bandeja.get(oc_id)
    objetivo = ESTADO_OBJETIVO.get(o.estado) if o else None
    if objetivo is None:
        return
    try:
        _enviar(oc_id, objetivo)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 400:
            conciliar_decision(oc_id)  # ya no estaba en creada: ver que paso
            return
        raise


def conciliar_decision(oc_id: str) -> None:
    """Para una OC en aceptando/rechazando: consulta la fuente oficial y sigue."""
    o = bandeja.get(oc_id)
    objetivo = ESTADO_OBJETIVO.get(o.estado) if o else None
    if objetivo is None:
        return
    remoto = ordenes_client.obtener(oc_id)
    bandeja.guardar_detalle(oc_id, remoto)
    estado = remoto.get("estado")
    if estado == "creada":
        _enviar(oc_id, objetivo)
    elif estado == objetivo or (objetivo == "aceptada" and estado == "cumplida"):
        bandeja.marcar(oc_id, estado)
    elif estado == "vencida":
        cierre.cerrar(oc_id, "vencida", "vencio antes de responderla")
    else:
        cierre.cerrar(oc_id, "descartada", f"estado remoto inesperado: {estado}")


def reintentar_decisiones() -> None:
    for o in bandeja.en_estado("aceptando", "rechazando"):
        try:
            conciliar_decision(o.id)
        except Exception as e:
            log.exception("OC %s: no se pudo conciliar la decision", o.id)
            bandeja.registrar_error(o.id, repr(e))
