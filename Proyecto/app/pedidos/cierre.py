"""Cerrar una OC que no se va a cumplir: libera lo reservado y no despachado."""
import logging

from app import custodia
from app.pedidos import bandeja

log = logging.getLogger("pedidos")


def reconciliar_pendientes(oc_id: str) -> int:
    """Confirma en custodia las unidades que el sistema de ordenes ya cuenta
    despachadas pero que custodia no alcanzo a anotar (caida entre el dispatch
    y la confirmacion). Usa el despachado_remoto que guardar_detalle acaba de
    copiar. Los despachos se intentan en el orden de pendientes_de_venta (por
    id), asi que las primeras N pendientes son las que salieron.
    Devuelve cuantas unidades confirmo."""
    o = bandeja.get(oc_id)
    if o is None or o.venta_id is None:
        return 0
    salieron = (o.despachado_remoto or 0) - custodia.despachadas_de_venta(o.venta_id)
    if salieron <= 0:
        return 0
    ids = custodia.pendientes_de_venta(o.venta_id)[:salieron]
    for unidad_id in ids:
        custodia.confirmar_despacho(unidad_id)
    if ids:
        log.warning("OC %s: %d unidades ya habian salido sin anotarse, se confirman: %s",
                    oc_id, len(ids), ids)
    return len(ids)


def cerrar(oc_id: str, estado_final: str, motivo: str | None = None) -> None:
    """estado_final: vencida, rechazada o descartada. Primero se confirman las
    unidades que si salieron; las reservadas y sin despachar vuelven a en_stock.
    Las que quedaron en checkOut las regresa despachador.devolver_desde_checkout."""
    o = bandeja.get(oc_id)
    if o is None:
        return
    if o.venta_id is not None:
        reconciliar_pendientes(oc_id)
        custodia.liberar_reserva(o.venta_id)
    bandeja.marcar(oc_id, estado_final, error=motivo)
    log.info("OC %s cerrada como %s%s", oc_id, estado_final, f": {motivo}" if motivo else "")
