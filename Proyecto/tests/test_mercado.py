"""Politica de precio, ciclo del mercado y filtro de notificaciones. Sin red."""
from __future__ import annotations

import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://farma:x@localhost/farma")
os.environ.setdefault("FARMA_GROUP", "4")
os.environ.setdefault("FARMA_BASE_URL", "https://dev.example")
os.environ.setdefault("FARMA_API_KEY", "test")

from app.mercado import ciclo, precio  # noqa: E402
from app.mercado.orden import es_notificable  # noqa: E402
from app.retiros import procesamiento  # noqa: E402


AHORA = datetime(2026, 11, 18, 15, 0, tzinfo=timezone.utc)


class PrecioTest(unittest.TestCase):
    def test_banda_y_escalon(self):
        self.assertEqual(precio.banda(10), (5, 15))
        self.assertTrue(precio.dentro_de_banda(8, 10))
        self.assertFalse(precio.dentro_de_banda(4, 10))
        self.assertFalse(precio.dentro_de_banda(16, 10))
        self.assertEqual(precio.siguiente_precio_venta(10, 0), 10)
        self.assertEqual(precio.siguiente_precio_venta(10, 5), 5)
        self.assertEqual(precio.precio_compra(10), 5)

    def test_el_portal_no_importa_el_mercado(self):
        from pathlib import Path
        texto = Path("app/main.py").read_text(encoding="utf-8")
        self.assertNotIn("mercado", texto)
        self.assertNotIn("trades_client", texto)


class NotificacionTest(unittest.TestCase):
    def test_mercado_no_se_notifica_y_sftp_si(self):
        self.assertFalse(es_notificable("mercado"))
        self.assertTrue(es_notificable("sftp"))
        self.assertTrue(es_notificable("pubsub"))
        self.assertTrue(es_notificable("mensajeria"))
        self.assertTrue(es_notificable(None))

    def test_una_entrega_de_mercado_no_entra_a_la_lista_de_aviso(self):
        entregas = [{"orderId": "oc-mercado"}, {"orderId": "oc-sftp"}]

        def canal(oc_id):
            return "mercado" if oc_id == "oc-mercado" else "sftp"

        with patch("app.mercado.orden.canal_de", side_effect=canal):
            avisos = procesamiento._notificables(entregas)
        self.assertEqual(avisos, [{"orderId": "oc-sftp"}])


class CicloTest(unittest.TestCase):
    def _parches(self, stock, listar, hay=None, siguiente=None):
        from unittest.mock import MagicMock
        hay = hay or (lambda sku, side: False)
        aceptar = MagicMock(return_value=True)
        vender = MagicMock(return_value=True)
        stack = [
            patch.object(ciclo.config, "FARMA_GROUP", 4),
            patch.object(ciclo.config, "MERCADO_LOTE", 10),
            patch.object(ciclo.config, "MERCADO_ESPERA_MIN", 30),
            patch.object(ciclo.config, "MERCADO_MAX_REQUESTS", 20),
            patch.object(ciclo.custodia, "stock_disponible", side_effect=stock),
            patch.object(ciclo.custodia, "en_camino", return_value=0),
            patch.object(ciclo.precio, "vigente", return_value=10),
            patch.object(ciclo.registro, "por_refrescar", return_value=[]),
            patch.object(ciclo.registro, "contar_cierres", return_value=(3, 1)),
            patch.object(ciclo.registro, "faltante_desde", return_value=AHORA),
            patch.object(ciclo.registro, "olvidar_faltante"),
            patch.object(ciclo.registro, "hay_abierta", side_effect=hay),
            patch.object(ciclo.registro, "existe", return_value=False),
            patch.object(ciclo.registro, "expiradas_seguidas", return_value=0),
            patch.object(ciclo.trades_client, "listar_ofertas", side_effect=listar),
            patch.object(ciclo.acciones, "reconciliar"),
            patch.object(ciclo.acciones, "aceptar_ajena", aceptar),
            patch.object(ciclo.acciones, "publicar_compra", return_value=True),
            patch.object(ciclo.acciones, "publicar_venta", vender),
            patch.object(ciclo.acciones, "refrescar"),
        ]
        if siguiente is not None:
            stack.append(patch.object(ciclo.precio, "siguiente_precio_venta", return_value=siguiente))
        return stack, aceptar, vender

    def test_acepta_la_oferta_mas_barata_dentro_de_la_banda(self):
        def stock(sku):
            return 0 if sku == "EXC-LACTOSA-DC" else 10

        def listar(sku=None, side=None, estado=None):
            if sku != "EXC-LACTOSA-DC":
                return []
            return [
                self._oferta("cara", 12),
                self._oferta("barata", 8),
                self._oferta("bajo", 4),
            ]

        stack, aceptar, vender = self._parches(stock, listar)
        with self._todos(stack):
            stats = ciclo.tick(AHORA)
        aceptar.assert_called_once()
        self.assertEqual(aceptar.call_args.args[0]["id"], "barata")
        self.assertEqual(stats["aceptadas"], ["barata"])
        vender.assert_not_called()

    def test_no_acepta_de_nuevo_una_oferta_ya_vista(self):
        def listar(sku=None, side=None, estado=None):
            if sku == "EXC-LACTOSA-DC":
                return [self._oferta("barata", 8)]
            return []

        stack, aceptar, _vender = self._parches(lambda sku: 0 if sku == "EXC-LACTOSA-DC" else 10, listar)
        with self._todos(stack), patch.object(ciclo.registro, "existe", return_value=True):
            stats = ciclo.tick(AHORA)
        aceptar.assert_not_called()
        self.assertEqual(stats["aceptadas"], [])

    def test_no_publica_otra_venta_si_ya_hay_una_abierta(self):
        def stock(sku):
            return 100 if sku == "LAM-BLISTER-PVC" else 10

        def hay(sku, side):
            return sku == "LAM-BLISTER-PVC" and side == "sell"

        stack, _aceptar, vender = self._parches(stock, lambda **k: [], hay=hay)
        with self._todos(stack):
            ciclo.tick(AHORA)
        vender.assert_not_called()

    def test_no_publica_fuera_de_banda(self):
        def stock(sku):
            return 100 if sku == "SOB-PAPEL-EST" else 10

        stack, _aceptar, vender = self._parches(stock, lambda **k: [], siguiente=16)
        with self._todos(stack):
            ciclo.tick(AHORA)
        vender.assert_not_called()

    def _oferta(self, offer_id, unit_price):
        return {"id": offer_id, "side": "sell", "sku": "EXC-LACTOSA-DC", "quantity": 10,
                "unitPrice": unit_price, "group": 2, "status": "open"}

    def _todos(self, stack):
        from contextlib import ExitStack
        pila = ExitStack()
        for item in stack:
            pila.enter_context(item)
        return pila


if __name__ == "__main__":
    unittest.main()
