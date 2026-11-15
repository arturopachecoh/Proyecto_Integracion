"""Escasez de la Entrega 3: sin red y sin Postgres."""
from __future__ import annotations

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://farma:x@localhost/farma")
os.environ.setdefault("FARMA_GROUP", "4")
os.environ.setdefault("FARMA_BASE_URL", "https://dev.example")
os.environ.setdefault("FARMA_API_KEY", "test")

from app import config, operaciones  # noqa: E402
from app.mercado.escasez import (  # noqa: E402
    InsumoNoDisponible,
    debe_conseguir_en_mercado,
    puede_comprar_en_farma,
    puede_revender,
)


class EscasezTest(unittest.TestCase):
    def test_grupo_4_no_compra_los_cuatro_que_farma_rechaza(self):
        for sku in ("EXC-LACTOSA-DC", "FRA-VIDRIO-120", "VIA-VIDRIO-10", "EXC-JARABE-BASE"):
            self.assertFalse(puede_comprar_en_farma(sku, 4), sku)

    def test_grupo_4_si_compra_los_tres_suyos(self):
        for sku in ("LAM-BLISTER-PVC", "EXC-SUERO-FISIO", "SOB-PAPEL-EST"):
            self.assertTrue(puede_comprar_en_farma(sku, 4), sku)

    def test_un_insumo_que_no_es_critico_sigue_libre(self):
        self.assertTrue(puede_comprar_en_farma("API-AMOXI-500", 4))
        self.assertTrue(puede_comprar_en_farma("API-AMOXI-500", 1))

    def test_la_tabla_no_esta_clavada_solo_en_el_grupo_4(self):
        self.assertEqual(
            debe_conseguir_en_mercado(4),
            ["EXC-JARABE-BASE", "EXC-LACTOSA-DC", "FRA-VIDRIO-120", "VIA-VIDRIO-10"],
        )
        self.assertEqual(
            puede_revender(1),
            ["EXC-JARABE-BASE", "EXC-LACTOSA-DC", "VIA-VIDRIO-10"],
        )
        self.assertFalse(puede_comprar_en_farma("LAM-BLISTER-PVC", 1))

    def test_comprar_lactosa_no_llama_a_farma(self):
        with patch.object(config, "FARMA_GROUP", 4), \
             patch.object(operaciones, "catalogo", side_effect=AssertionError("catalogo")), \
             patch.object(operaciones, "_pedir_con_pow", side_effect=AssertionError("pow")):
            with self.assertRaises(InsumoNoDisponible):
                operaciones.comprar("EXC-LACTOSA-DC", 10)

    def test_comprar_blister_sigue_el_camino_actual(self):
        catalogo = {"LAM-BLISTER-PVC": {"components": [], "production": {"batch": 1}}}
        with patch.object(config, "FARMA_GROUP", 4), \
             patch.object(operaciones, "catalogo", return_value=catalogo), \
             patch.object(operaciones, "_pedir_con_pow",
                          return_value=({"availableAt": "2026-11-18T12:00:00Z"}, "ch")) as pedir, \
             patch.object(operaciones.custodia, "registrar_compra", return_value=7) as alta:
            self.assertEqual(operaciones.comprar("LAM-BLISTER-PVC", 1), 7)
        pedir.assert_called_once()
        alta.assert_called_once()


if __name__ == "__main__":
    unittest.main()
