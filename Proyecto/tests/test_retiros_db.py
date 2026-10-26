"""Tests del retiro de lote contra un Postgres desechable (NUNCA el de PROD).

Se saltan si TEST_DATABASE_URL no esta definido. Farma Central se parchea:
ningun test llama a la API real.
"""
from __future__ import annotations

import os
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

TEST_DB = os.environ.get("TEST_DATABASE_URL")
if TEST_DB:
    os.environ["DATABASE_URL"] = TEST_DB

    import httpx
    from sqlalchemy import select, update

    from app import custodia
    from app.db import SessionLocal
    from app.models import (Lote, LotRelation, Movimiento, OrdenCompra, Retiro, RetiroNotificacion,
                            RetiroUnidad, Solicitud, Unidad, VentaUnidad)
    from app.pedidos import despachador
    from app.retiros import investigacion, procesamiento, registro


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _id() -> str:
    return uuid.uuid4().hex[:24]


def _error(status: int) -> "httpx.HTTPStatusError":
    req = httpx.Request("PATCH", "http://farma/x")
    return httpx.HTTPStatusError("error", request=req, response=httpx.Response(status, request=req))


class FarmaFalsa:
    """Registra lo que se le pide a Farma Central. fallar: {nombre: [excepciones]}"""

    def __init__(self):
        self.reportes, self.notificaciones, self.movidas = [], [], []
        self.fallar: dict[str, list] = {}
        self.en_cuarentena: list[dict] = []
        self.espacios: dict[str, list[dict]] = {}  # store -> productos (salvo cuarentena)
        self.consultas = 0

    def _quizas_fallar(self, nombre):
        cola = self.fallar.get(nombre) or []
        if cola:
            exc = cola.pop(0)
            if exc is not None:
                raise exc

    def reportar_retiro(self, recall_id, cuerpo):
        self._quizas_fallar("reporte")
        self.reportes.append((recall_id, cuerpo))

    def notificar_retiro(self, recall_id, cuerpo):
        self._quizas_fallar("notificacion")
        self.notificaciones.append((recall_id, cuerpo))

    def move_product(self, unidad_id, store):
        self._quizas_fallar("mover")
        self.movidas.append((unidad_id, store))

    def space_products(self, store, sku, limit=200):
        self.consultas += 1
        productos = (self.en_cuarentena if store == "store-quarantine"
                     else self.espacios.get(store, []))
        return [p for p in productos if p["sku"] == sku]

    def parches(self):
        return [patch.object(procesamiento.farma_client, "reportar_retiro", self.reportar_retiro),
                patch.object(procesamiento.farma_client, "notificar_retiro", self.notificar_retiro),
                patch.object(procesamiento.farma_client, "move_product", self.move_product),
                patch.object(procesamiento.farma_client, "space_products", self.space_products),
                patch.object(procesamiento.esp, "store_id", lambda tipo: f"store-{tipo}")]


