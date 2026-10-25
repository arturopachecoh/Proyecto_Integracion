"""Tests de pedidos (OC) contra un Postgres desechable (NUNCA el de PROD).

Se saltan si TEST_DATABASE_URL no esta definido. Ver docs/05 para correrlos.
"""
from __future__ import annotations

import os
import unittest
import uuid
from datetime import datetime, timedelta, timezone

TEST_DB = os.environ.get("TEST_DATABASE_URL")
if TEST_DB:
    os.environ["DATABASE_URL"] = TEST_DB
    os.environ.setdefault("FARMA_GROUP", "4")  # las OC de prueba son para el grupo 4

    from sqlalchemy import select, update
    from sqlalchemy.exc import IntegrityError

    from unittest.mock import patch

    from app import custodia, salud, stock
    from app.db import SessionLocal
    from app.models import OrdenCompra, Solicitud, Unidad, Venta
    import httpx

    from app.pedidos import bandeja, conciliador, despachador, procesador


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _oc_id() -> str:
    return uuid.uuid4().hex[:24]


class BaseDB(unittest.TestCase):
    """SKU unico por test: la base de prueba puede tener datos de antes."""

    def setUp(self):
        self.sufijo = uuid.uuid4().hex[:8]
        self.sku = f"KIT-TEST-{self.sufijo}"
        if TEST_DB:
            # Los procesos recorren todas las OC activas: se cierran las de tests anteriores
            with SessionLocal.begin() as s:
                s.execute(update(OrdenCompra)
                          .where(OrdenCompra.estado.in_(
                              ("nueva", "aceptando", "rechazando", "aceptada")))
                          .values(estado="descartada"))

    def sembrar(self, n: int, espacio: str = "bodega") -> list[str]:
        """Registra n unidades vendibles del kit de prueba y devuelve sus ids."""
        vence = (_ahora() + timedelta(days=10)).isoformat()
        productos = [{"_id": uuid.uuid4().hex[:24], "sku": self.sku,
                      "batch": f"L-TEST-{self.sufijo}", "expiresAt": vence} for _ in range(n)]
        custodia.registrar_llegadas(productos, espacio)
        return [p["_id"] for p in productos]

    def aceptada(self, cantidad: int, vence_en: timedelta = timedelta(hours=2)) -> str:
        """Una OC ya aceptada en el sistema de ordenes, con su Venta y sin unidades."""
        oc_id = _oc_id()
        bandeja.recibir(oc_id, "pubsub", "msg")
        bandeja.guardar_detalle(oc_id, self.oc_remota(oc_id, cantidad=cantidad, vence_en=vence_en))
        bandeja.reclamar(oc_id, "nueva", "aceptada", {"precio_unitario": 1500})
        procesador.asegurar_venta(oc_id)
        return oc_id

    def oc_remota(self, oc_id: str, cantidad: int = 1, estado: str = "creada",
                  vence_en: timedelta = timedelta(hours=2), despachado: int = 0) -> dict:
        """Una OC como la devuelve GET /ordenes-compra/ordenes/{id}."""
        return {"id": oc_id, "cliente": "9", "proveedor": "4", "sku": self.sku,
                "cantidad": cantidad, "despachado": despachado, "precioUnitario": 1500,
                "nombreCliente": "", "estado": estado,
                "vencimiento": (_ahora() + vence_en).isoformat()}


@unittest.skipUnless(TEST_DB, "TEST_DATABASE_URL no definido")
class ModeloTest(BaseDB):
    def test_oc_repetida_viola_la_clave_primaria(self):
        oc_id = _oc_id()
        with SessionLocal.begin() as s:
            s.add(OrdenCompra(id=oc_id, canal="sftp", estado="nueva"))
        with self.assertRaises(IntegrityError):
            with SessionLocal.begin() as s:
                s.add(OrdenCompra(id=oc_id, canal="pubsub", estado="nueva"))

    def test_venta_acepta_estado_orden_compra(self):
        venta_id = custodia.crear_venta("Cliente", None, 0, canal="sftp",
                                        orden_externa_id=_oc_id(), estado="orden_compra")
        with SessionLocal() as s:
            self.assertEqual(s.get(Venta, venta_id).estado, "orden_compra")


