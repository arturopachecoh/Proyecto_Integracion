"""Calcula cuanto hay que fabricar y comprar para tener N unidades de cada kit.

Uso:
  docker compose run --rm --build web python -m scripts.calcular_requerimientos        # 30 de cada kit
  docker compose run --rm --build web python -m scripts.calcular_requerimientos 35     # con colchon
"""
import json
import math
import sys
from collections import defaultdict

from app import farma_client


def calcular(catalogo: list[dict], unidades_por_kit: int):
    P = {p["sku"]: p for p in catalogo}
    kits = [s for s, p in P.items() if p["sellable"]]
    batch = lambda s: P[s]["production"]["batch"]

    # Nivel 1: kits -> cuantos kits fabricar (redondeado al lote)
    a_fabricar = {k: math.ceil(unidades_por_kit / batch(k)) * batch(k) for k in kits}

    # Nivel 2: productos acondicionados (sumando la demanda de todos los kits que los usan)
    demanda_intermedios = defaultdict(int)
    for k, qty in a_fabricar.items():
        for c in P[k]["components"]:
            demanda_intermedios[c["sku"]] += c["req"] * qty
    intermedios = {s: math.ceil(q / batch(s)) * batch(s) for s, q in demanda_intermedios.items()}

    # Nivel 3: insumos a comprar a Farma Central
    demanda_insumos = defaultdict(int)
    for s, qty in intermedios.items():
        for c in P[s]["components"]:
            demanda_insumos[c["sku"]] += c["req"] * qty
    insumos = {s: math.ceil(q / batch(s)) * batch(s) for s, q in demanda_insumos.items()}

    return P, a_fabricar, intermedios, demanda_insumos, insumos


def huella_lote(P, sku):
    """Unidades que hay que dejar en acondicionamiento para fabricar UN lote."""
    return sum(c["req"] for c in P[sku]["components"]) * P[sku]["production"]["batch"]


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    catalogo = farma_client.available_products()
    P, kits, intermedios, demanda_insumos, insumos = calcular(catalogo, n)
    frio = lambda s: "FRIO" if P[s]["storage"]["cold"] else ""

    print(f"=== Objetivo: {n} unidades de cada uno de los {len(kits)} kits ===\n")

    print("KITS (nivel 1)")
    for s, q in kits.items():
        p = P[s]
        print(f"  {s:<20} fabricar {q:>4}  lote {p['production']['batch']:>2}  "
              f"lotes {q // p['production']['batch']:>3}  huella/lote {huella_lote(P, s):>3}  {frio(s)}")

    print("\nPRODUCTOS ACONDICIONADOS (nivel 2)")
    for s, q in sorted(intermedios.items()):
        p = P[s]
        print(f"  {s:<20} fabricar {q:>4}  lote {p['production']['batch']:>2}  "
              f"lotes {q // p['production']['batch']:>3}  huella/lote {huella_lote(P, s):>3}  "
              f"vida {p['obsolescence']:>4}  {frio(s)}")

    print("\nINSUMOS A COMPRAR (nivel 3)")
    costo_total = 0
    for s, q in sorted(insumos.items(), key=lambda x: -x[1]):
        p = P[s]
        costo = q * p["cost"]
        costo_total += costo
        sobra = q - demanda_insumos[s]
        print(f"  {s:<20} comprar {q:>5}  (necesita {demanda_insumos[s]:>5}, sobran {sobra:>3})  "
              f"lote {p['production']['batch']:>3}  costo {costo:>7}  {frio(s)}")

    print("\nRESUMEN")
    print(f"  Lotes de kits a fabricar:          {sum(q // P[s]['production']['batch'] for s, q in kits.items())}")
    print(f"  Lotes de intermedios a fabricar:   {sum(q // P[s]['production']['batch'] for s, q in intermedios.items())}")
    print(f"  Tipos de insumo a comprar:         {len(insumos)}")
    print(f"  Unidades de insumo a comprar:      {sum(insumos.values())}")
    print(f"  Costo estimado de insumos:         {costo_total}")
    grandes = [s for s in list(intermedios) + list(kits) if huella_lote(P, s) > 150]
    if grandes:
        print(f"  OJO: lotes que no caben en acondicionamiento (150): {grandes}")


if __name__ == "__main__":
    main()