@unittest.skipUnless(TEST_DB, "TEST_DATABASE_URL no definido")
class BaseRetiro(unittest.TestCase):
    """Arbol de lotes: raiz -> intermedio -> kit, mas un lote ajeno del mismo SKU.

    raiz:       r_stock (bodega), r_reservada (OC A, pendiente), r_despachada (OC B),
                r_consumida, r_portal (venta del portal despachada, sin OC)
    intermedio: i_stock (cold), i_consumida
    kit:        k_stock (packaging), k_despachada (OC C), k_vencida
    ajeno:      x_stock (mismo SKU que la raiz, otro lote)
    """

    def setUp(self):
        self.sufijo = uuid.uuid4().hex[:8].upper()
        self.recall_id = f"rcl_{self.sufijo.lower()}"
        # Los retiros de tests anteriores no deben procesarse en este test
        self.cerrar_retiros()
        self.addCleanup(self.cerrar_retiros)  # un retiro pendiente pausaria el despacho
        procesamiento._fallos.clear()
        procesamiento._no_movibles.clear()
        procesamiento._investigados.clear()
        self.reloj = 1000.0
        self.farma = FarmaFalsa()
        for p in self.farma.parches() + [patch.object(procesamiento, "_reloj",
                                                      lambda: self.reloj)]:
            p.start()
            self.addCleanup(p.stop)
        self.sembrar()

    @staticmethod
    def cerrar_retiros():
        with SessionLocal.begin() as s:
            s.execute(update(Retiro).values(estado="completo", plazo=_ahora() - timedelta(days=2)))

    def sembrar(self):
        sx = self.sufijo
        self.sku_raiz, self.sku_int, self.sku_kit = f"API-T-{sx}", f"BLI-T-{sx}", f"KIT-T-{sx}"
        self.u = {n: _id() for n in ("r_stock", "r_reservada", "r_despachada", "r_consumida",
                                    "r_portal", "i_stock", "i_consumida", "k_stock",
                                    "k_despachada", "k_vencida", "x_stock")}
        self.oc = {n: _id() for n in ("A", "B", "C")}
        with SessionLocal.begin() as s:
            sol_i = Solicitud(tipo="fabricacion", sku=self.sku_int, cantidad=2, estado="recibida")
            sol_k = Solicitud(tipo="fabricacion", sku=self.sku_kit, cantidad=3, estado="recibida")
            s.add_all([sol_i, sol_k])
            s.flush()
            self.raiz = Lote(codigo=f"L-RAIZ-{sx}", sku=self.sku_raiz, cantidad_inicial=5,
                             origen="farma_central")
            self.inter = Lote(codigo=f"L-INT-{sx}", sku=self.sku_int, cantidad_inicial=2,
                              origen="produccion", solicitud_id=sol_i.id)
            self.kit = Lote(codigo=f"L-KIT-{sx}", sku=self.sku_kit, cantidad_inicial=3,
                            origen="produccion", solicitud_id=sol_k.id)
            self.ajeno = Lote(codigo=f"L-AJENO-{sx}", sku=self.sku_raiz, cantidad_inicial=1,
                              origen="farma_central")
            s.add_all([self.raiz, self.inter, self.kit, self.ajeno])
            s.flush()
            s.add(LotRelation(parent_lote_id=self.raiz.id, child_lote_id=self.inter.id,
                              cantidad=1, solicitud_id=sol_i.id))
            s.add(LotRelation(parent_lote_id=self.inter.id, child_lote_id=self.kit.id,
                              cantidad=1, solicitud_id=sol_k.id))

            def unidad(nombre, lote, estado, espacio):
                s.add(Unidad(id=self.u[nombre], lote_id=lote.id, sku=lote.sku, estado=estado,
                             espacio_actual=espacio))

            unidad("r_stock", self.raiz, "en_stock", "bodega")
            unidad("r_reservada", self.raiz, "en_stock", "checkOut")
            unidad("r_despachada", self.raiz, "despachada", None)
            unidad("r_consumida", self.raiz, "consumida", None)
            unidad("r_portal", self.raiz, "despachada", None)
            unidad("i_stock", self.inter, "en_stock", "cold")
            unidad("i_consumida", self.inter, "consumida", None)
            unidad("k_stock", self.kit, "en_stock", "packaging")
            unidad("k_despachada", self.kit, "despachada", None)
            unidad("k_vencida", self.kit, "vencida", None)
            unidad("x_stock", self.ajeno, "en_stock", "bodega")
            for letra, cliente in (("A", "Clinica A"), ("B", "Farmacia B"), ("C", "Hospital C")):
                s.add(OrdenCompra(id=self.oc[letra], canal="pubsub", estado="cumplida",
                                  sku=self.sku_raiz, cantidad=1, cliente=cliente))

        self.ventas = {}
        for letra in ("A", "B", "C"):
            nombre = "" if letra == "C" else f"Venta {letra}"  # C: el nombre sale de la OC
            self.ventas[letra] = custodia.crear_venta(nombre, None, 0, canal="pubsub",
                                                      orden_externa_id=self.oc[letra],
                                                      estado="orden_compra")
        portal = custodia.crear_venta("Cliente Portal", "p@x.cl", 1000)
        custodia.asignar_unidades_a_venta(self.ventas["A"], [self.u["r_reservada"]])
        with SessionLocal.begin() as s:
            s.add(VentaUnidad(venta_id=self.ventas["B"], unidad_id=self.u["r_despachada"],
                              lote_id=self.raiz.id, estado="despachada", despachada_en=_ahora()))
            s.add(VentaUnidad(venta_id=self.ventas["C"], unidad_id=self.u["k_despachada"],
                              lote_id=self.kit.id, estado="despachada", despachada_en=_ahora()))
            s.add(VentaUnidad(venta_id=portal, unidad_id=self.u["r_portal"],
                              lote_id=self.raiz.id, estado="despachada", despachada_en=_ahora()))

    def recibir(self, plazo: timedelta = timedelta(minutes=30)) -> None:
        registro.recibir({"id": self.recall_id, "lote": self.raiz.codigo, "sku": self.sku_raiz,
                          "motivo": "prueba", "emitido_en": _ahora(),
                          "plazo": _ahora() + plazo})

    def reportes(self):
        return [c for rid, c in self.farma.reportes if rid == self.recall_id]

    def notificaciones(self):
        return [c for rid, c in self.farma.notificaciones if rid == self.recall_id]

    def en_stock_esperado(self):
        return {self.u["r_stock"], self.u["r_reservada"], self.u["i_stock"], self.u["k_stock"]}


