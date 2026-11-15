"""Worker de facturacion: cada minuto emite las facturas pendientes y paga las recibidas.

Proceso propio: si el SOAP se pone lento, no frena los pedidos ni el frio."""
import logging
import time

from app import facturacion, salud

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("facturacion")

TICK_SECONDS = 60


def main():
    log.info("Worker de facturacion iniciado")
    while True:
        try:
            facturacion.emitir_pendientes()
            facturacion.pagar_pendientes()
            salud.ok("facturacion")
        except Exception as e:
            log.exception("Error en facturacion")
            try:
                salud.fallo("facturacion", repr(e))
            except Exception:
                log.exception("No se pudo registrar la salud de facturacion")
        time.sleep(TICK_SECONDS)


if __name__ == "__main__":
    main()
