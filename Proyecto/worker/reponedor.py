"""Reponedor: mantiene el minimo de cada kit con una vuelta de produccion por tick.

Corre en su propio contenedor porque el PoW de fabricacion usa CPU por
minutos y no debe frenar la atencion de las OC.
"""
import logging
import os
import time

from app import produccion, reposicion, salud

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("reponedor")

TICK_SECONDS = 20


def main():
    os.nice(10)  # prioridad baja frente al portal y a los pedidos
    log.info("Reponedor iniciado")
    estado: dict = {}
    while True:
        try:
            objetivos = reposicion.faltantes()
            if objetivos:
                pedidos = produccion.intentar_vuelta(objetivos, estado)
                if pedidos is None:
                    log.info("Hay una produccion manual en curso; espero")
                elif any(pedidos.values()):
                    log.info("Faltantes %s; pedidos en esta vuelta %s", objetivos, pedidos)
            salud.ok("reponedor")
        except Exception as e:
            log.exception("Error en el reponedor")
            try:
                salud.fallo("reponedor", repr(e))
            except Exception:
                log.exception("No se pudo registrar la salud del reponedor")
        time.sleep(TICK_SECONDS)


if __name__ == "__main__":
    main()
