"""Worker del mercado entre distribuidoras.

Proceso propio para que una llamada a /trades no frene el portal ni el despacho.
No llama a SOAP: la OC de mercado queda cumplida y la factura es de otro worker.
Un candado de Postgres evita que dos copias aparten el mismo stock.
"""
import logging
import os
import time
from contextlib import contextmanager

from sqlalchemy import text

from app import config, salud
from app.db import engine
from app.mercado import ciclo

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("mercado")

LOCK_MERCADO = 4_000_012


class MercadoOcupado(RuntimeError):
    """Otro proceso ya tiene el candado de este tick."""


@contextmanager
def _candado():
    with engine.connect() as conn:
        if not conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": LOCK_MERCADO}).scalar():
            raise MercadoOcupado()
        try:
            yield
        finally:
            conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": LOCK_MERCADO})
            conn.commit()


def main():
    os.nice(10)
    log.info("Worker de mercado iniciado (lote=%d, espera=%d min)",
             config.MERCADO_LOTE, config.MERCADO_ESPERA_MIN)
    while True:
        try:
            with _candado():
                ciclo.tick()
            salud.ok("mercado")
        except MercadoOcupado:
            log.info("Otro proceso ya corre el mercado; este tick se salta")
        except Exception as e:
            log.exception("Fallo el mercado")
            try:
                salud.fallo("mercado", repr(e))
            except Exception:
                log.exception("No se pudo registrar la salud del mercado")
        time.sleep(config.MERCADO_TICK_SECONDS)


if __name__ == "__main__":
    main()