@unittest.skipUnless(TEST_DB, "TEST_DATABASE_URL no definido")
class StockTest(BaseDB):
    def _oc_aceptada(self, cantidad: int, asignar: list[str]) -> str:
        oc_id = _oc_id()
        venta_id = custodia.crear_venta("C", None, 0, canal="sftp",
                                        orden_externa_id=oc_id, estado="orden_compra")
        if asignar:
            custodia.asignar_unidades_a_venta(venta_id, asignar)
        with SessionLocal.begin() as s:
            s.add(OrdenCompra(id=oc_id, canal="sftp", estado="aceptada", sku=self.sku,
                              cantidad=cantidad, venta_id=venta_id,
                              vencimiento=_ahora() + timedelta(hours=2)))
        return oc_id

    def test_comprometido_cuenta_solo_lo_que_falta_asignar(self):
        ids = self.sembrar(1)
        self._oc_aceptada(cantidad=3, asignar=ids)
        self.assertEqual(stock.comprometido(self.sku), 2)

    def test_en_camino_antes_respeta_el_limite(self):
        with SessionLocal.begin() as s:
            s.add(Solicitud(tipo="fabricacion", sku=self.sku, cantidad=2,
                            llega_en=_ahora() + timedelta(minutes=30)))
            s.add(Solicitud(tipo="fabricacion", sku=self.sku, cantidad=5,
                            llega_en=_ahora() + timedelta(hours=3)))
        self.assertEqual(stock.en_camino_antes(self.sku, _ahora() + timedelta(hours=1)), 2)

    def test_portal_solo_vende_sobre_el_minimo_y_lo_comprometido(self):
        self.sembrar(6)
        self._oc_aceptada(cantidad=1, asignar=[])
        with patch.object(stock, "minimo", return_value=3):
            self.assertEqual(stock.vendible_portal(self.sku), 2)  # 6 - 3 - 1

    def test_portal_nunca_negativo(self):
        self.sembrar(1)
        with patch.object(stock, "minimo", return_value=3):
            self.assertEqual(stock.vendible_portal(self.sku), 0)


@unittest.skipUnless(TEST_DB, "TEST_DATABASE_URL no definido")
class BandejaTest(BaseDB):
    def test_recibir_es_idempotente_entre_canales(self):
        oc_id = _oc_id()
        self.assertTrue(bandeja.recibir(oc_id, "pubsub", "msg-1"))
        self.assertFalse(bandeja.recibir(oc_id, "pubsub", "msg-1"))
        self.assertFalse(bandeja.recibir(oc_id, "sftp", "archivo.xml"))
        self.assertEqual(bandeja.get(oc_id).canal, "pubsub")

    def test_archivo_leido_no_vuelve_a_aparecer(self):
        nombre = f"oc-{self.sufijo}.xml"
        self.assertEqual(bandeja.archivos_no_leidos([nombre]), [nombre])
        self.assertTrue(bandeja.recibir_archivo(nombre, _oc_id()))
        self.assertEqual(bandeja.archivos_no_leidos([nombre]), [])

    def test_archivo_invalido_se_anota_sin_oc(self):
        nombre = f"malo-{self.sufijo}.xml"
        self.assertFalse(bandeja.recibir_archivo(nombre, None, "XML invalido"))
        self.assertEqual(bandeja.archivos_no_leidos([nombre]), [])

    def test_reclamar_solo_gana_una_vez(self):
        oc_id = _oc_id()
        bandeja.recibir(oc_id, "sftp", "a.xml")
        self.assertTrue(bandeja.reclamar(oc_id, "nueva", "aceptando", {"acepta": True}))
        self.assertFalse(bandeja.reclamar(oc_id, "nueva", "rechazando"))
        o = bandeja.get(oc_id)
        self.assertEqual((o.estado, o.decision), ("aceptando", {"acepta": True}))

    def test_guardar_detalle_copia_la_oc_oficial(self):
        oc_id = _oc_id()
        bandeja.recibir(oc_id, "sftp", "a.xml")
        bandeja.guardar_detalle(oc_id, self.oc_remota(oc_id, cantidad=2, despachado=1))
        o = bandeja.get(oc_id)
        self.assertEqual((o.sku, o.cantidad, o.estado_remoto, o.despachado_remoto),
                         (self.sku, 2, "creada", 1))


