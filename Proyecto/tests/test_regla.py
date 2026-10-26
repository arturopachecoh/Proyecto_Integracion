"""Tests de la regla B de aceptacion de OC (sin red ni Postgres)."""
from __future__ import annotations

import os
import unittest
from datetime import datetime, timedelta, timezone

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://farma:x@localhost/farma")
os.environ.setdefault("FARMA_GROUP", "4")

from app.pedidos import regla  # noqa: E402

AHORA = datetime(2026, 10, 27, 15, 0, tzinfo=timezone.utc)


def _ev(cantidad, stock, en_camino=0, comprometido=0):
    return regla.Evaluacion(sku="KIT-X", cantidad=cantidad, stock=stock,
                            en_camino=en_camino, comprometido=comprometido)


class EvaluacionTest(unittest.TestCase):
    def test_stock_justo_acepta_y_reserva_todo(self):
        ev = _ev(cantidad=2, stock=2)
        self.assertTrue(ev.acepta)
        self.assertEqual(ev.reservar_ahora, 2)

    def test_produccion_en_camino_completa_lo_que_falta(self):
        ev = _ev(cantidad=2, stock=1, en_camino=1)
        self.assertTrue(ev.acepta)
        self.assertEqual(ev.reservar_ahora, 1)

    def test_lo_comprometido_no_se_cuenta_dos_veces(self):
        # Un kit en camino ya prometido a otra OC no sirve para esta
        self.assertFalse(_ev(cantidad=1, stock=0, en_camino=1, comprometido=1).acepta)

    def test_no_reserva_stock_prometido_a_oc_anteriores(self):
        ev = _ev(cantidad=2, stock=2, en_camino=2, comprometido=2)
        self.assertTrue(ev.acepta)
        self.assertEqual(ev.reservar_ahora, 0)

    def test_como_dict_guarda_los_numeros_y_la_decision(self):
        d = _ev(cantidad=2, stock=1).como_dict()
        self.assertEqual((d["stock"], d["disponible"], d["acepta"]), (1, 1, False))


class ValidarOcTest(unittest.TestCase):
    def _oc(self, **cambios):
        oc = {"proveedor": "4", "estado": "creada", "sku": "KIT-X", "cantidad": 1,
              "vencimiento": (AHORA + timedelta(hours=2)).isoformat()}
        oc.update(cambios)
        return oc

    def _validar(self, oc):
        return regla.validar_oc(oc, AHORA, es_kit=lambda sku: sku == "KIT-X")

    def test_oc_valida(self):
        self.assertEqual(self._validar(self._oc()), (None, None))

    def test_de_otro_proveedor_se_descarta(self):
        self.assertEqual(self._validar(self._oc(proveedor="7"))[0], "descartar")

    def test_ya_no_creada_se_descarta(self):
        self.assertEqual(self._validar(self._oc(estado="vencida"))[0], "descartar")

    def test_sku_que_no_es_kit_se_rechaza(self):
        self.assertEqual(self._validar(self._oc(sku="API-AMOXI-500"))[0], "rechazar")

    def test_cantidad_invalida_se_rechaza(self):
        self.assertEqual(self._validar(self._oc(cantidad=0))[0], "rechazar")

    def test_plazo_menor_al_margen_se_rechaza(self):
        vence = (AHORA + timedelta(minutes=10)).isoformat()
        self.assertEqual(self._validar(self._oc(vencimiento=vence))[0], "rechazar")

    def test_vencimiento_sin_zona_horaria_se_toma_como_utc(self):
        vence = (AHORA + timedelta(hours=2)).replace(tzinfo=None).isoformat()
        self.assertEqual(self._validar(self._oc(vencimiento=vence)), (None, None))
        self.assertEqual(regla._fecha(vence), AHORA + timedelta(hours=2))


if __name__ == "__main__":
    unittest.main()
