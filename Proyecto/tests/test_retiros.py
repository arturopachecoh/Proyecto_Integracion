"""Tests del webhook de retiros sin Postgres: autenticacion y validacion del aviso."""
from __future__ import annotations

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://farma:x@localhost/farma")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import oidc  # noqa: E402
from app.retiros import webhook  # noqa: E402

AVISO = {
    "recallId": "rcl_6721a0b3",
    "batch": "L-EXCLACTOSA-261026-3B9C",
    "sku": "EXC-LACTOSA-DC",
    "reason": "Contaminacion detectada por el proveedor",
    "issuedAt": "2026-10-28T14:12:00Z",
    "deadline": "2026-10-28T14:42:00Z",
}


def _cliente() -> TestClient:
    app = FastAPI()
    app.include_router(webhook.router)
    return TestClient(app)


class WebhookTest(unittest.TestCase):
    def test_sin_token_responde_401_y_no_registra(self):
        with patch.object(webhook.oidc, "verificar",
                          side_effect=oidc.TokenInvalido("falta el token Bearer")), \
                patch.object(webhook.registro, "recibir") as recibir:
            r = _cliente().post("/api/recalls", json=AVISO)
        self.assertEqual(r.status_code, 401)
        recibir.assert_not_called()

    def test_verifica_la_audiencia_exacta(self):
        with patch.object(webhook.oidc, "verificar", return_value={}) as verificar, \
                patch.object(webhook.registro, "recibir", return_value=True):
            r = _cliente().post("/api/recalls", json=AVISO,
                                headers={"Authorization": "Bearer x"})
        self.assertEqual(r.status_code, 200)
        args = verificar.call_args.args
        self.assertEqual(args[0], "Bearer x")
        self.assertTrue(args[1].endswith("/api/recalls"))

    def test_aviso_valido_se_registra(self):
        with patch.object(webhook.oidc, "verificar", return_value={}), \
                patch.object(webhook.registro, "recibir", return_value=True) as recibir:
            r = _cliente().post("/api/recalls", json=AVISO,
                                headers={"Authorization": "Bearer x"})
        self.assertEqual(r.status_code, 200)
        aviso = recibir.call_args.args[0]
        self.assertEqual(aviso["id"], "rcl_6721a0b3")
        self.assertEqual(aviso["lote"], "L-EXCLACTOSA-261026-3B9C")
        self.assertEqual(aviso["plazo"].isoformat(), "2026-10-28T14:42:00+00:00")

    def test_sin_deadline_el_plazo_son_30_minutos(self):
        cuerpo = {k: v for k, v in AVISO.items() if k != "deadline"}
        with patch.object(webhook.oidc, "verificar", return_value={}), \
                patch.object(webhook.registro, "recibir", return_value=True) as recibir:
            _cliente().post("/api/recalls", json=cuerpo, headers={"Authorization": "Bearer x"})
        self.assertEqual(recibir.call_args.args[0]["plazo"].isoformat(),
                         "2026-10-28T14:42:00+00:00")

    def test_aviso_sin_lote_responde_400(self):
        cuerpo = {k: v for k, v in AVISO.items() if k != "batch"}
        with patch.object(webhook.oidc, "verificar", return_value={}), \
                patch.object(webhook.registro, "recibir") as recibir:
            r = _cliente().post("/api/recalls", json=cuerpo,
                                headers={"Authorization": "Bearer x"})
        self.assertEqual(r.status_code, 400)
        recibir.assert_not_called()

    def test_aviso_repetido_tambien_responde_200(self):
        with patch.object(webhook.oidc, "verificar", return_value={}), \
                patch.object(webhook.registro, "recibir", return_value=False):
            r = _cliente().post("/api/recalls", json=AVISO,
                                headers={"Authorization": "Bearer x"})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()["nuevo"])


if __name__ == "__main__":
    unittest.main()
