"""Tests del cliente del sistema de ordenes (sin red)."""
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

import httpx  # noqa: E402

from app import farma_client, ordenes_client  # noqa: E402

BASE = ordenes_client.ORDENES_BASE_URL


def _jwt(exp: float) -> str:
    payload = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).decode().rstrip("=")
    return f"x.{payload}.y"


def _resp(status: int, method: str, url: str, body=None, headers=None) -> httpx.Response:
    return httpx.Response(status, json=body, headers=headers,
                          request=httpx.Request(method, url))


class OrdenesClientTest(unittest.TestCase):
    def setUp(self):
        ordenes_client._token = None
        ordenes_client._token_exp = 0

    def _auth(self, *a, **k):
        return _resp(200, "POST", f"{BASE}/ordenes-compra/autenticar",
                     {"token": _jwt(time.time() + 3600)})

    def test_obtener_usa_bearer_y_cachea_el_token(self):
        url = f"{BASE}/ordenes-compra/ordenes/abc"
        with patch("httpx.post", side_effect=self._auth) as post, \
             patch("httpx.request", return_value=_resp(200, "GET", url, {"id": "abc"})) as req:
            self.assertEqual(ordenes_client.obtener("abc"), {"id": "abc"})
            ordenes_client.obtener("abc")
        self.assertEqual(post.call_count, 1)  # el token se reutiliza
        self.assertTrue(req.call_args.kwargs["headers"]["Authorization"].startswith("Bearer "))

    def test_401_renueva_el_token_una_vez(self):
        url = f"{BASE}/ordenes-compra/ordenes/abc"
        respuestas = [_resp(401, "GET", url), _resp(200, "GET", url, {"id": "abc"})]
        with patch("httpx.post", side_effect=self._auth) as post, \
             patch("httpx.request", side_effect=respuestas):
            self.assertEqual(ordenes_client.obtener("abc"), {"id": "abc"})
        self.assertEqual(post.call_count, 2)

    def test_429_espera_ratelimit_reset_y_reintenta(self):
        url = f"{BASE}/ordenes-compra/ordenes/abc"
        respuestas = [_resp(429, "GET", url, headers={"Ratelimit-Reset": "2"}),
                      _resp(200, "GET", url, {"id": "abc"})]
        with patch("httpx.post", side_effect=self._auth), \
             patch("httpx.request", side_effect=respuestas), \
             patch("time.sleep") as dormir:
            ordenes_client.obtener("abc")
        dormir.assert_called_once_with(3.0)

    def test_actualizar_estado_404_levanta_error(self):
        url = f"{BASE}/ordenes-compra/ordenes/abc/estado"
        with patch("httpx.post", side_effect=self._auth), \
             patch("httpx.request", return_value=_resp(404, "POST", url)):
            with self.assertRaises(httpx.HTTPStatusError):
                ordenes_client.actualizar_estado("abc", "aceptada")

    def test_actualizar_estado_envia_el_estado(self):
        url = f"{BASE}/ordenes-compra/ordenes/abc/estado"
        with patch("httpx.post", side_effect=self._auth), \
             patch("httpx.request", return_value=httpx.Response(
                 204, request=httpx.Request("POST", url))) as req:
            ordenes_client.actualizar_estado("abc", "aceptada")
        self.assertEqual(req.call_args.kwargs["json"], {"estado": "aceptada"})


class DispatchTest(unittest.TestCase):
    def test_dispatch_envia_producto_y_orden(self):
        with patch.object(farma_client, "request", return_value=None) as req:
            farma_client.dispatch("p" * 24, "o" * 24)
        req.assert_called_once_with("POST", "/farma-central/dispatch",
                                    json={"productId": "p" * 24, "orderId": "o" * 24})


if __name__ == "__main__":
    unittest.main()
