"""Cliente del mercado entre distribuidoras (Farma Central /trades).

Mismo patron que ordenes_client:
- Token en memoria, renovado una vez si la llamada responde 401.
- 429 espera Ratelimit-Reset (maximo 60 s) y reintenta, hasta 6 intentos.
- 5xx no es exito: se propaga HTTPStatusError.
- 4xx de negocio (precio, oferta propia, ya cerrada) se devuelve y no se reintenta.

Auth: POST /trades/autenticar con {group, secret}.
Campos reales de una oferta: state, publisher (quien publica) y counterparty
(quien acepta). TRADES_TOKEN_MODE=farma reutiliza el token de Farma Central.
"""
from __future__ import annotations

import threading
import time
from urllib.parse import quote

import httpx

from app.config import (
    FARMA_API_KEY,
    FARMA_GROUP,
    TRADES_AUTH_PATH,
    TRADES_BASE_URL,
    TRADES_TOKEN_MODE,
)
from app.farma_client import _jwt_exp

_token: str | None = None
_token_exp: float = 0.0
_lock = threading.Lock()

_ESTADO_QUERY = {
    "abierta": "open",
    "cerrada": "closed",
    "expirada": "expired",
    "cancelada": "cancelled",
}


class Respuesta:
    def __init__(self, status: int, datos):
        self.status = status
        self.datos = datos
        self.ok = 200 <= status < 300


def get_token(force: bool = False) -> str:
    global _token, _token_exp
    if TRADES_TOKEN_MODE == "farma":
        from app.farma_client import get_token as token_farma
        return token_farma(force=force)
    with _lock:
        if force or _token is None or time.time() > _token_exp - 60:
            r = httpx.post(
                f"{TRADES_BASE_URL}{TRADES_AUTH_PATH}",
                json={"group": FARMA_GROUP, "secret": FARMA_API_KEY},
                timeout=15,
            )
            r.raise_for_status()
            _token = r.json()["token"]
            _token_exp = _jwt_exp(_token)
        return _token


def _llamar(method: str, path: str, **kwargs) -> Respuesta:
    url = f"{TRADES_BASE_URL}{path}"
    renovado = forzar = False
    r = None
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
    assert r is not None
    if r.status_code >= 500:
        r.raise_for_status()
    try:
        datos = r.json() if r.content else None
    except ValueError:
        datos = {"texto": r.text[:500]}
    return Respuesta(r.status_code, datos)


def publicar(side: str, sku: str, quantity: int, unit_price: int) -> Respuesta:
    """POST /trades/offers. El precio ya tiene que estar dentro de la banda."""
    return _llamar("POST", "/trades/offers", json={
        "side": side,
        "sku": sku,
        "quantity": quantity,
        "unitPrice": unit_price,
    })


def cancelar(offer_id: str) -> Respuesta:
    return _llamar("POST", f"/trades/offers/{quote(offer_id, safe='')}/cancel")


def aceptar(offer_id: str) -> Respuesta:
    """Toma la oferta completa. No manda cantidad: el cierre parcial no existe."""
    return _llamar("POST", f"/trades/offers/{quote(offer_id, safe='')}/accept")


def obtener(offer_id: str) -> Respuesta:
    return _llamar("GET", f"/trades/offers/{quote(offer_id, safe='')}")


def listar_ofertas(sku: str | None = None, side: str | None = None,
                   estado: str | None = None) -> list[dict]:
    """Ofertas normalizadas. Filtra en local por si el servidor ignora el query."""
    params = {}
    if sku:
        params["sku"] = sku
    if side:
        params["side"] = side
    if estado:
        params["state"] = _ESTADO_QUERY.get(estado, estado)
    respuesta = _llamar("GET", "/trades/offers", params=params or None)
    if not respuesta.ok:
        raise httpx.HTTPStatusError(
            f"listar ofertas respondio {respuesta.status}",
            request=httpx.Request("GET", f"{TRADES_BASE_URL}/trades/offers"),
            response=httpx.Response(respuesta.status, json=respuesta.datos),
        )
    ofertas = [normalizar(item) for item in _lista(respuesta.datos)]
    if sku:
        ofertas = [o for o in ofertas if o.get("sku") == sku]
    if side:
        ofertas = [o for o in ofertas if o.get("side") == side]
    if estado:
        querido = {"abierta": _ABIERTOS, "cerrada": _CERRADOS,
                   "expirada": _EXPIRADOS, "cancelada": _CANCELADOS}.get(estado)
        if querido is not None:
            ofertas = [o for o in ofertas if o.get("status") in querido]
    return ofertas


def _lista(datos) -> list:
    if isinstance(datos, list):
        return datos
    if isinstance(datos, dict):
        for clave in ("offers", "ofertas", "items", "data"):
            if isinstance(datos.get(clave), list):
                return datos[clave]
    return []


_ABIERTOS = {"open", "abierta", "active", "opened"}
_CERRADOS = {"closed", "cerrada", "accepted", "filled", "completed", "matched"}
_EXPIRADOS = {"expired", "expirada"}
_CANCELADOS = {"cancelled", "canceled", "cancelada"}


def normalizar(raw) -> dict:
    """Unifica los nombres que el enunciado fija y los que la doc podria usar."""
    if not isinstance(raw, dict):
        return {}
    cuerpo = raw
    for clave in ("offer", "oferta"):
        if isinstance(raw.get(clave), dict):
            cuerpo = {**raw, **raw[clave]}
            break
    offer_id = cuerpo.get("offerId") or cuerpo.get("id") or cuerpo.get("_id")
    precio = cuerpo.get("unitPrice", cuerpo.get("unit_price", cuerpo.get("precio")))
    cantidad = cuerpo.get("quantity", cuerpo.get("cantidad"))
    order_id = cuerpo.get("orderId") or cuerpo.get("order_id")
    return {
        "id": None if offer_id is None else str(offer_id),
        "side": str(cuerpo.get("side") or "").lower(),
        "sku": cuerpo.get("sku"),
        "quantity": _entero(cantidad) or 0,
        "unitPrice": _entero(precio),
        "status": str(cuerpo.get("state") or "").lower(),
        "orderId": None if order_id in (None, "") else str(order_id),
        "group": _entero(cuerpo.get("publisher")),          # quien la publico
        "counterparty": _entero(cuerpo.get("counterparty")),  # quien la acepto
    }


def estado_local(status: str | None) -> str | None:
    """Traduce el estado remoto al de la tabla ofertas_mercado. None si sigue abierta
    o si el texto no se reconoce (se vuelve a consultar)."""
    if not status:
        return None
    if status in _ABIERTOS:
        return "abierta"
    if status in _CERRADOS:
        return "cerrada"
    if status in _EXPIRADOS:
        return "expirada"
    if status in _CANCELADOS:
        return "cancelada"
    return None


def _entero(valor) -> int | None:
    if isinstance(valor, bool) or valor is None:
        return None
    if isinstance(valor, int):
        return valor
    if isinstance(valor, float):
        return int(round(valor))
    if isinstance(valor, str):
        texto = valor.strip()
        if texto.lstrip("-").isdigit():
            return int(texto)
    return None

