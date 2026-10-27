"""Tests de la reposicion automatica de kits (sin red ni Postgres)."""
from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://farma:x@localhost/farma")

from app import operaciones, produccion, reposicion  # noqa: E402

CATALOGO = {"KIT-A": {"sellable": True}, "KIT-B": {"sellable": True},
            "API-X": {"sellable": False}}


class FaltantesTest(unittest.TestCase):
    def _faltantes(self, stock, en_camino, comprometido, minimo=3):
        with patch.object(reposicion, "catalogo", return_value=CATALOGO), \
             patch.object(reposicion, "STOCK_EXTRA_PORTAL", 0), \
             patch.object(reposicion.stock, "minimo", return_value=minimo), \
             patch.object(reposicion.stock, "comprometido", side_effect=comprometido.get), \
             patch.object(reposicion.custodia, "stock_disponible", side_effect=stock.get), \
             patch.object(reposicion.custodia, "en_camino", side_effect=en_camino.get):
            return reposicion.faltantes()

    def test_repone_hasta_el_minimo_mas_lo_comprometido(self):
        r = self._faltantes(stock={"KIT-A": 1, "KIT-B": 3}, en_camino={"KIT-A": 0, "KIT-B": 0},
                            comprometido={"KIT-A": 2, "KIT-B": 0})
        self.assertEqual(r, {"KIT-A": 4})  # 3 + 2 - 1; KIT-B ya esta en el minimo

    def test_descuenta_lo_que_viene_en_camino(self):
        r = self._faltantes(stock={"KIT-A": 0, "KIT-B": 3}, en_camino={"KIT-A": 2, "KIT-B": 0},
                            comprometido={"KIT-A": 0, "KIT-B": 0})
        self.assertEqual(r, {"KIT-A": 1})

    def test_solo_kits(self):
        r = self._faltantes(stock={"KIT-A": 3, "KIT-B": 3}, en_camino={"KIT-A": 0, "KIT-B": 0},
                            comprometido={"KIT-A": 0, "KIT-B": 0})
        self.assertEqual(r, {})


class IntentarVueltaTest(unittest.TestCase):
    def test_si_hay_produccion_manual_devuelve_none(self):
        def ocupado():
            raise produccion.ProduccionOcupada("otro proceso")
        with patch.object(produccion, "_candado", side_effect=ocupado):
            self.assertIsNone(produccion.intentar_vuelta({"KIT-A": 1}, {}))

    def test_un_error_dentro_de_la_vuelta_no_se_confunde_con_candado_ocupado(self):
        from contextlib import nullcontext
        with patch.object(produccion, "_candado", return_value=nullcontext()), \
             patch.object(produccion, "una_vuelta", side_effect=RuntimeError("PoW fallo")):
            with self.assertRaises(RuntimeError):
                produccion.intentar_vuelta({"KIT-A": 1}, {})


class ProducirTest(unittest.TestCase):
    def test_pasa_a_una_vuelta_todos_los_kits_con_cero_los_completos(self):
        from contextlib import nullcontext
        llamadas = []

        def vuelta(objetivos, tanda=10, estado=None):
            llamadas.append(dict(objetivos))
            return {"KIT-A": 2} if len(llamadas) == 1 else {"KIT-B": 1}

        cat = {"KIT-A": {"sellable": True}, "KIT-B": {"sellable": True}}
        with patch.object(produccion, "catalogo", return_value=cat), \
             patch.object(produccion, "tamano_lote", return_value=1), \
             patch.object(produccion, "_candado", return_value=nullcontext()), \
             patch.object(produccion, "una_vuelta", side_effect=vuelta), \
             patch.object(produccion, "_despejar"), \
             patch.object(produccion, "_liberar_buffer"), \
             patch.object(produccion.time, "sleep"), \
             patch.object(produccion.custodia, "en_camino", return_value=0):
            r = produccion.producir({"KIT-A": 2, "KIT-B": 1})
        self.assertEqual(llamadas, [{"KIT-A": 2, "KIT-B": 1}, {"KIT-A": 0, "KIT-B": 1}])
        self.assertEqual(r, {"KIT-A": 2, "KIT-B": 1})


class UnidadesPerdidasTest(unittest.TestCase):
    def test_detecta_las_que_farma_no_tiene(self):
        unidades = [SimpleNamespace(id="a", sku="VIA"), SimpleNamespace(id="b", sku="VIA")]
        with patch.object(operaciones.esp, "store_id", return_value="pack"), \
             patch.object(operaciones.farma_client, "space_products", return_value=[{"_id": "a"}]):
            self.assertEqual(operaciones._no_estan_en_farma(unidades), {"b"})


if __name__ == "__main__":
    unittest.main()
