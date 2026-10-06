"""Produce kits completos: compra insumos, fabrica intermedios y arma los kits.

Uso:
  docker compose run --rm --build worker python -m app.scripts.producir KIT-RESP-ADULTO 1
  docker compose run --rm --build worker python -m app.scripts.producir KIT-RESP-ADULTO 30 KIT-GASTRO 30
  ... --plan        solo muestra que compraria y fabricaria, sin hacer nada
  ... --tanda 5     cuantos kits de cada tipo planifica a la vez (default 10)

Requiere que el worker este corriendo (registra llegadas y cuida el frio).
En prod pide confirmacion. Se puede cortar con Ctrl+C y volver a lanzar
con lo que falte.
"""
import logging
import sys

from app.config import FARMA_ENV
from app.produccion import planificar, producir

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)

args = sys.argv[1:]
tanda = 10
if "--tanda" in args:
    i = args.index("--tanda")
    tanda = int(args[i + 1])
    del args[i:i + 2]
solo_plan = "--plan" in args
args = [a for a in args if not a.startswith("--")]

if not args or len(args) % 2:
    raise SystemExit("Uso: python -m app.scripts.producir KIT CANTIDAD [KIT CANTIDAD ...] [--plan] [--tanda N]")
objetivos = {args[i]: int(args[i + 1]) for i in range(0, len(args), 2)}

print(f"Objetivo: {objetivos}  (tanda de {tanda})")
print("\nPrimera tanda, lo que falta pedir:")
for sku, n in planificar({k: min(tanda, n) for k, n in objetivos.items()}).items():
    print(f"  {sku:<20} {n}")

if solo_plan:
    raise SystemExit(0)

if FARMA_ENV != "dev":
    r = input(f"\nEstas en {FARMA_ENV.upper()}. Producir {objetivos}? (escribe 'si'): ")
    if r.strip().lower() != "si":
        raise SystemExit("Cancelado")

producir(objetivos, tanda=tanda)
