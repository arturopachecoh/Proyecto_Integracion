"""Primera compra real de un insumo: challenge -> PoW -> solicitud.

Sirve para medir cuanto demora en llegar y asi saber en que unidad
esta el campo "time" del catalogo (horas o minutos).

Uso (solo dev):
  docker compose run --rm --build web python -m scripts.probar_compra
  docker compose run --rm --build web python -m scripts.probar_compra API-AMOXI-500 50
"""
import sys
import time
from datetime import datetime, timezone

from app import farma_client
from app.config import FARMA_ENV
from app.pow import solve

if FARMA_ENV != "dev":
    print(f"FARMA_ENV={FARMA_ENV}. Este script es solo para dev, no hago nada.")
    raise SystemExit(1)

sku = sys.argv[1] if len(sys.argv) > 1 else "API-AMOXI-500"
qty = int(sys.argv[2]) if len(sys.argv) > 2 else 50

catalogo = {p["sku"]: p for p in farma_client.available_products()}
tiempo_catalogo = catalogo[sku]["production"]["time"]
print(f"Comprando {qty} x {sku} (lote {catalogo[sku]['production']['batch']}, "
      f"time en catalogo = {tiempo_catalogo})\n")

# 1. Pedir el desafio
ch = farma_client.fabrication_challenge(sku, qty)
print(f"[1] Desafio: dificultad {ch['difficulty']} bits, expira {ch['expiresAt']}")

# 2. Resolverlo
t0 = time.time()
nonce = solve(ch["prefix"], ch["difficulty"])
print(f"[2] Resuelto en {time.time() - t0:.2f}s, nonce = {nonce}")
if nonce is None:
    raise SystemExit("No se alcanzo a resolver antes de que expirara")

# 3. Comprar
resp = farma_client.request_products(sku, qty, ch["challengeId"], nonce)
ahora = datetime.now(timezone.utc)
llega = datetime.fromisoformat(resp["availableAt"].replace("Z", "+00:00"))
espera_min = (llega - ahora).total_seconds() / 60
print(f"[3] Compra OK. Llega: {resp['availableAt']}  (en {espera_min:.1f} minutos)")

if abs(espera_min - tiempo_catalogo * 60) < abs(espera_min - tiempo_catalogo):
    print(f"    -> 'time' del catalogo parece estar en HORAS ({tiempo_catalogo} h ~ {espera_min:.0f} min)")
else:
    print(f"    -> 'time' del catalogo parece estar en MINUTOS ({tiempo_catalogo} min ~ {espera_min:.1f} min)")

# 4. Donde quedo reservado el espacio
print("\n[4] Ocupacion de espacios despues de la compra:")
for s in farma_client.spaces():
    tipo = [k for k in ("checkIn", "checkOut", "packaging", "cold", "buffer", "quarantine") if s.get(k)]
    print(f"    {', '.join(tipo) or 'bodega principal':<20} {s['usedSpace']}/{s['totalSpace']}")
