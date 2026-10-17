"""Tests de registrar_llegadas contra un Postgres desechable (NUNCA el de PROD).

Se saltan si TEST_DATABASE_URL no esta definido. Para correrlos:
  docker run -d --rm --name pg-test -e POSTGRES_USER=farma -e POSTGRES_PASSWORD=x \
    -e POSTGRES_DB=farma -p 127.0.0.1:55432:5432 postgres:16
  export TEST_DATABASE_URL=postgresql+psycopg://farma:x@127.0.0.1:55432/farma
  DATABASE_URL=$TEST_DATABASE_URL alembic upgrade head
  python -m unittest tests/test_llegadas_db.py
"""
from __future__ import annotations

import os
import unittest
import uuid
from datetime import datetime, timedelta, timezone

TEST_DB = os.environ.get("TEST_DATABASE_URL")
if TEST_DB:
    os.environ["DATABASE_URL"] = TEST_DB

    from sqlalchemy import select

    from app import custodia
    from app.db import SessionLocal
    from app.models import Lote, Movimiento, Solicitud, Unidad


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


@unittest.skipUnless(TEST_DB, "TEST_DATABASE_URL no definido")
class LlegadaSinSolicitudTest(unittest.TestCase):
    def setUp(self):
        # SKU y lote unicos por test: la base de prueba puede tener datos de antes
        self.sufijo = uuid.uuid4().hex[:8]
        self.sku = f"KIT-TEST-{self.sufijo}"
        self.codigo = f"L-TEST-{self.sufijo}"

    def _productos(self, n: int, desde: int = 0) -> list[dict]:
        vence = (_ahora() + timedelta(days=10)).isoformat()
        return [{"_id": f"u-{self.sufijo}-{i}", "sku": self.sku, "batch": self.codigo,
                 "expiresAt": vence} for i in range(desde, desde + n)]

    def _lote(self) -> Lote | None:
        with SessionLocal() as s:
            return s.scalar(select(Lote).where(Lote.codigo == self.codigo))

    def test_lote_sin_solicitud_se_recibe_y_es_vendible(self):
        n = custodia.registrar_llegadas(self._productos(5), "bodega")

        self.assertEqual(n, 5)
        lote = self._lote()
        self.assertEqual(lote.origen, "farma_central")
        self.assertIsNone(lote.solicitud_id)
        self.assertEqual(lote.cantidad_inicial, 5)
        self.assertEqual(custodia.stock_disponible(self.sku), 5)
        with SessionLocal() as s:
            tipos = set(s.scalars(select(Movimiento.tipo).where(Movimiento.lote_id == lote.id)))
        self.assertEqual(tipos, {"recepcion"})

    def test_llega_en_partes_e_idempotente(self):
        custodia.registrar_llegadas(self._productos(3), "bodega")
        custodia.registrar_llegadas(self._productos(5), "bodega")  # 3 repetidas + 2 nuevas

        self.assertEqual(self._lote().cantidad_inicial, 5)
        self.assertEqual(custodia.stock_disponible(self.sku), 5)

    def test_espera_si_hay_solicitud_pendiente_futura(self):
        # Una fabricacion propia que Farma muestra antes de su hora: no se registra aun
        with SessionLocal.begin() as s:
            s.add(Solicitud(tipo="fabricacion", sku=self.sku, cantidad=5,
                            llega_en=_ahora() + timedelta(hours=1)))

        self.assertEqual(custodia.registrar_llegadas(self._productos(5), "packaging"), 0)
        self.assertIsNone(self._lote())

    def test_con_solicitud_que_calza_sigue_igual(self):
        with SessionLocal.begin() as s:
            sol = Solicitud(tipo="compra", sku=self.sku, cantidad=5,
                            llega_en=_ahora() - timedelta(minutes=1))
            s.add(sol)
            s.flush()
            sol_id = sol.id

        custodia.registrar_llegadas(self._productos(5), "checkIn")

        lote = self._lote()
        self.assertEqual(lote.solicitud_id, sol_id)
        self.assertEqual(lote.cantidad_inicial, 5)
        with SessionLocal() as s:
            self.assertEqual(s.get(Solicitud, sol_id).estado, "recibida")
            self.assertEqual(len(list(s.scalars(
                select(Unidad).where(Unidad.lote_id == lote.id)))), 5)


if __name__ == "__main__":
    unittest.main()