class InvestigacionTest(BaseRetiro):
    def test_encuentra_derivados_recursivos_con_su_lote_padre(self):
        inv = investigacion.investigar(self.raiz.codigo)
        self.assertEqual(
            sorted((d["batch"], d["sku"], d["sourceBatch"]) for d in inv["derivados"]),
            sorted([(self.inter.codigo, self.sku_int, self.raiz.codigo),
                    (self.kit.codigo, self.sku_kit, self.inter.codigo)]))

    def test_lote_con_dos_padres_afectados_va_una_vez_por_padre(self):
        with SessionLocal.begin() as s:
            s.add(LotRelation(parent_lote_id=self.raiz.id, child_lote_id=self.kit.id,
                              cantidad=1, solicitud_id=self.kit.solicitud_id))
        inv = investigacion.investigar(self.raiz.codigo)
        self.assertEqual(len(inv["derivados"]), 3)

    def test_unidades_en_stock_solo_del_lote_y_sus_derivados(self):
        inv = investigacion.investigar(self.raiz.codigo)
        self.assertEqual({u["unidad_id"] for u in inv["en_stock"]}, self.en_stock_esperado())
        espacios = {u["unidad_id"]: u["espacio"] for u in inv["en_stock"]}
        self.assertEqual(espacios[self.u["i_stock"]], "cold")

    def test_entregas_agrupadas_por_oc_sin_ventas_del_portal(self):
        inv = investigacion.investigar(self.raiz.codigo)
        entregas = {e["orderId"]: e for e in inv["entregas"]}
        self.assertEqual(set(entregas), {self.oc["B"], self.oc["C"]})
        self.assertEqual(entregas[self.oc["B"]]["productIds"], [self.u["r_despachada"]])
        self.assertEqual(entregas[self.oc["B"]]["customerName"], "Venta B")
        self.assertEqual(entregas[self.oc["C"]]["customerName"], "Hospital C")

    def test_lote_desconocido_da_investigacion_vacia(self):
        inv = investigacion.investigar("L-NO-EXISTE-" + self.sufijo)
        self.assertIsNone(inv["lote"])
        self.assertEqual((inv["derivados"], inv["en_stock"], inv["entregas"]), ([], [], []))


class RegistroTest(BaseRetiro):
    def test_aviso_repetido_no_entra_dos_veces(self):
        aviso = {"id": self.recall_id, "lote": self.raiz.codigo, "sku": None, "motivo": None,
                 "emitido_en": None, "plazo": None}
        self.assertTrue(registro.recibir(aviso))
        self.assertFalse(registro.recibir(aviso))

    def test_sincronizar_activos_registra_los_que_faltan(self):
        activos = [{"recallId": self.recall_id, "batch": self.raiz.codigo, "sku": self.sku_raiz,
                    "reason": "x", "issuedAt": "2026-10-28T14:12:00Z",
                    "deadline": "2026-10-28T14:42:00Z"}]
        with patch.object(procesamiento.farma_client, "recalls_activos", return_value=activos):
            self.assertEqual(procesamiento.sincronizar_activos(), 1)
            self.assertEqual(procesamiento.sincronizar_activos(), 0)
        with SessionLocal() as s:
            r = s.get(Retiro, self.recall_id)
            self.assertEqual(r.lote, self.raiz.codigo)
            self.assertEqual(r.plazo, datetime(2026, 10, 28, 14, 42, tzinfo=timezone.utc))


