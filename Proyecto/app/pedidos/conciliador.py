"""Conciliador: mantiene la base al dia con el sistema de ordenes (la fuente oficial).

Cada ~5 minutos consulta las OC que no estan cerradas: si el sistema dice que
vencio, se libera lo reservado; si dice cumplida, se anota.
"""
import logging

from app import custodia, ordenes_client
from app.pedidos import bandeja, cierre

log = logging.getLogger("pedidos")


def conciliar() -> int:
    revisadas = 0
    for o in bandeja.en_estado("aceptada") + bandeja.cumplidas_sin_confirmar():
        try:
            _conciliar_una(o)
            revisadas += 1
        except Exception as e:
            log.exception("OC %s: no se pudo conciliar", o.id)
            bandeja.registrar_error(o.id, repr(e))
    return revisadas


def _conciliar_una(o) -> None:
    remoto = ordenes_client.obtener(o.id)
    bandeja.guardar_detalle(o.id, remoto)
    estado = remoto.get("estado")
    if estado == "aceptada":
        return
    if estado == "cumplida":
        # El sistema ya cuenta la OC completa: se anotan las salidas que faltaron
        cierre.reconciliar_pendientes(o.id)
        pendientes = custodia.pendientes_de_venta(o.venta_id) if o.venta_id else []
        if pendientes:
            # Sobran unidades que no salieron: vuelven a stock (las de checkOut las
            # regresa despachador.devolver_desde_checkout)
            log.warning("OC %s cumplida con %d unidades que no salieron, se liberan: %s",
                        o.id, len(pendientes), pendientes)
            custodia.liberar_reserva(o.venta_id)
        bandeja.marcar(o.id, "cumplida")
    elif estado == "vencida":
        cierre.cerrar(o.id, "vencida", "vencio sin completarse")
    else:
        cierre.cerrar(o.id, "descartada", f"estado remoto inesperado: {estado}")
