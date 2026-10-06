"""Adapter de Integrapay (pasarela de pagos del curso).

Contrato oficial (OpenAPI / checkout/docs):
  POST /payments/auth  {group, secret} -> {success, token}
  POST /payments/init  Bearer + {amount, group, backUrls:{success,error,cancelled}}
                       -> {payment_id, redirect_url}

Modo mock (CHECKOUT_MODE != real): no llama a la universidad.
En Entrega 1 la pasarela real falla ~20% de las veces; el mock replica eso.
"""
from __future__ import annotations

import logging
import random
import threading
import time
import uuid

import httpx

from app.config import (
    CHECKOUT_BASE_URL,
    CHECKOUT_FORCE,
    CHECKOUT_GROUP,
    CHECKOUT_MODE,
    CHECKOUT_SECRET,
    PUBLIC_BASE_URL,
)

log = logging.getLogger("checkout")

ERROR_RATE = 0.20
CANCEL_RATE = 0.10

_token: str | None = None
_token_exp: float = 0
_lock = threading.Lock()


def _jwt_exp(token: str) -> float:
    import base64
    import json

    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(payload))["exp"]


def _auth_token(force: bool = False) -> str:
    """POST /payments/auth. Cachea el JWT hasta ~60s antes de exp."""
    global _token, _token_exp
    if not CHECKOUT_BASE_URL or not CHECKOUT_BASE_URL.startswith("http"):
        raise RuntimeError("CHECKOUT_BASE_URL inválida para modo real")
    if not CHECKOUT_SECRET or not CHECKOUT_GROUP:
        raise RuntimeError("Faltan CHECKOUT_SECRET / CHECKOUT_GROUP (o FARMA_*)")
    with _lock:
        if force or _token is None or time.time() > _token_exp - 60:
            r = httpx.post(
                f"{CHECKOUT_BASE_URL}/payments/auth",
                json={"group": CHECKOUT_GROUP, "secret": CHECKOUT_SECRET},
                timeout=15,
            )
            r.raise_for_status()
            data = r.json()
            _token = data["token"]
            try:
                _token_exp = _jwt_exp(_token)
            except Exception:
                _token_exp = time.time() + 240
        return _token


def crear_transaccion(monto: int, venta_id: int, urls: dict[str, str]) -> dict:
    """urls usa keys internas success | cancelado | error; se mapean a backUrls de Integrapay."""
    tx_id = f"tx-{uuid.uuid4().hex[:16]}"
    if CHECKOUT_MODE != "real":
        return {
            "id": tx_id,
            "status": "PENDING",
            "redirect_url": f"{PUBLIC_BASE_URL}/api/checkout/mock/{venta_id}",
        }

    back_urls = {
        "success": urls["success"],
        "error": urls["error"],
        "cancelled": urls.get("cancelled") or urls.get("cancel") or urls.get("cancelado"),
    }
    payload = {
        "amount": monto,
        "group": CHECKOUT_GROUP,
        "backUrls": back_urls,
    }
    token = _auth_token()
    for attempt in range(2):
        r = httpx.post(
            f"{CHECKOUT_BASE_URL}/payments/init",
            headers={"Authorization": f"Bearer {token}"},
            json=payload,
            timeout=15,
        )
        if r.status_code == 401 and attempt == 0:
            token = _auth_token(force=True)
            continue
        r.raise_for_status()
        data = r.json()
        payment_id = str(data.get("payment_id") or data.get("id") or tx_id)
        redirect = data.get("redirect_url") or data.get("redirectUrl")
        if not redirect:
            raise RuntimeError("Integrapay no devolvió redirect_url")
        return {"id": payment_id, "status": data.get("status") or "PENDING", "redirect_url": redirect}
    raise RuntimeError("No se pudo inicializar el pago en Integrapay")


def resultado_mock() -> str:
    if CHECKOUT_FORCE in {"exito", "cancelado", "error"}:
        return CHECKOUT_FORCE
    roll = random.random()
    if roll < ERROR_RATE:
        return "error"
    if roll < ERROR_RATE + CANCEL_RATE:
        return "cancelado"
    return "exito"
