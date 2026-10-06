"""Muestra el inventario de cada espacio, con lote y vencimiento.

Uso:  docker compose run --rm --build web python -m scripts.ver_inventario
"""
from datetime import datetime, timezone

from app import farma_client

catalogo = {p["sku"]: p for p in farma_client.available_products()}
ahora = datetime.now(timezone.utc)

for s in farma_client.spaces():
    tipo = [k for k in ("checkIn", "checkOut", "packaging", "cold", "buffer", "quarantine") if s.get(k)]
    nombre = ", ".join(tipo) or "bodega principal"
    inventario = farma_client.space_inventory(s["_id"])
    # usedSpace de la API no es confiable: se suma el inventario real (igual que app/espacios.py)
    ocupado = sum(i["quantity"] for i in inventario)
    aviso = f"  [usedSpace de la API dice {s['usedSpace']}]" if ocupado != s["usedSpace"] else ""
    print(f"\n{nombre}  ({ocupado}/{s['totalSpace']}){aviso}")
    if not inventario:
        print("    (vacio)")
    for item in inventario:
        sku = item["sku"]
        print(f"    {sku:<20} {item['quantity']:>4} unidades   "
              f"obsolescence catalogo = {catalogo.get(sku, {}).get('obsolescence')}")
        # Mostrar los lotes y cuanto falta para que venzan
        lotes = {}
        productos = farma_client.space_products(s["_id"], sku)
        print(f"        ejemplo de producto: {productos[0]}")
        for p in productos:
            vence = datetime.fromisoformat(p["expiresAt"].replace("Z", "+00:00"))
            lotes.setdefault(p.get("batch", "sin-lote"), []).append(vence)
        for lote, vencimientos in lotes.items():
            horas = (min(vencimientos) - ahora).total_seconds() / 3600
            print(f"        lote {lote}: {len(vencimientos)} u, vence en {horas:.1f} h "
                  f"({horas * 60:.0f} min)")
