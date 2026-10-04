"""Proceso de fondo: abastecimiento, traslados, cadena de frio y produccion.

Corre en un contenedor separado del portal, limitado a 1 nucleo,
para que resolver el PoW nunca deje sin CPU al sitio web.
"""
import logging
import os
import time

from app.db import db_ok

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("worker")

TICK_SECONDS = 30


def tick():
    # TODO: revisar inventario, mover productos frios, reponer insumos, producir
    log.info("tick - db_ok=%s", db_ok())


def main():
    os.nice(10)  # prioridad baja: si compite por CPU, gana el portal
    log.info("worker iniciado")
    while True:
        try:
            tick()
        except Exception:
            log.exception("error en tick")  # un error no debe matar el worker
        time.sleep(TICK_SECONDS)


if __name__ == "__main__":
    main()
