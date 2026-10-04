"""Cliente de Farma Central.

Todo el codigo que hable con Farma Central pasa por aqui.
- Pide el token una sola vez y lo reutiliza hasta que esta por vencer
  (el endpoint /auth permite solo 20 llamadas cada 5 minutos).
- Si una llamada responde 401, renueva el token y reintenta una vez.
"""
import base64
import json
import threading
import time

import httpx

from app.config import FARMA_BASE_URL, FARMA_GROUP, FARMA_API_KEY

# Ajustar segun el resultado de scripts/probar_farma.py:
# "Bearer " si funciono con Bearer, "" si funciono con el token solo.
AUTH_PREFIX = "Bearer "

_token: str | None = None
_token_exp: float = 0
_lock = threading.Lock()


def _jwt_exp(token: str) -> float:
    """Lee la fecha de expiracion (campo exp) que viene dentro del JWT."""
    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(payload))["exp"]


def get_token(force: bool = False) -> str:
    global _token, _token_exp
    with _lock:
        if force or _token is None or time.time() > _token_exp - 60:
            r = httpx.post(
                f"{FARMA_BASE_URL}/farma-central/auth",
                json={"group": FARMA_GROUP, "secret": FARMA_API_KEY},
                timeout=15,
            )
            r.raise_for_status()
            _token = r.json()["token"]
            _token_exp = _jwt_exp(_token)
        return _token


def request(method: str, path: str, *, auth: bool = True, **kwargs):
    url = f"{FARMA_BASE_URL}{path}"
    for attempt in range(2):
        headers = {"Authorization": AUTH_PREFIX + get_token(force=attempt > 0)} if auth else {}
        r = httpx.request(method, url, headers=headers, timeout=15, **kwargs)
        if r.status_code == 401 and auth and attempt == 0:
            continue  # token vencido o invalido: renovar y reintentar una vez
        break
    r.raise_for_status()
    return r.json() if r.content else None


# --- Consultas publicas (no requieren token) ---

def available_products():
    return request("GET", "/farma-central/products/available", auth=False)


def market_prices():
    return request("GET", "/farma-central/market/prices", auth=False)


# --- Espacios ---

def spaces():
    return request("GET", "/farma-central/spaces")


def space_inventory(store_id: str):
    return request("GET", f"/farma-central/spaces/{store_id}/inventory")


def space_products(store_id: str, sku: str, limit: int = 200):
    return request("GET", f"/farma-central/spaces/{store_id}/products",
                   params={"sku": sku, "limit": limit})


# --- Productos ---

def fabrication_challenge(sku: str, quantity: int):
    return request("POST", "/farma-central/fabrication/challenge",
                   json={"sku": sku, "quantity": quantity})


def request_products(sku: str, quantity: int, challenge_id: str, nonce: str):
    return request("POST", "/farma-central/products",
                   json={"sku": sku, "quantity": quantity,
                         "challengeId": challenge_id, "nonce": nonce})


def move_product(product_id: str, store_id: str):
    return request("PATCH", f"/farma-central/products/{product_id}",
                   json={"store": store_id})


# --- Solo en dev ---

def sandbox_product(sku: str):
    return request("POST", "/farma-central/sandbox/products", json={"sku": sku})
