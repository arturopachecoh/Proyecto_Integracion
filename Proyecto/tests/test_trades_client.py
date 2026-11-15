"""Cliente /trades sin red."""
from __future__ import annotations

import base64
import json
import os
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://farma:x@localhost/farma")
os.environ.setdefault("FARMA_BASE_URL", "https://dev.example")
os.environ.setdefault("FARMA_GROUP", "4")
os.environ.setdefault("FARMA_API_KEY", "test-secret")
os.environ.setdefault("TRADES_TOKEN_MODE", "propio")

import httpx  # noqa: E402

from app import trades_client  # noqa: E402

BASE = trades_client.TRADES_BASE_URL


def _jwt(exp: float) -> str:
    payload = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).decode().rstrip("=")
    return f"x.{payload}.y"


def _resp(status: int, method: str, url: str, body=None, headers=None) -> httpx.Response:
    return httpx.Response(status, json=body, headers=headers, request=httpx.Request(method, url))


class TradesClientTest(unittest.TestCase):
    def setUp(self):
        trades_client._token = None
        trades_client._token_exp = 0

    def _auth(self, *a, **k):
        return _resp(200, "POST", f"{BASE}/trades/auth", {"token": _jwt(time.time() + 3600)})

    def test_401_renueva_el_token_una_vez(self):
        url = f"{BASE}/trades/offers"
        respuestas = [_resp(401, "GET", url), _resp(200, "GET", url, {"offers": []})]
        with patch("httpx.post", side_effect=self._auth) as post, \
             patch("httpx.request", side_effect=respuestas):
            self.assertEqual(trades_client.listar_ofertas(), [])
        self.assertEqual(post.call_count, 2)

    def test_429_espera_y_reintenta(self):
        url = f"{BASE}/trades/offers/abc"
        respuestas = [
            _resp(429, "GET", url, headers={"Ratelimit-Reset": "2"}),
            _resp(200, "GET", url, {"id": "abc", "status": "open"}),
        ]
        with patch("httpx.post", side_effect=self._auth), \
             patch("httpx.request", side_effect=respuestas), \
             patch("time.sleep") as dormir:
            trades_client.obtener("abc")
        dormir.assert_called_once_with(3.0)

    def test_aceptar_no_manda_cantidad(self):
        url = f"{BASE}/trades/offers/off-1/accept"
        with patch("httpx.post", side_effect=self._auth), \
             patch("httpx.request", return_value=_resp(200, "POST", url, {"id": "off-1"})) as req:
            respuesta = trades_client.aceptar("off-1")
        self.assertTrue(respuesta.ok)
        self.assertNotIn("json", req.call_args.kwargs)
        self.assertTrue(req.call_args.args[1].endswith("/trades/offers/off-1/accept"))

    def test_500_no_es_exito(self):
        url = f"{BASE}/trades/offers"
        with patch("httpx.post", side_effect=self._auth), \
             patch("httpx.request", return_value=_resp(500, "POST", url, {"error": "x"})):
            with self.assertRaises(httpx.HTTPStatusError):
                trades_client.publicar("sell", "EXC-LACTOSA-DC", 10, 6)

    def test_normaliza_nombres_distintos(self):
        oferta = trades_client.normalizar(
            {"offerId": "abc", "side": "sell", "sku": "EXC-LACTOSA-DC",
             "quantity": "10", "unitPrice": 6, "status": "open", "sellerGroup": "2",
             "orderId": "oc-1"}
        )
        self.assertEqual(oferta["id"], "abc")
        self.assertEqual(oferta["quantity"], 10)
        self.assertEqual(oferta["unitPrice"], 6)
        self.assertEqual(oferta["group"], 2)
        self.assertEqual(oferta["orderId"], "oc-1")
        self.assertEqual(trades_client.estado_local("open"), "abierta")
        self.assertEqual(trades_client.estado_local("accepted"), "cerrada")


if __name__ == "__main__":
    unittest.main()
