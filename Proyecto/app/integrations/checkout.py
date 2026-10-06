"""Adapter de la pasarela de pago.

Por defecto es mock: no llama a la universidad. El modo real queda
implementado pero no se usa a menos que CHECKOUT_MODE=real y haya URL.
"""
from __future__ import annotations

import random
import uuid

import httpx

from app.config import CHECKOUT_BASE_URL, CHECKOUT_FORCE, CHECKOUT_MODE, PUBLIC_BASE_URL

ERROR_RATE = 0.20
CANCEL_RATE = 0.10


def crear_transaccion(monto: int, venta_id: int, urls: dict[str, str]) -> dict:
    """urls: success, cancel, error (rutas absolutas de retorno)."""
    tx_id = f"tx-{uuid.uuid4().hex[:16]}"
    if CHECKOUT_MODE != "real":
        return {
            "id": tx_id,
            "status": "PENDING",
            "redirect_url": f"{PUBLIC_BASE_URL}/api/checkout/mock/{venta_id}",
        }
    if not CHECKOUT_BASE_URL:
        raise RuntimeError("CHECKOUT_BASE_URL no configurada para modo real")
    r = httpx.post(
        f"{CHECKOUT_BASE_URL.rstrip('/')}/transactions",
        json={
            "amount": monto,
            "return_urls": urls,
            "metadata": {"venta_id": venta_id},
        },
        timeout=15,
    )
    r.raise_for_status()
    data = r.json()
    return {
        "id": str(data.get("id") or data.get("transactionId") or tx_id),
        "status": data.get("status") or "PENDING",
        "redirect_url": data.get("url") or data.get("redirect_url") or data.get("redirectUrl"),
    }


def resultado_mock() -> str:
    if CHECKOUT_FORCE in {"exito", "cancelado", "error"}:
        return CHECKOUT_FORCE
    roll = random.random()
    if roll < ERROR_RATE:
        return "error"
    if roll < ERROR_RATE + CANCEL_RATE:
        return "cancelado"
    return "exito"