def _http_error(status: int) -> "httpx.HTTPStatusError":
    req = httpx.Request("POST", "https://x")
    return httpx.HTTPStatusError("error", request=req, response=httpx.Response(status, request=req))


@unittest.skipUnless(TEST_DB, "TEST_DATABASE_URL no definido")
class ProcesadorTest(BaseDB):
    def setUp(self):
        super().setUp()
        self.es_kit = patch.object(procesador, "_es_kit", side_effect=lambda sku: sku == self.sku)
        self.es_kit.start()
        self.addCleanup(self.es_kit.stop)

    def _recibir(self) -> str:
        oc_id = _oc_id()
        bandeja.recibir(oc_id, "sftp", f"{oc_id}.xml")
        return oc_id

    def test_con_stock_reserva_y_acepta(self):
        self.sembrar(2)
        oc_id = self._recibir()
        with patch.object(procesador, "ordenes_client") as api:
            api.obtener.return_value = self.oc_remota(oc_id, cantidad=2)
            procesador.procesar(oc_id)
        api.actualizar_estado.assert_called_once_with(oc_id, "aceptada")
        o = bandeja.get(oc_id)
        self.assertEqual(o.estado, "aceptada")
        self.assertEqual(custodia.unidades_de_venta(o.venta_id), 2)
        self.assertEqual(custodia.stock_disponible(self.sku), 0)

    def test_sin_stock_rechaza_y_guarda_el_motivo(self):
        oc_id = self._recibir()
        with patch.object(procesador, "ordenes_client") as api:
            api.obtener.return_value = self.oc_remota(oc_id, cantidad=1)
            procesador.procesar(oc_id)
        api.actualizar_estado.assert_called_once_with(oc_id, "rechazada")
        o = bandeja.get(oc_id)
        self.assertEqual(o.estado, "rechazada")
        self.assertFalse(o.decision["acepta"])

    def test_oc_inexistente_se_descarta(self):
        oc_id = self._recibir()
        with patch.object(procesador, "ordenes_client") as api:
            api.obtener.side_effect = _http_error(404)
            procesador.procesar(oc_id)
        self.assertEqual(bandeja.get(oc_id).estado, "descartada")
        api.actualizar_estado.assert_not_called()

    def test_caida_tras_anotar_aceptando_se_recupera(self):
        # Se anoto "aceptando" pero la API no respondio: la OC sigue creada
        self.sembrar(1)
        oc_id = self._recibir()
        with patch.object(procesador, "ordenes_client") as api:
            api.obtener.return_value = self.oc_remota(oc_id)
            api.actualizar_estado.side_effect = httpx.ConnectError("caida")
            with self.assertRaises(httpx.ConnectError):
                procesador.procesar(oc_id)
        self.assertEqual(bandeja.get(oc_id).estado, "aceptando")

        with patch.object(procesador, "ordenes_client") as api:
            api.obtener.return_value = self.oc_remota(oc_id)
            procesador.reintentar_decisiones()
        api.actualizar_estado.assert_called_once_with(oc_id, "aceptada")
        self.assertEqual(bandeja.get(oc_id).estado, "aceptada")

    def test_aceptacion_que_si_llego_no_se_reenvia(self):
        self.sembrar(1)
        oc_id = self._recibir()
        bandeja.reclamar(oc_id, "nueva", "aceptando")
        with patch.object(procesador, "ordenes_client") as api:
            api.obtener.return_value = self.oc_remota(oc_id, estado="aceptada")
            procesador.reintentar_decisiones()
        api.actualizar_estado.assert_not_called()
        self.assertEqual(bandeja.get(oc_id).estado, "aceptada")

    def test_aceptando_que_vencio_libera_la_reserva(self):
        self.sembrar(1)
        oc_id = self._recibir()
        with patch.object(procesador, "ordenes_client") as api:
            api.obtener.return_value = self.oc_remota(oc_id)
            api.actualizar_estado.side_effect = httpx.ConnectError("caida")
            with self.assertRaises(httpx.ConnectError):
                procesador.procesar(oc_id)
        self.assertEqual(custodia.stock_disponible(self.sku), 0)

        with patch.object(procesador, "ordenes_client") as api:
            api.obtener.return_value = self.oc_remota(oc_id, estado="vencida")
            procesador.reintentar_decisiones()
        self.assertEqual(bandeja.get(oc_id).estado, "vencida")
        self.assertEqual(custodia.stock_disponible(self.sku), 1)

    def test_la_misma_oc_dos_veces_acepta_una_sola_vez(self):
        self.sembrar(2)
        oc_id = self._recibir()
        bandeja.recibir(oc_id, "pubsub", "msg-repetido")
        with patch.object(procesador, "ordenes_client") as api:
            api.obtener.return_value = self.oc_remota(oc_id, cantidad=1)
            procesador.procesar_nuevas()
            procesador.procesar_nuevas()
        api.actualizar_estado.assert_called_once_with(oc_id, "aceptada")
        self.assertEqual(custodia.stock_disponible(self.sku), 1)

    def _con_intentos(self, oc_id: str, intentos: int) -> None:
        with SessionLocal.begin() as s:
            s.execute(update(OrdenCompra).where(OrdenCompra.id == oc_id)
                      .values(intentos=intentos))

    def test_oc_que_falla_siempre_se_descarta_al_llegar_al_maximo(self):
        oc_id = self._recibir()
        self._con_intentos(oc_id, procesador.MAX_INTENTOS - 1)
        with patch.object(procesador, "ordenes_client") as api:
            api.obtener.side_effect = _http_error(500)
            procesador.procesar_nuevas()
        o = bandeja.get(oc_id)
        self.assertEqual((o.estado, o.intentos), ("descartada", procesador.MAX_INTENTOS))
        self.assertIn("ultimo error", o.decision["motivo"])
        api.actualizar_estado.assert_not_called()

    def test_oc_sin_intentos_va_antes_que_las_que_fallaron(self):
        vieja = self._recibir()
        self._con_intentos(vieja, 3)
        nueva = self._recibir()
        self.assertEqual(bandeja.nuevas()[:2], [nueva, vieja])
        with patch.object(procesador, "ordenes_client") as api:
            api.obtener.side_effect = _http_error(500)
            procesador.procesar_nuevas(limite=1)
        api.obtener.assert_called_once_with(nueva)


