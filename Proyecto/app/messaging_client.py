"""Cliente de la plataforma de mensajeria (sistema distinto del de ordenes).

Mismo patron que ordenes_client:
- Pide el token una vez y lo reutiliza hasta que esta por vencer
  (/messaging/auth permite solo 20 llamadas por IP cada 5 minutos).
- Si una llamada responde 401, renueva el token y reintenta una vez.
- Si responde 429, espera lo que indica Ratelimit-Reset (maximo 60 s) y
  reintenta, hasta 6 intentos en total.
A diferencia de los otros clientes, responder() no levanta por el codigo HTTP:
404, 409, 410 y 422 son respuestas de negocio que decide el procesador.
"""
import threading
import time
from urllib.parse import quote

import httpx

from app.config import FARMA_GROUP, MESSAGING_BASE_URL, MESSAGING_SECRET
from app.farma_client import _jwt_exp

# Generoso: si un 200 lento se corta, el reintento recibe 409 y el orderId se pierde
TIMEOUT_RESPONDER_S = 30

_token: str | None = None
_token_exp: float = 0
_lock = threading.Lock()


def get_token(force: bool = False) -> str:
    global _token, _token_exp
    with _lock:
        if force or _token is None or time.time() > _token_exp - 60:
            r = httpx.post(
                f"{MESSAGING_BASE_URL}/messaging/auth",
                json={"group": FARMA_GROUP, "secret": MESSAGING_SECRET},
                timeout=15,
            )
            r.raise_for_status()
            _token = r.json()["token"]
            _token_exp = _jwt_exp(_token)
        return _token


def _request(method: str, path: str, timeout: float = 15, **kwargs) -> httpx.Response:
    url = f"{MESSAGING_BASE_URL}{path}"
    renovado = forzar = False
    for _ in range(6):
        headers = {"Authorization": "Bearer " + get_token(force=forzar)}
        forzar = False
        r = httpx.request(method, url, headers=headers, timeout=timeout, **kwargs)
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
    return r


def responder(message_id: str, cuerpo: dict) -> tuple[int, dict | None]:
    """POST /messaging/messages/{id}/response. Devuelve (codigo HTTP, cuerpo JSON).
    Levanta httpx.HTTPError solo si no hubo respuesta (red, timeout)."""
    r = _request("POST", f"/messaging/messages/{quote(message_id, safe='')}/response",
                 json=cuerpo, timeout=TIMEOUT_RESPONDER_S)
    try:
        datos = r.json() if r.content else None
    except ValueError:
        datos = {"texto": r.text[:500]}
    return r.status_code, datos
