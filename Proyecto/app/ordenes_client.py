"""Cliente del sistema de ordenes de compra.

Mismo patron que farma_client:
- Pide el token una vez y lo reutiliza hasta que esta por vencer
  (/ordenes-compra/autenticar permite solo 20 llamadas por IP cada 5 minutos).
- Si una llamada responde 401, renueva el token y reintenta una vez.
- Si responde 429 (limite de 250/min por grupo), espera lo que indica
  Ratelimit-Reset (maximo 60 s) y reintenta, hasta 6 intentos en total.
"""
import threading
import time

import httpx

from app.config import FARMA_GROUP, ORDENES_BASE_URL, ORDENES_SECRET
from app.farma_client import _jwt_exp

_token: str | None = None
_token_exp: float = 0
_lock = threading.Lock()


def get_token(force: bool = False) -> str:
    global _token, _token_exp
    with _lock:
        if force or _token is None or time.time() > _token_exp - 60:
            r = httpx.post(
                f"{ORDENES_BASE_URL}/ordenes-compra/autenticar",
                json={"group": FARMA_GROUP, "secret": ORDENES_SECRET},
                timeout=15,
            )
            r.raise_for_status()
            _token = r.json()["token"]
            _token_exp = _jwt_exp(_token)
        return _token


def request(method: str, path: str, **kwargs):
    url = f"{ORDENES_BASE_URL}{path}"
    renovado = forzar = False
    for _ in range(6):
        headers = {"Authorization": "Bearer " + get_token(force=forzar)}
        forzar = False
        r = httpx.request(method, url, headers=headers, timeout=15, **kwargs)
        if r.status_code == 401 and not renovado:
            renovado = forzar = True
            continue
        if r.status_code == 429:
            try:
                espera = float(r.headers.get("Ratelimit-Reset", "10"))
            except ValueError:
                espera = 10
            time.sleep(min(espera, 60) + 1)
            continue
        break
    r.raise_for_status()
    return r.json() if r.content else None


def obtener(oc_id: str) -> dict:
    """Detalle oficial de la OC. Al consultarla, el sistema aplica el vencimiento."""
    return request("GET", f"/ordenes-compra/ordenes/{oc_id}")


def actualizar_estado(oc_id: str, estado: str) -> None:
    """estado: aceptada o rechazada. 400 si la OC ya no esta en creada."""
    request("POST", f"/ordenes-compra/ordenes/{oc_id}/estado", json={"estado": estado})


def pubsub_key() -> dict:
    """Llave de la cuenta de servicio para crear la suscripcion de Pub/Sub."""
    return request("GET", "/ordenes-compra/pubsub/key")
