"""Compra un insumo y lo registra en custodia.

Uso:
  docker compose run --rm --build worker python -m app.scripts.comprar API-AMOXI-500 50

En prod pide confirmacion antes de comprar.
"""
import logging
import sys

from app.config import FARMA_ENV
from app.operaciones import comprar

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

if len(sys.argv) != 3:
    raise SystemExit("Uso: python -m app.scripts.comprar SKU CANTIDAD")

sku, cantidad = sys.argv[1], int(sys.argv[2])

if FARMA_ENV != "dev":
    r = input(f"Estas en {FARMA_ENV.upper()}. Comprar {cantidad} x {sku}? (escribe 'si'): ")
    if r.strip().lower() != "si":
        raise SystemExit("Cancelado")

comprar(sku, cantidad)