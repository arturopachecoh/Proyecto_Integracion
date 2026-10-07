"""Tests de custodia contra un Postgres desechable (NUNCA el de PROD).

Se saltan si TEST_DATABASE_URL no esta definido. Para correrlos:
  docker run -d --rm --name pg-test -e POSTGRES_USER=farma -e POSTGRES_PASSWORD=x \
    -e POSTGRES_DB=farma -p 127.0.0.1:55432:5432 postgres:16
  export TEST_DATABASE_URL=postgresql+psycopg://farma:x@127.0.0.1:55432/farma
  DATABASE_URL=$TEST_DATABASE_URL alembic upgrade head
  python -m unittest tests/test_custodia_db.py
"""
from __future__ import annotations

import os
import unittest
import uuid
from datetime import datetime, timedelta, timezone

TEST_DB = os.environ.get("TEST_DATABASE_URL")
if TEST_DB:
    os.environ["DATABASE_URL"] = TEST_DB

if TEST_DB:
    from sqlalchemy import select

    from app import custodia, ventas
    from app.db import SessionLocal
    from app.models import Lote, Movimiento, Unidad, Venta


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


@unittest.skipUnless(TEST_DB, "TEST_DATABASE_URL no definido")
class _ConLote(unittest.TestCase):
    def setUp(self):
        self.sufijo = uuid.uuid4().hex[:8]
        with SessionLocal.begin() as s:
            lote = Lote(codigo=f"L-TEST-{self.sufijo}", sku="KIT-TEST", cantidad_inicial=3,
                        origen="produccion")
            s.add(lote)
            s.flush()
            self.lote_id = lote.id

    def _unidad(self, estado: str, vence_en: datetime) -> str:
        uid = f"u-{self.sufijo}-{uuid.uuid4().hex[:6]}"
        with SessionLocal.begin() as s:
            s.add(Unidad(id=uid, lote_id=self.lote_id, sku="KIT-TEST",
                         espacio_actual="bodega", estado=estado, vence_en=vence_en))
        return uid

    def _estado(self, uid: str) -> str:
        with SessionLocal() as s:
            return s.get(Unidad, uid).estado


class VencerExpiradasTest(_ConLote):
    def test_marca_solo_en_stock_vencidas(self):
        vencida = self._unidad("en_stock", _ahora() - timedelta(minutes=5))
        vigente = self._unidad("en_stock", _ahora() + timedelta(hours=5))
        reservada = self._unidad("reservada", _ahora() - timedelta(minutes=5))

        self.assertGreaterEqual(custodia.vencer_expiradas(), 1)

        self.assertEqual(self._estado(vencida), "vencida")
        self.assertEqual(self._estado(vigente), "en_stock")
        self.assertEqual(self._estado(reservada), "reservada")
        with SessionLocal() as s:
            u = s.get(Unidad, vencida)
            self.assertIsNone(u.espacio_actual)
            tipos = list(s.scalars(select(Movimiento.tipo).where(Movimiento.unidad_id == vencida)))
        self.assertEqual(tipos, ["vencimiento"])

    def test_idempotente(self):
        uid = self._unidad("en_stock", _ahora() - timedelta(minutes=1))
        custodia.vencer_expiradas()
        custodia.vencer_expiradas()
        with SessionLocal() as s:
            n = len(list(s.scalars(select(Movimiento).where(Movimiento.unidad_id == uid))))
        self.assertEqual(n, 1)


@unittest.skipUnless(TEST_DB, "TEST_DATABASE_URL no definido")
class ExpirarReservasTest(_ConLote):
    def _venta_reservada(self, hace: timedelta) -> tuple[int, str]:
        uid = self._unidad("en_stock", _ahora() + timedelta(days=1))
        venta_id = custodia.crear_venta("Test", "t@test.cl", 100)
        custodia.asignar_unidades_a_venta(venta_id, [uid])
        with SessionLocal.begin() as s:
            s.get(Venta, venta_id).creada_en = _ahora() - hace
        return venta_id, uid

    def _estado_venta(self, venta_id: int) -> str:
        with SessionLocal() as s:
            return s.get(Venta, venta_id).estado

    def test_cancela_abandonadas_y_libera_stock(self):
        vieja, uid_vieja = self._venta_reservada(timedelta(hours=2))
        nueva, uid_nueva = self._venta_reservada(timedelta(minutes=5))

        expiradas = ventas.expirar_reservas(60)

        self.assertIn(vieja, expiradas)
        self.assertNotIn(nueva, expiradas)
        self.assertEqual(self._estado_venta(vieja), "cancelada")
        self.assertEqual(self._estado(uid_vieja), "en_stock")
        self.assertEqual(self._estado_venta(nueva), "pendiente_pago")
        self.assertEqual(self._estado(uid_nueva), "reservada")

    def test_no_toca_pagadas(self):
        venta_id, uid = self._venta_reservada(timedelta(hours=2))
        custodia.marcar_pago(venta_id, "pagada")
        self.assertNotIn(venta_id, ventas.expirar_reservas(60))
        self.assertEqual(self._estado_venta(venta_id), "pagada")


if __name__ == "__main__":
    unittest.main()
