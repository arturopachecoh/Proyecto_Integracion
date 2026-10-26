"""Worker de pedidos: recibe, decide y despacha las OC de sFTP y Pub/Sub.

Cada TICK_SECONDS:
  Pub/Sub -> procesar OC nuevas -> reintentar decisiones -> asignar -> despachar
  -> devolver a stock lo que quedo en checkOut sin salir
Cada SFTP_CADA revisa la casilla sFTP y cada CONCILIAR_CADA concilia con el
sistema de ordenes. Un error en una pieza no detiene a las demas.
"""
import logging
import time

from app import salud
from app.canales import pubsub, sftp
from app.config import SFTP_HOST
from app.pedidos import conciliador, despachador, procesador
from app.retiros import procesamiento as retiros

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("paramiko").setLevel(logging.WARNING)
log = logging.getLogger("pedidos")

TICK_SECONDS = 10
SFTP_CADA = 60
CONCILIAR_CADA = 300
RETIROS_POLLING_CADA = 60  # respaldo por si el webhook de retiros no llega


def _paso(nombre: str, fn) -> None:
    try:
        fn()
        salud.ok(nombre)
    except Exception as e:
        log.exception("Fallo %s", nombre)
        try:
            salud.fallo(nombre, repr(e))
        except Exception:
            log.exception("No se pudo registrar la salud de %s", nombre)


def main():
    log.info("Worker de pedidos iniciado (sFTP: %s, Pub/Sub: %s)",
             bool(SFTP_HOST), pubsub.habilitado())
    ultimo_sftp = ultimo_conciliar = ultimo_retiros = 0.0
    while True:
        ahora = time.monotonic()
        if pubsub.habilitado():
            _paso("pubsub", pubsub.revisar)
        if SFTP_HOST and ahora - ultimo_sftp >= SFTP_CADA:
            _paso("sftp", sftp.revisar)
            ultimo_sftp = ahora
        if ahora - ultimo_retiros >= RETIROS_POLLING_CADA:
            _paso("retiros_polling", retiros.sincronizar_activos)
            ultimo_retiros = ahora
        # Los retiros van antes de asignar: una unidad retirada no se despacha
        _paso("retiros", retiros.procesar_pendientes)
        _paso("procesador", procesador.procesar_nuevas)
        _paso("decisiones", procesador.reintentar_decisiones)
        _paso("asignacion", despachador.asignar_pendientes)
        _paso("despacho", despachador.despachar_pendientes)
        _paso("devolucion", despachador.devolver_desde_checkout)
        if ahora - ultimo_conciliar >= CONCILIAR_CADA:
            _paso("conciliador", conciliador.conciliar)
            ultimo_conciliar = ahora
        time.sleep(TICK_SECONDS)


if __name__ == "__main__":
    main()
