"""Worker del canal de mensajeria: interpreta y responde los mensajes recibidos.

Proceso propio porque cada llamada al modelo puede tardar hasta ~40 s: dentro
del ciclo de OC de worker/pedidos.py frenaria las decisiones y los despachos.
Cada TICK_SECONDS termina los mensajes ya decididos e interpreta hasta
procesador.POR_TICK mensajes nuevos.
"""
import logging
import time

from app import salud
from app.mensajeria import procesador

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("mensajeria")

TICK_SECONDS = 5


def main():
    log.info("Worker de mensajeria iniciado")
    while True:
        try:
            procesador.procesar_pendientes()
            salud.ok("mensajeria")
        except Exception as e:
            log.exception("Fallo mensajeria")
            try:
                salud.fallo("mensajeria", repr(e))
            except Exception:
                log.exception("No se pudo registrar la salud de mensajeria")
        time.sleep(TICK_SECONDS)


if __name__ == "__main__":
    main()