@unittest.skipUnless(TEST_DB, "TEST_DATABASE_URL no definido")
class DespachadorTest(BaseDB):
    def _sin_red(self):
        mover = patch.object(despachador, "mover", side_effect=lambda uid, hacia:
                             custodia.registrar_traslado(uid, hacia))
        dispatch = patch.object(despachador.farma_client, "dispatch", return_value=None)
        return mover, dispatch

    def test_asigna_unidades_nuevas_a_la_que_vence_primero(self):
        tarde = self.aceptada(1, vence_en=timedelta(hours=2))
        pronto = self.aceptada(1, vence_en=timedelta(hours=1))
        self.sembrar(1)
        self.assertEqual(despachador.asignar_pendientes(), 1)
        self.assertEqual(custodia.unidades_de_venta(bandeja.get(pronto).venta_id), 1)
        self.assertEqual(custodia.unidades_de_venta(bandeja.get(tarde).venta_id), 0)

    def test_despacha_y_marca_cumplida(self):
        oc_id = self.aceptada(2)
        self.sembrar(2)
        despachador.asignar_pendientes()
        mover, dispatch = self._sin_red()
        with mover as m, dispatch as d:
            self.assertEqual(despachador.despachar_pendientes(), 2)
        self.assertEqual(d.call_count, 2)
        self.assertTrue(all(c.args[1] == "checkOut" for c in m.call_args_list))
        self.assertEqual(bandeja.get(oc_id).estado, "cumplida")

    def test_unidad_ya_despachada_no_se_despacha_dos_veces(self):
        oc_id = self.aceptada(1)
        self.sembrar(1)
        despachador.asignar_pendientes()
        mover, dispatch = self._sin_red()
        with mover, dispatch as d:
            despachador.despachar_pendientes()
            despachador.despachar_pendientes()
        self.assertEqual(d.call_count, 1)

    def test_404_tras_caida_se_confirma_si_el_sistema_ya_lo_conto(self):
        oc_id = self.aceptada(1)
        self.sembrar(1)
        despachador.asignar_pendientes()
        mover, dispatch = self._sin_red()
        with mover, dispatch as d, patch.object(despachador, "ordenes_client") as api:
            d.side_effect = _http_error(404)
            api.obtener.return_value = self.oc_remota(oc_id, estado="cumplida", despachado=1)
            despachador.despachar_pendientes()
        self.assertEqual(bandeja.get(oc_id).estado, "cumplida")

    def test_error_de_dispatch_deja_la_unidad_pendiente(self):
        oc_id = self.aceptada(1)
        self.sembrar(1)
        despachador.asignar_pendientes()
        mover, dispatch = self._sin_red()
        with mover, dispatch as d:
            d.side_effect = _http_error(500)
            self.assertEqual(despachador.despachar_pendientes(), 0)
        venta_id = bandeja.get(oc_id).venta_id
        self.assertEqual(len(custodia.pendientes_de_venta(venta_id)), 1)
        self.assertEqual(bandeja.get(oc_id).estado, "aceptada")

    def test_404_de_unidad_que_no_salio_la_desasigna_y_se_asigna_otra(self):
        oc_id = self.aceptada(1)
        self.sembrar(2)
        despachador.asignar_pendientes()
        venta_id = bandeja.get(oc_id).venta_id
        [perdida] = custodia.pendientes_de_venta(venta_id)
        mover, dispatch = self._sin_red()
        with mover, dispatch as d, patch.object(despachador, "ordenes_client") as api:
            d.side_effect = _http_error(404)
            api.obtener.return_value = self.oc_remota(oc_id, estado="aceptada", despachado=0)
            self.assertEqual(despachador.despachar_pendientes(), 0)
        self.assertEqual(custodia.pendientes_de_venta(venta_id), [])
        with SessionLocal() as s:
            u = s.get(Unidad, perdida)
            self.assertEqual((u.estado, u.espacio_actual), ("vencida", None))
        self.assertEqual(bandeja.get(oc_id).estado, "aceptada")

        self.assertEqual(despachador.asignar_pendientes(), 1)
        [otra] = custodia.pendientes_de_venta(venta_id)
        self.assertNotEqual(otra, perdida)

    def test_devolver_desde_checkout_no_toca_las_reservadas(self):
        oc_id = self.aceptada(1)
        [reservada] = self.sembrar(1, espacio="checkOut")
        custodia.asignar_unidades_a_venta(bandeja.get(oc_id).venta_id, [reservada])
        mover, _ = self._sin_red()
        with mover as m, patch.object(despachador, "es_frio", return_value=False):
            despachador.devolver_desde_checkout(maximo=1000)
        self.assertNotIn(reservada, [c.args[0] for c in m.call_args_list])


