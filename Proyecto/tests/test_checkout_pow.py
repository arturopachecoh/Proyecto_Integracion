"""Tests del adapter Integrapay y del solver PoW (sin red ni Postgres)."""
from __future__ import annotations

import hashlib
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://farma:x@localhost/farma")
os.environ["CHECKOUT_MODE"] = "mock"
os.environ["CHECKOUT_BASE_URL"] = "https://dev.proyecto.2026-2.tallerdeintegracion.cl"
os.environ["PUBLIC_BASE_URL"] = "http://localhost:3000"
os.environ["FARMA_GROUP"] = "4"
os.environ["FARMA_API_KEY"] = "test-secret"

from app.integrations import checkout  # noqa: E402
from app.pow import _reference_leading_zero_bits, leading_zero_bits, solve  # noqa: E402
from app.ventas import normalizar_resultado  # noqa: E402


class PowTest(unittest.TestCase):
    def test_enunciado_leading_zero_bits(self):
        nonce = solve("test-prefix", 12, max_seconds=30)
        self.assertIsNotNone(nonce)
        digest = hashlib.sha256(f"test-prefix:{nonce}".encode()).digest()
        self.assertGreaterEqual(leading_zero_bits(digest), 12)
        self.assertGreaterEqual(_reference_leading_zero_bits(digest.hex()), 12)

    def test_hash_concatena_prefix_colon_nonce(self):
        # Regla Anexo 4: sha256(prefix + ":" + nonce)
        h = hashlib.sha256(b"abc:0").hexdigest()
        self.assertEqual(_reference_leading_zero_bits(h), leading_zero_bits(bytes.fromhex(h)))


class CheckoutMockTest(unittest.TestCase):
    def test_mock_no_llama_red(self):
        with patch.object(checkout, "CHECKOUT_MODE", "mock"):
            tx = checkout.crear_transaccion(9990, 42, {
                "success": "http://localhost:3000/pago/exito?venta=42",
                "error": "http://localhost:3000/pago/error?venta=42",
                "cancelled": "http://localhost:3000/pago/cancelado?venta=42",
            })
        self.assertTrue(tx["redirect_url"].endswith("/api/checkout/mock/42"))
        self.assertEqual(tx["status"], "PENDING")

    def test_force_exito(self):
        with patch.object(checkout, "CHECKOUT_FORCE", "exito"):
            self.assertEqual(checkout.resultado_mock(), "exito")

    def test_integrapay_payload(self):
        urls = {
            "success": "https://x/pago/exito?venta=7",
            "error": "https://x/pago/error?venta=7",
            "cancelled": "https://x/pago/cancelado?venta=7",
        }

        class FakeResp:
            status_code = 201

            def raise_for_status(self):
                return None

            def json(self):
                return {"payment_id": "pay-1", "redirect_url": "https://pay.example/checkout/pay-1"}

        posts = []

        def fake_post(url, **kwargs):
            posts.append((url, kwargs))
            if url.endswith("/payments/auth"):
                class Auth:
                    status_code = 200

                    def raise_for_status(self):
                        return None

                    def json(self):
                        # header.payload.sig — payload {"exp": 9999999999}
                        return {"success": True, "token": "eyJhbGciOiJIUzI1NiJ9.eyJleHAiOjk5OTk5OTk5OTl9.x"}
                return Auth()
            return FakeResp()

        with patch.object(checkout, "CHECKOUT_MODE", "real"), \
             patch.object(checkout, "CHECKOUT_BASE_URL", "https://dev.example"), \
             patch.object(checkout, "CHECKOUT_GROUP", 4), \
             patch.object(checkout, "CHECKOUT_SECRET", "secret"), \
             patch.object(checkout, "_token", None), \
             patch.object(checkout, "_token_exp", 0), \
             patch("app.integrations.checkout.httpx.post", side_effect=fake_post):
            tx = checkout.crear_transaccion(5450, 7, urls)

        self.assertEqual(tx["id"], "pay-1")
        self.assertIn("/payments/auth", posts[0][0])
        self.assertEqual(posts[0][1]["json"], {"group": 4, "secret": "secret"})
        self.assertIn("/payments/init", posts[1][0])
        body = posts[1][1]["json"]
        self.assertEqual(body["amount"], 5450)
        self.assertEqual(body["group"], 4)
        self.assertEqual(set(body["backUrls"]), {"success", "error", "cancelled"})
        self.assertTrue(posts[1][1]["headers"]["Authorization"].startswith("Bearer "))


class ResultadoAliasesTest(unittest.TestCase):
    def test_integrapay_cancelled(self):
        self.assertEqual(normalizar_resultado("cancelled"), "cancelado")
        self.assertEqual(normalizar_resultado("success"), "exito")
        self.assertIsNone(normalizar_resultado("pending"))


if __name__ == "__main__":
    unittest.main()
