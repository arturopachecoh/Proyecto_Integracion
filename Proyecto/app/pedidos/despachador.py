"""Despachador de OC: asigna unidades a las OC aceptadas y las despacha.

Por cada unidad: moverla a checkOut, POST /farma-central/dispatch y confirmar
en custodia. Si falla a mitad de camino, la unidad queda pendiente y se
reintenta en el proximo tick. VentaUnidad.unidad_id es unico: una unidad no
puede quedar en dos OC ni despacharse dos veces.
"""
import logging

import httpx

from app import custodia, farma_client, ordenes_client, stock
from app import espacios as esp
from app.operaciones import es_frio, mover
from app.pedidos import bandeja, procesador
from app.retiros import procesamiento as retiros

log = logging.getLogger("pedidos")

# Cada despacho son 2 requests a Farma Central (mover + dispatch). El limite
# de 250/min es por grupo y lo comparten el worker de frio y el reponedor.
MAX_DESPACHOS_POR_TICK = 5


def asignar_pendientes() -> int:
    """Asigna unidades que ya existen a OC aceptadas que aun no las tienen,
    empezando por la que vence primero."""
    if _pausa_por_retiro():
        return 0
    asignadas = 0
    with stock.candado_stock(esperar_s=procesador.ESPERA_CANDADO_S):
        for o in bandeja.aceptadas_por_vencimiento():
            venta_id = o.venta_id or procesador.asegurar_venta(o.id)
            faltan = (o.cantidad or 0) - custodia.unidades_de_venta(venta_id)
            if faltan <= 0:
                continue
            ids = [u.id for u in custodia.unidades_disponibles(o.sku)][:faltan]
            if ids:
                custodia.asignar_unidades_a_venta(venta_id, ids)
                asignadas += len(ids)
                log.info("OC %s: %d unidades asignadas", o.id, len(ids))
    return asignadas


def _pausa_por_retiro() -> bool:
    """Un retiro recien llegado aun no saca sus unidades de circulacion: se
    espera (segundos, o el tope de procesamiento.PAUSA_MAXIMA_DESPACHO) para no
    asignar ni despachar producto retirado."""
    if retiros.hay_retiro_sin_investigar():
        log.warning("Retiro de lote sin investigar: asignacion y despacho en pausa este tick")
        return True
    return False


def despachar_pendientes(maximo: int = MAX_DESPACHOS_POR_TICK) -> int:
    if _pausa_por_retiro():
        return 0
    hechos = 0
    for o in bandeja.aceptadas_por_vencimiento():
        if o.venta_id is None:
            continue
        for unidad_id in custodia.pendientes_de_venta(o.venta_id):
            if hechos >= maximo:
                return hechos
            estado = custodia.estado_de(unidad_id)
            if estado == "cuarentena":
                # Producto retirado: nunca se despacha. La OC recibe otra unidad
                custodia.desasignar_retirada(unidad_id)
                log.warning("OC %s: %s esta retirada (cuarentena), se desasigna", o.id, unidad_id)
                continue
            if estado != "reservada":
                log.error("OC %s: %s no se despacha, su estado es %s", o.id, unidad_id, estado)
                continue
            if _despachar_unidad(unidad_id, o):
                hechos += 1
        if custodia.despachadas_de_venta(o.venta_id) >= (o.cantidad or 0):
            bandeja.marcar(o.id, "cumplida")
            log.info("OC %s cumplida: %d unidades despachadas", o.id, o.cantidad)
    return hechos


def _despachar_unidad(unidad_id: str, o) -> bool:
    try:
        if custodia.espacio_de(unidad_id) != "checkOut":
            mover(unidad_id, "checkOut")
        farma_client.dispatch(unidad_id, o.id)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404 and _ya_salio(o):
            log.warning("OC %s: %s ya habia salido (caida antes de anotarlo)", o.id, unidad_id)
        elif e.response.status_code == 404:
            # No salio y Farma Central ya no la tiene (vencio o se perdio): se quita
            # de la OC para que asignar_pendientes le asigne otra
            log.error("OC %s: %s ya no existe en Farma Central, se desasigna", o.id, unidad_id)
            custodia.descartar_asignacion(unidad_id)
            bandeja.registrar_error(o.id, f"dispatch {unidad_id}: 404, unidad desasignada")
            return False
        else:
            log.error("OC %s: no se pudo despachar %s: %s", o.id, unidad_id, e.response.text)
            bandeja.registrar_error(o.id, f"dispatch {unidad_id}: {e.response.status_code}")
            return False
    custodia.confirmar_despacho(unidad_id)
    log.info("OC %s: despachada %s", o.id, unidad_id)
    return True


def _ya_salio(o) -> bool:
    """Un 404 dice que la unidad ya no esta. Si el sistema de ordenes cuenta mas
    despachos que custodia, el despacho anterior si llego y solo falto anotarlo."""
    remoto = ordenes_client.obtener(o.id)
    bandeja.guardar_detalle(o.id, remoto)
    return int(remoto.get("despachado") or 0) > custodia.despachadas_de_venta(o.venta_id)


def devolver_desde_checkout(maximo: int = MAX_DESPACHOS_POR_TICK) -> int:
    """Unidades en stock que quedaron en checkOut sin salir (su OC se cerro o
    se libero): checkOut no es un espacio vendible, asi que vuelven a cold (o
    buffer si cold esta lleno) si requieren frio, o a bodega si no. Las
    reservadas no se tocan. Un error deja la unidad para el proximo tick."""
    devueltas = 0
    for u in custodia.unidades_en("checkOut")[:maximo]:
        try:
            if es_frio(u.sku):
                destino = "cold" if esp.libres("cold") > 0 else "buffer"
            else:
                destino = "bodega"
            mover(u.id, destino)
            devueltas += 1
            log.info("%s (%s) devuelta de checkOut a %s", u.id, u.sku, destino)
        except Exception:
            log.exception("No se pudo devolver %s (%s) desde checkOut", u.id, u.sku)
    return devueltas