class ProcesamientoTest(BaseRetiro):
    def test_flujo_completo(self):
        self.recibir()
        procesamiento.procesar_pendientes()

        # Reporte: exactamente lo afectado, con el espacio donde estaba
        reporte = self.reportes()[-1]
        self.assertEqual({i["productId"] for i in reporte["inStock"]}, self.en_stock_esperado())
        stores = {i["productId"]: i["store"] for i in reporte["inStock"]}
        self.assertEqual(stores[self.u["r_stock"]], "store-bodega")
        self.assertEqual(stores[self.u["k_stock"]], "store-packaging")
        self.assertEqual(len(reporte["derivedBatches"]), 2)
        self.assertEqual({d["orderId"] for d in reporte["deliveries"]},
                         {self.oc["B"], self.oc["C"]})
        self.assertNotIn(self.u["x_stock"], str(reporte))

        # Una notificacion por OC con entregas
        self.assertEqual(sorted(n["orderId"] for n in self.notificaciones()),
                         sorted([self.oc["B"], self.oc["C"]]))

        # Cuarentena: movidas en Farma y en custodia
        self.assertEqual({uid for uid, store in self.farma.movidas
                          if store == "store-quarantine"}, self.en_stock_esperado())
        with SessionLocal() as s:
            for uid in self.en_stock_esperado():
                u = s.get(Unidad, uid)
                self.assertEqual((u.estado, u.espacio_actual), ("cuarentena", "quarantine"))
            self.assertEqual(s.get(Unidad, self.u["x_stock"]).estado, "en_stock")
            mov = s.scalar(select(Movimiento).where(Movimiento.unidad_id == self.u["r_stock"],
                                                   Movimiento.tipo == "cuarentena"))
            self.assertEqual((mov.desde, mov.hacia), ("bodega", "quarantine"))
            # La reserva de la OC A se suelta para que el despachador asigne otra unidad
            self.assertIsNone(s.scalar(select(VentaUnidad).where(
                VentaUnidad.unidad_id == self.u["r_reservada"])))
            filas = s.scalars(select(RetiroUnidad).where(
                RetiroUnidad.retiro_id == self.recall_id)).all()
            self.assertTrue(all(f.en_cuarentena for f in filas))
            espacios = {f.unidad_id: f.espacio_original for f in filas}
            self.assertEqual(espacios[self.u["r_reservada"]], "checkOut")
            r = s.get(Retiro, self.recall_id)
            self.assertEqual(r.estado, "completo")
            self.assertIsNotNone(r.reportado_en)

    def test_re_ejecutar_no_repite_nada(self):
        self.recibir()
        procesamiento.procesar_pendientes()
        reportes, notifs, movidas = (len(self.reportes()), len(self.notificaciones()),
                                     len(self.farma.movidas))
        procesamiento.procesar_pendientes()
        procesamiento.procesar_pendientes()
        self.assertEqual(len(self.reportes()), reportes)
        self.assertEqual(len(self.notificaciones()), notifs)
        self.assertEqual(len(self.farma.movidas), movidas)

    def test_unidades_retiradas_no_son_vendibles_antes_de_moverlas(self):
        self.recibir()
        self.farma.fallar["mover"] = [_error(500)] * 20
        procesamiento.procesar_pendientes()
        self.assertEqual(len(self.reportes()), 1)  # el reporte sale igual
        ids = {u.id for u in custodia.unidades_disponibles(self.sku_raiz)}
        self.assertNotIn(self.u["r_stock"], ids)
        self.assertIn(self.u["x_stock"], ids)
        with SessionLocal() as s:
            self.assertEqual(s.get(Retiro, self.recall_id).estado, "reportado")

    def test_se_recupera_si_falla_la_notificacion(self):
        self.recibir()
        self.farma.fallar["notificacion"] = [_error(500)]
        procesamiento.procesar_pendientes()
        self.assertEqual(len(self.notificaciones()), 1)
        with SessionLocal() as s:
            self.assertEqual(s.get(Retiro, self.recall_id).estado, "reportado")
        self.reloj += 11  # espera del primer reintento
        procesamiento.procesar_pendientes()
        self.assertEqual(sorted(n["orderId"] for n in self.notificaciones()),
                         sorted([self.oc["B"], self.oc["C"]]))
        with SessionLocal() as s:
            self.assertEqual(s.get(Retiro, self.recall_id).estado, "completo")
            self.assertTrue(all(n.enviada_en for n in s.scalars(select(RetiroNotificacion).where(
                RetiroNotificacion.retiro_id == self.recall_id))))

    def test_se_recupera_si_falla_el_reporte(self):
        self.recibir()
        self.farma.fallar["reporte"] = [httpx.ConnectError("caido")]
        procesamiento.procesar_pendientes()
        self.assertEqual(self.reportes(), [])
        with SessionLocal() as s:
            r = s.get(Retiro, self.recall_id)
            self.assertEqual(r.estado, "pendiente")
            self.assertIn("caido", r.ultimo_error)
        self.reloj += 11
        procesamiento.procesar_pendientes()
        self.assertEqual(len(self.reportes()), 1)
        self.assertEqual({i["productId"] for i in self.reportes()[0]["inStock"]},
                         self.en_stock_esperado())

    def test_unidad_que_ya_estaba_en_cuarentena(self):
        """Caida entre el move de Farma y la anotacion: el segundo move falla,
        pero la unidad aparece en el area de cuarentena."""
        self.recibir()
        self.farma.fallar["mover"] = [_error(400)]
        self.farma.en_cuarentena = [{"_id": uid, "sku": sku} for uid, sku in (
            (self.u["r_stock"], self.sku_raiz), (self.u["r_reservada"], self.sku_raiz),
            (self.u["i_stock"], self.sku_int), (self.u["k_stock"], self.sku_kit))]
        procesamiento.procesar_pendientes()
        with SessionLocal() as s:
            for uid in self.en_stock_esperado():
                self.assertEqual(s.get(Unidad, uid).espacio_actual, "quarantine")
            self.assertEqual(s.get(Retiro, self.recall_id).estado, "completo")

    def test_unidad_que_ya_no_existe_en_farma(self):
        """I-1: 404 o 400 y no esta en cuarentena ni en su espacio: se da por
        inexistente, no se reintenta y sale del reporte."""
        self.recibir()
        self.farma.fallar["mover"] = [_error(400)]
        procesamiento.procesar_pendientes()
        with SessionLocal() as s:
            filas = {f.unidad_id: f for f in s.scalars(select(RetiroUnidad).where(
                RetiroUnidad.retiro_id == self.recall_id))}
            perdidas = [uid for uid, f in filas.items() if not f.en_cuarentena]
            self.assertEqual(len(perdidas), 1)
            self.assertEqual(s.get(Unidad, perdidas[0]).estado, "vencida")
        procesamiento.procesar_pendientes()
        self.assertNotIn(perdidas[0], {i["productId"] for i in self.reportes()[-1]["inStock"]})
        self.assertEqual(len(self.reportes()[-1]["inStock"]), 3)
        with SessionLocal() as s:
            self.assertEqual(s.get(Retiro, self.recall_id).estado, "completo")

    def test_unidad_que_farma_no_deja_mover_no_se_reintenta(self):
        """I-1: 4xx, la unidad existe en su espacio pero Farma no la mueve."""
        self.recibir()
        self.farma.fallar["mover"] = [_error(400)]
        for nombre, sku, espacio in (("r_stock", self.sku_raiz, "bodega"),
                                     ("r_reservada", self.sku_raiz, "checkOut"),
                                     ("i_stock", self.sku_int, "cold"),
                                     ("k_stock", self.sku_kit, "packaging")):
            self.farma.espacios[f"store-{espacio}"] = [{"_id": self.u[nombre], "sku": sku}]
        procesamiento.procesar_pendientes()
        self.assertEqual(len(procesamiento._no_movibles), 1)
        rechazada = next(iter(procesamiento._no_movibles))
        movidas = len(self.farma.movidas)
        self.reloj += 120
        procesamiento.procesar_pendientes()
        self.assertEqual(len(self.farma.movidas), movidas)  # no se reintenta
        self.assertNotIn(rechazada, {uid for uid, _ in self.farma.movidas})
        self.assertIn(rechazada, {i["productId"] for i in self.reportes()[-1]["inStock"]})
        with SessionLocal() as s:
            r = s.get(Retiro, self.recall_id)
            self.assertEqual(r.estado, "completo")
            self.assertIn("no movible", r.ultimo_error)

    def test_unidad_vencida_no_se_reporta(self):
        """I-1: vence_en ya paso: Farma ya no la tiene."""
        with SessionLocal.begin() as s:
            s.get(Unidad, self.u["r_stock"]).vence_en = _ahora() - timedelta(minutes=5)
        self.recibir()
        procesamiento.procesar_pendientes()
        ids = {i["productId"] for i in self.reportes()[-1]["inStock"]}
        self.assertEqual(ids, self.en_stock_esperado() - {self.u["r_stock"]})
        self.assertNotIn(self.u["r_stock"], {uid for uid, _ in self.farma.movidas})

    def test_respeta_el_tope_de_movimientos(self):
        self.recibir()
        with patch.object(procesamiento, "MAX_REQUESTS_POR_TICK", 2):
            procesamiento.procesar_pendientes()
            self.assertEqual(len(self.farma.movidas), 2)
            procesamiento.procesar_pendientes()
        self.assertEqual(len(self.farma.movidas), 4)
        with SessionLocal() as s:
            self.assertEqual(s.get(Retiro, self.recall_id).estado, "completo")

    def test_unidad_nueva_del_lote_reenvia_el_reporte(self):
        self.recibir()
        procesamiento.procesar_pendientes()
        nueva = _id()
        with SessionLocal.begin() as s:
            s.add(Unidad(id=nueva, lote_id=self.kit.id, sku=self.sku_kit, estado="en_stock",
                         espacio_actual="packaging"))
        procesamiento.procesar_pendientes()
        self.assertEqual(len(self.reportes()), 2)
        self.assertIn(nueva, {i["productId"] for i in self.reportes()[-1]["inStock"]})

    def test_lote_desconocido_reporta_vacio(self):
        registro.recibir({"id": self.recall_id, "lote": "L-NADA-" + self.sufijo, "sku": None,
                          "motivo": None, "emitido_en": None,
                          "plazo": _ahora() + timedelta(minutes=30)})
        procesamiento.procesar_pendientes()
        self.assertEqual(self.reportes(),
                         [{"inStock": [], "derivedBatches": [], "deliveries": []}])
        self.assertEqual(self.farma.movidas, [])

    def test_api_detalle(self):
        self.recibir()
        procesamiento.procesar_pendientes()
        listado = {r["id"]: r for r in registro.listar()}
        self.assertEqual(listado[self.recall_id]["unidades_retiradas"], 4)
        d = registro.detalle(self.recall_id)
        self.assertEqual({u["id"] for u in d["unidades"]}, self.en_stock_esperado())
        self.assertTrue(all(u["sku"] and u["en_cuarentena"] for u in d["unidades"]))
        self.assertEqual(len(d["derivados"]), 2)
        self.assertEqual(len(d["entregas"]), 2)
        self.assertIsNone(registro.detalle("rcl_no_existe"))

    def test_consultas_de_espacios_cuentan_en_el_tope(self):
        """I-4: con tope 1, el move que falla gasta el request y la consulta
        del area de cuarentena queda para despues."""
        self.recibir()
        self.farma.fallar["mover"] = [_error(400)]
        with patch.object(procesamiento, "MAX_REQUESTS_POR_TICK", 1):
            self.assertEqual(procesamiento.procesar_pendientes(), 1)
        self.assertEqual(self.farma.consultas, 0)

    def test_reintento_del_reporte_con_espera(self):
        """I-4: tras un error se espera 10 s, luego 20 s."""
        self.recibir()
        self.farma.fallar["reporte"] = [_error(500), _error(500)]
        procesamiento.procesar_pendientes()
        procesamiento.procesar_pendientes()
        self.assertEqual(self.reportes(), [])
        self.reloj += 11
        procesamiento.procesar_pendientes()  # segundo fallo: ahora espera 20 s
        self.reloj += 11
        procesamiento.procesar_pendientes()
        self.assertEqual(self.reportes(), [])
        self.reloj += 10
        procesamiento.procesar_pendientes()
        self.assertEqual(len(self.reportes()), 1)

    def test_despues_del_plazo_no_reporta_ni_notifica(self):
        """I-4: pasado el deadline ya no cuentan; la cuarentena si sigue."""
        self.recibir(plazo=-timedelta(minutes=1))
        procesamiento.procesar_pendientes()
        self.assertEqual((self.reportes(), self.notificaciones()), ([], []))
        self.assertEqual({uid for uid, _ in self.farma.movidas}, self.en_stock_esperado())
        with SessionLocal() as s:
            self.assertEqual(s.get(Retiro, self.recall_id).estado, "completo")

    def test_retiro_cerrado_sigue_aislando_lo_que_llega(self):
        """I-5: un derivado que llega despues del plazo tambien va a cuarentena."""
        self.recibir()
        procesamiento.procesar_pendientes()
        with SessionLocal.begin() as s:
            s.get(Retiro, self.recall_id).plazo = _ahora() - timedelta(hours=1)
        reportes = len(self.reportes())
        nueva = _id()
        with SessionLocal.begin() as s:
            s.add(Unidad(id=nueva, lote_id=self.kit.id, sku=self.sku_kit, estado="en_stock",
                         espacio_actual="packaging"))
        procesamiento.procesar_pendientes()
        self.assertIn(nueva, {uid for uid, _ in self.farma.movidas})
        self.assertEqual(len(self.reportes()), reportes)
        with SessionLocal() as s:
            self.assertEqual(s.get(Unidad, nueva).espacio_actual, "quarantine")
            self.assertEqual(s.get(Retiro, self.recall_id).estado, "completo")