@unittest.skipUnless(TEST_DB, "TEST_DATABASE_URL no definido")
class ConciliadorTest(BaseDB):
    def test_vencida_en_el_sistema_libera_la_reserva(self):
        oc_id = self.aceptada(1)
        self.sembrar(1)
        despachador.asignar_pendientes()
        self.assertEqual(custodia.stock_disponible(self.sku), 0)
        with patch.object(conciliador, "ordenes_client") as api:
            api.obtener.return_value = self.oc_remota(oc_id, estado="vencida")
            conciliador.conciliar()
        self.assertEqual(bandeja.get(oc_id).estado, "vencida")
        self.assertEqual(custodia.stock_disponible(self.sku), 1)

    def test_cumplida_local_se_confirma_con_el_sistema(self):
        oc_id = self.aceptada(1)
        bandeja.marcar(oc_id, "cumplida")
        with patch.object(conciliador, "ordenes_client") as api:
            api.obtener.return_value = self.oc_remota(oc_id, estado="cumplida", despachado=1)
            conciliador.conciliar()
        self.assertEqual(bandeja.get(oc_id).estado_remoto, "cumplida")

    def _remotas(self, por_id: dict[str, dict]):
        """obtener() que responde por id; las OC de otros tests siguen aceptadas."""
        return lambda i: por_id.get(i) or self.oc_remota(i, estado="aceptada")

    def _en_checkout(self, oc_id: str) -> str:
        [unidad_id] = custodia.pendientes_de_venta(bandeja.get(oc_id).venta_id)
        custodia.registrar_traslado(unidad_id, "checkOut")
        return unidad_id

    def _unidad(self, unidad_id: str):
        with SessionLocal() as s:
            return s.get(Unidad, unidad_id)

    def test_cumplida_en_el_sistema_confirma_la_unidad_pendiente(self):
        oc_id = self.aceptada(1)
        self.sembrar(1)
        despachador.asignar_pendientes()
        unidad_id = self._en_checkout(oc_id)
        with patch.object(conciliador, "ordenes_client") as api:
            api.obtener.side_effect = self._remotas(
                {oc_id: self.oc_remota(oc_id, estado="cumplida", despachado=1)})
            conciliador.conciliar()
        venta_id = bandeja.get(oc_id).venta_id
        self.assertEqual(bandeja.get(oc_id).estado, "cumplida")
        self.assertEqual(custodia.pendientes_de_venta(venta_id), [])
        self.assertEqual(custodia.despachadas_de_venta(venta_id), 1)
        self.assertEqual(self._unidad(unidad_id).estado, "despachada")

    def test_vencida_confirma_lo_que_salio_y_devuelve_lo_que_no(self):
        salio = self.aceptada(1)
        no_salio = self.aceptada(1)
        self.sembrar(2)
        despachador.asignar_pendientes()
        u_salio = self._en_checkout(salio)
        u_no_salio = self._en_checkout(no_salio)
        with patch.object(conciliador, "ordenes_client") as api:
            api.obtener.side_effect = self._remotas({
                salio: self.oc_remota(salio, estado="vencida", despachado=1),
                no_salio: self.oc_remota(no_salio, estado="vencida", despachado=0)})
            conciliador.conciliar()
        self.assertEqual(bandeja.get(salio).estado, "vencida")
        self.assertEqual(bandeja.get(no_salio).estado, "vencida")
        self.assertEqual(self._unidad(u_salio).estado, "despachada")
        self.assertEqual(custodia.despachadas_de_venta(bandeja.get(salio).venta_id), 1)
        u = self._unidad(u_no_salio)
        self.assertEqual((u.estado, u.espacio_actual), ("en_stock", "checkOut"))
        self.assertEqual(custodia.stock_disponible(self.sku), 0)  # checkOut no es vendible

        mover = patch.object(despachador, "mover", side_effect=lambda uid, hacia:
                             custodia.registrar_traslado(uid, hacia))
        with mover, patch.object(despachador, "es_frio", return_value=False):
            self.assertGreaterEqual(despachador.devolver_desde_checkout(maximo=1000), 1)
        u = self._unidad(u_no_salio)
        self.assertEqual((u.estado, u.espacio_actual), ("en_stock", "bodega"))
        self.assertEqual(custodia.stock_disponible(self.sku), 1)

    def test_sigue_aceptada_no_cambia_nada(self):
        oc_id = self.aceptada(1)
        with patch.object(conciliador, "ordenes_client") as api:
            api.obtener.return_value = self.oc_remota(oc_id, estado="aceptada")
            conciliador.conciliar()
        self.assertEqual(bandeja.get(oc_id).estado, "aceptada")


@unittest.skipUnless(TEST_DB, "TEST_DATABASE_URL no definido")
class SaludTest(BaseDB):
    def test_registra_ok_y_error_por_componente(self):
        nombre = f"test-{self.sufijo}"
        salud.ok(nombre)
        salud.fallo(nombre, "se cayo")
        comp = salud.resumen()["componentes"][nombre]
        self.assertIsNotNone(comp["ultimo_ok"])
        self.assertEqual(comp["ultimo_error"], "se cayo")

    def test_resumen_cuenta_oc_por_estado(self):
        bandeja.recibir(_oc_id(), "sftp", "x.xml")
        self.assertGreaterEqual(salud.resumen()["ordenes"].get("nueva", 0), 1)


if __name__ == "__main__":
    unittest.main()
