"""Fabrica un producto acondicionado o un kit, con registro en custodia.

Uso:
  docker compose run --rm --build worker python -m app.scripts.fabricar BLI-AMOXI-500 3
  docker compose run --rm --build worker python -m app.scripts.fabricar KIT-RESP-ADULTO 1 --verificar

--verificar solo revisa si hay componentes suficientes, sin mover ni fabricar.
En prod pide confirmacion antes de fabricar.
"""
import logging
import sys

from app.config import FARMA_ENV
from app.operaciones import FaltanInsumos, fabricar, receta, verificar_componentes

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)

args = [a for a in sys.argv[1:] if not a.startswith("--")]
if len(args) != 2:
    raise SystemExit("Uso: python -m app.scripts.fabricar SKU CANTIDAD [--verificar]")
sku, cantidad = args[0], int(args[1])

print(f"Receta para {cantidad} x {sku}:")
for comp, n in receta(sku, cantidad).items():
    print(f"  {comp:<20} {n}")

try:
    if "--verificar" in sys.argv:
        verificar_componentes(sku, cantidad)
        print("\nHay componentes suficientes.")
        raise SystemExit(0)

    if FARMA_ENV != "dev":
        r = input(f"\nEstas en {FARMA_ENV.upper()}. Fabricar {cantidad} x {sku}? (escribe 'si'): ")
        if r.strip().lower() != "si":
            raise SystemExit("Cancelado")

    fabricar(sku, cantidad)
except FaltanInsumos as e:
    print("\nNo se puede fabricar. Falta:")
    for comp, n in e.faltantes.items():
        print(f"  {comp:<20} {n}")
    raise SystemExit(1)