class DespachoTest(BaseRetiro):
    """I-3: el despacho de OC nunca entrega producto retirado."""

    def setUp(self):
        super().setUp()
        with SessionLocal.begin() as s:
            s.execute(update(OrdenCompra)
                      .where(OrdenCompra.estado.in_(("nueva", "aceptando", "rechazando",
                                                     "aceptada")))
                      .values(estado="descartada"))
            s.get(OrdenCompra, self.oc["A"]).estado = "aceptada"
            s.get(OrdenCompra, self.oc["A"]).venta_id = self.ventas["A"]
            s.get(OrdenCompra, self.oc["A"]).vencimiento = _ahora() + timedelta(hours=2)
        self.despachos = []
        for p in (patch.object(despachador.farma_client, "dispatch",
                               lambda uid, oc: self.despachos.append(uid)),
                  patch.object(despachador, "mover", lambda uid, hacia: None)):
            p.start()
            self.addCleanup(p.stop)

    def test_no_despacha_una_unidad_en_cuarentena(self):
        with SessionLocal.begin() as s:  # carrera: retirada pero aun asignada
            s.get(Unidad, self.u["r_reservada"]).estado = "cuarentena"
        despachador.despachar_pendientes()
        self.assertEqual(self.despachos, [])
        self.assertEqual(custodia.pendientes_de_venta(self.ventas["A"]), [])

    def test_retiro_sin_investigar_pausa_asignacion_y_despacho(self):
        self.recibir()
        self.assertTrue(procesamiento.hay_retiro_sin_investigar())
        self.assertEqual(despachador.asignar_pendientes(), 0)
        self.assertEqual(despachador.despachar_pendientes(), 0)
        self.assertEqual(self.despachos, [])
        procesamiento.procesar_pendientes()
        self.assertFalse(procesamiento.hay_retiro_sin_investigar())

    def test_sin_retiros_despacha_normal(self):
        despachador.despachar_pendientes()
        self.assertEqual(self.despachos, [self.u["r_reservada"]])


if __name__ == "__main__":
    unittest.main()
