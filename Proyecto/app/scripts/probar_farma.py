"""Primera prueba de conexion con Farma Central. No compra ni fabrica nada.

Uso:  docker compose run --rm --build web python -m scripts.probar_farma
"""
import time

import httpx

from app.config import FARMA_BASE_URL, FARMA_ENV, FARMA_GROUP, FARMA_API_KEY

print(f"Ambiente: {FARMA_ENV} | URL base: {FARMA_BASE_URL} | Grupo: {FARMA_GROUP}\n")

# 1. Catalogo (publico)
r = httpx.get(f"{FARMA_BASE_URL}/farma-central/products/available", timeout=15)
print(f"[1] Catalogo: HTTP {r.status_code}")
if r.status_code == 200:
    productos = r.json()
    print(f"    {len(productos)} productos. Kits vendibles:")
    for p in productos:
        if p.get("sellable"):
            print(f"      - {p['sku']}: {p.get('name')}")
print()

# 2. Precios (publico)
r = httpx.get(f"{FARMA_BASE_URL}/farma-central/market/prices", timeout=15)
print(f"[2] Precios: HTTP {r.status_code}" + (f" ({len(r.json())} SKUs)" if r.status_code == 200 else ""))
print()

# 3. Token (una sola llamada: /auth tiene limite de 20 cada 5 minutos)
r = httpx.post(f"{FARMA_BASE_URL}/farma-central/auth",
               json={"group": FARMA_GROUP, "secret": FARMA_API_KEY}, timeout=15)
print(f"[3] Auth: HTTP {r.status_code}")
if r.status_code != 200:
    print("    Revisen FARMA_GROUP y FARMA_API_KEY en el .env:", r.text)
    raise SystemExit(1)
token = r.json()["token"]
print("    Token obtenido OK\n")

# 4. Espacios: probamos los dos formatos posibles del header Authorization
for nombre, valor in (("Bearer <token>", f"Bearer {token}"), ("<token> solo", token)):
    r = httpx.get(f"{FARMA_BASE_URL}/farma-central/spaces",
                  headers={"Authorization": valor}, timeout=15)
    print(f"[4] Espacios con header '{nombre}': HTTP {r.status_code}")
    if r.status_code == 200:
        print("    Este formato funciona. Ajusten AUTH_PREFIX en app/farma_client.py si hace falta.\n")
        for s in r.json():
            tipo = [k for k in ("checkIn", "checkOut", "packaging", "cold", "buffer", "quarantine") if s.get(k)]
            tipo = ", ".join(tipo) or "bodega principal"
            print(f"      {s['_id']}  {tipo:<20} {s['usedSpace']}/{s['totalSpace']}")
        break
    time.sleep(0.5)
