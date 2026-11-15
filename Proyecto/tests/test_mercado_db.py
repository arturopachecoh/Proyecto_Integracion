"""Custodia de mercado y OC contra un Postgres desechable (NUNCA el de prod).

Se saltan si TEST_DATABASE_URL no esta definido. La base tiene que tener
`alembic upgrade head` de esta rama (incluye e3d1a0mercado).
"""
from __future__ import annotations

import os
import unittest
import uuid
from datetime import datetime, timedelta, timezone

TEST_DB = os.environ.get("TEST_DATABASE_URL")
if TEST_DB:
    os.environ["DATABASE_URL"] = TEST_DB
    os.environ.setdefault("FARMA_GROUP", "4")

    from sqlalchemy import func, select

    from app import custodia
    from app.db import SessionLocal
    from app.mercado import orden, registro
    from app.mercado.modelos import OfertaMercado
    from app.models import Lote, OrdenCompra, Unidad, Venta
    from app.retiros import investigacion, procesamiento


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


@unittest.skipUnless(TEST_DB, "TEST_DATABASE_URL no definido")
class MercadoDbTest(unittest.TestCase):
    def setUp(self):
        self.sufijo = uuid.uuid4().hex[:8]
        self.sku = f"EXC-TEST-{self.sufijo}"
        self.codigo = f"L-MERC-{self.sufijo}"

    def _llegada(self, n: int) -> list[str]:
        vence = (_ahora() + timedelta(days=10)).isoformat()
        productos = [{"_id": f"u-{self.sufijo}-{i}", "sku": self.sku, "batch": self.codigo,
                      "expiresAt": vence} for i in range(n)]
        custodia.registrar_llegadas(productos, "bodega")
        return [p["_id"] for p in productos]

    def test_apartar_dos_deja_el_resto_vendible_y_liberar_las_devuelve(self):
        ids = self._llegada(5)
        self.assertEqual(custodia.stock_disponible(self.sku), 5)
        registro.crear(f"off-{self.sufijo}", "sell", self.sku, 2, 10, "abierta", "vendedor")
        custodia.apartar_para_oferta(f"off-{self.sufijo}", ids[:2])
        self.assertEqual(custodia.stock_disponible(self.sku), 3)
        self.assertEqual(len(custodia.unidades_disponibles(self.sku)), 3)
        custodia.liberar_oferta(f"off-{self.sufijo}")
        self.assertEqual(custodia.stock_disponible(self.sku), 5)

    def test_no_aparta_una_unidad_ya_reservada_por_una_oc(self):
        ids = self._llegada(2)
        venta = custodia.crear_venta("Cliente", None, 0, estado="orden_compra")
        custodia.asignar_unidades_a_venta(venta, [ids[0]])
        registro.crear(f"off-{self.sufijo}", "sell", self.sku, 1, 10, "abierta", "vendedor")
        with self.assertRaises(ValueError):
            custodia.apartar_para_oferta(f"off-{self.sufijo}", [ids[0]])
        self.assertEqual(custodia.ids_de_oferta(f"off-{self.sufijo}"), [])

    def test_oc_de_mercado_se_inserta_una_sola_vez(self):
        order_id = f"oc-{self.sufijo}"
        self.assertTrue(orden.registrar(order_id, self.sku, 10, 6, 2, "vendedor", offer_id="off"))
        self.assertFalse(orden.registrar(order_id, self.sku, 10, 6, 2, "vendedor", offer_id="off"))
        with SessionLocal() as s:
            oc = s.get(OrdenCompra, order_id)
            self.assertEqual((oc.canal, oc.estado, oc.decision["rol"]), ("mercado", "cumplida", "vendedor"))
            n = s.scalar(select(func.count()).select_from(OrdenCompra).where(OrdenCompra.id == order_id))
        self.assertEqual(n, 1)

    def test_compra_de_mercado_deja_el_lote_encontrable(self):
        registro.crear(
            f"buy-{self.sufijo}", "buy", self.sku, 5, 6, "cerrada", "comprador", contraparte=2,
        )
        self._llegada(2)
        with SessionLocal() as s:
            lote = s.query(Lote).filter(Lote.codigo == self.codigo).one()
            self.assertEqual(lote.origen, "distribuidora")
            self.assertEqual(lote.origen_grupo, 2)
            self.assertEqual(lote.lote_proveedor, self.codigo)
        inv = investigacion.investigar(self.codigo)
        self.assertEqual(len(inv["en_stock"]), 2)

    def test_venta_de_mercado_queda_despachada_y_no_se_vuelve_a_contar(self):
        ids = self._llegada(2)
        offer = f"sell-{self.sufijo}"
        order_id = f"ocv-{self.sufijo}"
        registro.crear(offer, "sell", self.sku, 2, 6, "abierta", "vendedor", contraparte=3)
        custodia.apartar_para_oferta(offer, ids)
        venta_id = custodia.cerrar_venta_mercado(ids, self.sku, 2, 6, order_id, 3)
        otra = custodia.cerrar_venta_mercado(ids, self.sku, 2, 6, order_id, 3)
        self.assertEqual(venta_id, otra)
        self.assertEqual(custodia.stock_disponible(self.sku), 0)
        with SessionLocal() as s:
            venta = s.get(Venta, venta_id)
            self.assertEqual(venta.canal, "mercado")
            unidad = s.get(Unidad, ids[0])
            self.assertEqual(unidad.estado, "despachada")
            oferta = s.get(OfertaMercado, offer)
            self.assertIsNotNone(oferta)
        orden.registrar(order_id, self.sku, 2, 6, 3, "vendedor", venta_id, offer)
        inv = investigacion.investigar(self.codigo)
        self.assertEqual([e["orderId"] for e in inv["entregas"]], [order_id])
        self.assertEqual(procesamiento._notificables(inv["entregas"]), [])

    def test_un_lote_que_no_paso_se_reporta_vacio_sin_error(self):
        codigo = f"NO-EXISTE-{self.sufijo}"
        with self.assertLogs("retiros", level="INFO") as logs:
            inv = investigacion.investigar(codigo)
        self.assertEqual(inv["en_stock"], [])
        self.assertEqual(inv["entregas"], [])
        self.assertTrue(any("no paso por esta distribuidora" in linea for linea in logs.output))
        self.assertFalse(any(linea.startswith("ERROR:") for linea in logs.output))


if __name__ == "__main__":
    unittest.main()
