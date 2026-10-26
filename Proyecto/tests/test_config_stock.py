"""Tests de los minimos de stock por kit (sin red ni Postgres)."""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://farma:x@localhost/farma")

from app import stock  # noqa: E402


class MinimosTest(unittest.TestCase):
    def test_vacio_no_tiene_excepciones(self):
        self.assertEqual(stock.parsear_minimos(""), {})

    def test_lee_pares_sku_cantidad(self):
        self.assertEqual(
            stock.parsear_minimos("KIT-DIABETES=2, KIT-GASTRO=4"),
            {"KIT-DIABETES": 2, "KIT-GASTRO": 4},
        )

    def test_rechaza_formato_malo(self):
        for malo in ("KIT-DIABETES", "KIT-DIABETES=dos", "=3", "KIT-A=-1"):
            with self.subTest(malo=malo), self.assertRaises(ValueError):
                stock.parsear_minimos(malo)

    def test_minimo_usa_el_default_si_no_hay_excepcion(self):
        self.assertEqual(stock.minimo("KIT-QUE-NO-ESTA"), stock.STOCK_MINIMO_DEFAULT)


if __name__ == "__main__":
    unittest.main()
