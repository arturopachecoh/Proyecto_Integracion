"""Tests del canal de mensajeria contra un Postgres desechable (NUNCA el de PROD).

El modelo de lenguaje y la plataforma de mensajeria se parchean. Se saltan si
TEST_DATABASE_URL no esta definido.
"""
from __future__ import annotations

import json
import os
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

TEST_DB = os.environ.get("TEST_DATABASE_URL")
if TEST_DB:
    os.environ["DATABASE_URL"] = TEST_DB
    os.environ.setdefault("FARMA_GROUP", "4")
    os.environ.setdefault("PUBLIC_BASE_URL", "https://choripan4.ing.uc.cl")

    import httpx
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy import text, update

    from app import config, oidc
    from app.db import SessionLocal, engine
    from app.mensajeria import modelo, procesador, registro, webhook
    from app.mensajeria.validacion import ZONA_CHILE
    from app.models import Mensaje, OrdenCompra, SaludComponente


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _p(sku, nombre, componentes=(), vendible=False):
    return {"sku": sku, "name": nombre, "sellable": vendible,
            "components": [{"sku": c, "req": 1} for c in componentes]}


CATALOGO = {p["sku"]: p for p in [
    _p("API-AMOXI-500", "Amoxicilina 500 mg (granel)"),
    _p("BLI-AMOXI-500", "Blíster amoxicilina 500 mg × 10 comprimidos", ["API-AMOXI-500"]),
    _p("KIT-RESP-ADULTO", "Kit de Atención Respiratoria Adulto", ["BLI-AMOXI-500"], True),
]}


def _salida_pedido(sku="KIT-RESP-ADULTO", cantidad=2, en=timedelta(hours=3)) -> str:
    local = (_ahora() + en).astimezone(ZONA_CHILE)
    return json.dumps({"analisis": "x", "es_pedido": True, "cumplible": True, "sku": sku,
                       "cantidad": cantidad, "entrega_local": f"{local:%Y-%m-%dT%H:%M}",
                       "en_minutos": None, "motivo": ""})


NO_PEDIDO = json.dumps({"analisis": "consulta", "es_pedido": False, "cumplible": False,
                        "sku": None, "cantidad": None, "entrega_local": None,
                        "en_minutos": None, "motivo": "consulta de estado"})


class BaseDB(unittest.TestCase):
    def setUp(self):
        # El procesador recorre todos los mensajes abiertos: se cierran los de tests anteriores
        with SessionLocal.begin() as s:
            s.execute(update(Mensaje).where(Mensaje.estado.in_(("pendiente", "respondiendo")))
                      .values(estado="sin_respuesta"))
        self.ocs: list[str] = []
        p = patch("app.mensajeria.procesador.catalogo", return_value=CATALOGO)
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(self._cerrar_ocs)

    def _cerrar_ocs(self):
        # Las OC de estos tests no deben llegar al procesador de OC de otros tests
        with SessionLocal.begin() as s:
            s.execute(update(OrdenCompra).where(OrdenCompra.canal == "mensajeria",
                                                OrdenCompra.estado == "nueva")
                      .values(estado="descartada"))

    def mensaje(self, hace: timedelta = timedelta(minutes=1), prefijo: str = "msg_") -> str:
        mid = f"{prefijo}{uuid.uuid4().hex[:16]}"
        self.assertTrue(registro.guardar(mid, "Farmacia Los Aromos", "+56 9 5555 0123",
                                         "Necesito dos kits respiratorios", _ahora() - hace))
        return mid

    def tick(self, salida=None, plataforma=None, modelo_error=None, por_tick=3):
        """Corre un tick con el modelo y la plataforma parcheados."""
        kw_modelo = {"side_effect": modelo_error} if modelo_error else {"return_value": salida}
        if isinstance(plataforma, (list, Exception)):
            kw_plat = {"side_effect": plataforma}
        else:
            kw_plat = {"return_value": plataforma}
        with patch("app.mensajeria.modelo.completar", **kw_modelo) as llm, \
             patch("app.messaging_client.responder", **kw_plat) as plat:
            procesador.procesar_pendientes(por_tick=por_tick)
        return llm, plat

    def envejecer(self, mid: str, segundos: int = 600):
        """Simula que paso la espera tras un fallo."""
        with SessionLocal.begin() as s:
            s.execute(update(Mensaje).where(Mensaje.id == mid).values(
                actualizado_en=_ahora() - timedelta(seconds=segundos)))

    def oc(self, oc_id: str) -> OrdenCompra | None:
        with SessionLocal() as s:
            return s.get(OrdenCompra, oc_id)


@unittest.skipUnless(TEST_DB, "TEST_DATABASE_URL no definido")
class WebhookTest(BaseDB):
    def setUp(self):
        super().setUp()
        app = FastAPI()
        app.include_router(webhook.router)
        self.cliente = TestClient(app)
        self.mid = f"msg_{uuid.uuid4().hex[:16]}"
        self.cuerpo = {"messageId": self.mid,
                       "sender": {"name": "Farmacia Los Aromos", "phone": "+56 9 5555 0123"},
                       "text": "Necesito dos kits", "receivedAt": "2026-10-27T16:05:00Z"}

    def post(self, cuerpo=None, token_ok=True):
        efecto = None if token_ok else oidc.TokenInvalido("firma invalida")
        with patch("app.mensajeria.webhook.oidc.verificar", side_effect=efecto,
                   return_value={"email": "x"}) as v:
            r = self.cliente.post("/api/messaging", json=cuerpo or self.cuerpo,
                                  headers={"Authorization": "Bearer t"})
        return r, v

    def test_token_invalido_responde_401_y_no_guarda(self):
        r, _ = self.post(token_ok=False)
        self.assertEqual(r.status_code, 401)
        self.assertIsNone(registro.get(self.mid))

    def test_verifica_audiencia_exacta_y_cuenta_de_la_plataforma(self):
        _, v = self.post()
        self.assertEqual(v.call_args.args, ("Bearer t", f"{config.PUBLIC_BASE_URL}/api/messaging",
                                            config.MESSAGING_OIDC_EMAIL))

    def test_guarda_el_mensaje_pendiente(self):
        r, _ = self.post()
        self.assertEqual(r.status_code, 200)
        m = registro.get(self.mid)
        self.assertEqual((m.estado, m.remitente, m.texto), ("pendiente", "Farmacia Los Aromos",
                                                            "Necesito dos kits"))
        self.assertEqual(m.recibido_en, datetime(2026, 10, 27, 16, 5, tzinfo=timezone.utc))

    def test_duplicado_responde_200_y_no_cambia_nada(self):
        self.post()
        r, _ = self.post({**self.cuerpo, "text": "otro texto"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["duplicado"])
        self.assertEqual(registro.get(self.mid).texto, "Necesito dos kits")

    def test_cuerpo_invalido_responde_400(self):
        r, _ = self.post({"messageId": self.mid})
        self.assertEqual(r.status_code, 400)
        self.assertIsNone(registro.get(self.mid))


@unittest.skipUnless(TEST_DB, "TEST_DATABASE_URL no definido")
class ProcesadorTest(BaseDB):
    def test_pedido_valido_se_registra_y_la_oc_entra_a_la_bandeja(self):
        mid = self.mensaje()
        oc_id = uuid.uuid4().hex[:24]
        _, plat = self.tick(_salida_pedido(), (200, {"orderId": oc_id}))
        enviado = plat.call_args.args
        self.assertEqual(enviado[0], mid)
        self.assertEqual(enviado[1]["status"], "order")
        self.assertEqual(enviado[1]["interpretation"]["sku"], "KIT-RESP-ADULTO")
        self.assertEqual(enviado[1]["interpretation"]["quantity"], 2)
        self.assertTrue(enviado[1]["interpretation"]["deliveryDate"].endswith("Z"))
        m = registro.get(mid)
        self.assertEqual((m.estado, m.oc_id), ("pedido", oc_id))
        self.assertEqual(m.respuesta, enviado[1])
        self.assertIn("crudo", m.interpretacion)
        self.assertTrue(m.decision["pasos"])
        oc = self.oc(oc_id)
        self.assertEqual((oc.canal, oc.origen_ref, oc.estado), ("mensajeria", mid, "nueva"))

    def test_no_pedido_se_descarta(self):
        mid = self.mensaje()
        _, plat = self.tick(NO_PEDIDO, (200, {"status": "discarded"}))
        self.assertEqual(plat.call_args.args[1]["status"], "discarded")
        self.assertIn("consulta de estado", plat.call_args.args[1]["reason"])
        self.assertEqual(registro.get(mid).estado, "descartado")

    def test_sku_que_no_es_kit_se_descarta_aunque_el_modelo_lo_diga(self):
        mid = self.mensaje()
        _, plat = self.tick(_salida_pedido(sku="BLI-AMOXI-500"), (200, {"status": "discarded"}))
        self.assertEqual(plat.call_args.args[1]["status"], "discarded")
        self.assertEqual(registro.get(mid).estado, "descartado")

    def test_caida_antes_de_la_respuesta_reenvia_el_mismo_cuerpo(self):
        mid = self.mensaje()
        self.tick(_salida_pedido(), httpx.ConnectError("caida"))
        m = registro.get(mid)
        self.assertEqual((m.estado, m.intentos), ("respondiendo", 1))
        cuerpo = m.respuesta
        self.envejecer(mid)
        oc_id = uuid.uuid4().hex[:24]
        llm, plat = self.tick(None, (200, {"orderId": oc_id}))
        llm.assert_not_called()  # no se vuelve a interpretar: se reenvia lo decidido
        self.assertEqual(plat.call_args.args[1], cuerpo)
        self.assertEqual(registro.get(mid).estado, "pedido")
        self.assertIsNotNone(self.oc(oc_id))

    def test_409_tras_caida_con_pedido_queda_pedido_con_error(self):
        mid = self.mensaje()
        self.tick(_salida_pedido(), httpx.ReadTimeout("sin respuesta"))
        self.envejecer(mid)
        self.tick(None, (409, {"message": "ya respondido"}))
        m = registro.get(mid)
        self.assertEqual(m.estado, "pedido")
        self.assertIn("409", m.ultimo_error)

    def test_409_con_descarte_queda_descartado(self):
        mid = self.mensaje()
        self.tick(NO_PEDIDO, (409, {}))
        self.assertEqual(registro.get(mid).estado, "descartado")

    def test_410_queda_sin_respuesta(self):
        mid = self.mensaje()
        self.tick(_salida_pedido(), (410, {}))
        self.assertEqual(registro.get(mid).estado, "sin_respuesta")

    def test_404_queda_sin_respuesta(self):
        mid = self.mensaje()
        self.tick(NO_PEDIDO, (404, {}))
        self.assertEqual(registro.get(mid).estado, "sin_respuesta")

    def test_422_al_registrar_se_descarta_con_el_motivo(self):
        mid = self.mensaje()
        _, plat = self.tick(_salida_pedido(), [
            (422, {"details": [{"field": "sku", "message": "no es kit vendible"}]}),
            (200, {"status": "discarded"})])
        self.assertEqual(plat.call_count, 2)
        self.assertEqual(plat.call_args.args[1]["status"], "discarded")
        self.assertIn("no es kit vendible", plat.call_args.args[1]["reason"])
        self.assertEqual(registro.get(mid).estado, "descartado")

    def test_error_5xx_se_reintenta(self):
        mid = self.mensaje()
        self.tick(NO_PEDIDO, (503, {}))
        m = registro.get(mid)
        self.assertEqual((m.estado, m.intentos), ("respondiendo", 1))

    def test_modelo_caido_se_reintenta_con_espera(self):
        mid = self.mensaje(hace=timedelta(minutes=5))
        llm, plat = self.tick(modelo_error=modelo.ModeloNoDisponible("429 presupuesto"))
        plat.assert_not_called()
        m = registro.get(mid)
        self.assertEqual((m.estado, m.intentos), ("pendiente", 1))
        llm, _ = self.tick(modelo_error=modelo.ModeloNoDisponible("sigue caido"))
        llm.assert_not_called()  # aun no pasa la espera
        self.envejecer(mid)
        _, plat = self.tick(NO_PEDIDO, (200, {"status": "discarded"}))
        self.assertEqual(registro.get(mid).estado, "descartado")

    def test_modelo_caido_hasta_el_limite_descarta_a_tiempo(self):
        mid = self.mensaje(hace=timedelta(minutes=26))
        llm, plat = self.tick(modelo_error=modelo.ModeloNoDisponible("caido"),
                              plataforma=(200, {"status": "discarded"}))
        llm.assert_not_called()
        self.assertEqual(plat.call_args.args[1],
                         {"status": "discarded", "reason": procesador.MOTIVO_SIN_INTERPRETAR})
        self.assertEqual(registro.get(mid).estado, "descartado")

    def salud_modelo(self):
        with SessionLocal() as s:
            return s.get(SaludComponente, procesador.SALUD_MODELO)

    def test_salud_registra_fallo_y_recuperacion_del_modelo(self):
        mid = self.mensaje()
        self.tick(modelo_error=modelo.ModeloNoDisponible("429 presupuesto agotado"))
        fallo = self.salud_modelo()
        self.assertIn("presupuesto agotado", fallo.ultimo_error)
        self.envejecer(mid)
        self.tick(NO_PEDIDO, (200, {"status": "discarded"}))
        sano = self.salud_modelo()
        self.assertGreater(sano.ultimo_ok, sano.ultimo_error_en)

    def test_inyeccion_que_pide_50_kits_se_descarta(self):
        mid = self.mensaje()
        _, plat = self.tick(_salida_pedido(cantidad=50), (200, {"status": "discarded"}))
        self.assertEqual(plat.call_args.args[1]["status"], "discarded")
        self.assertEqual(registro.get(mid).estado, "descartado")

    def test_salida_sin_json_cuenta_como_fallo(self):
        mid = self.mensaje()
        self.tick("no entendi", (200, {}))
        m = registro.get(mid)
        self.assertEqual((m.estado, m.intentos), ("pendiente", 1))

    def test_oc_anotada_sin_bandeja_se_completa_sin_llamar_a_la_plataforma(self):
        mid = self.mensaje()
        oc_id = uuid.uuid4().hex[:24]
        registro.preparar_respuesta(mid, None, {}, {"status": "order", "interpretation": {}})
        registro.anotar_oc(mid, oc_id, {"paso": "test"})
        _, plat = self.tick()
        plat.assert_not_called()
        self.assertEqual(registro.get(mid).estado, "pedido")
        self.assertEqual(self.oc(oc_id).origen_ref, mid)

    def test_mensaje_de_prueba_sin_orderid_queda_anotado_como_prueba(self):
        mid = self.mensaje(prefijo="test_")
        self.tick(_salida_pedido(), (200, {"orderId": None, "test": True}))
        m = registro.get(mid)
        self.assertEqual(m.estado, "pedido")
        self.assertIsNone(m.ultimo_error)
        self.assertTrue(any(e.get("test") for e in m.decision["eventos"]))

    def test_limite_de_mensajes_por_tick(self):
        for _ in range(4):
            self.mensaje()
        llm, _ = self.tick(NO_PEDIDO, (200, {"status": "discarded"}), por_tick=3)
        self.assertEqual(llm.call_count, 3)

    def test_otro_procesador_corriendo_salta_el_tick(self):
        self.mensaje()
        with engine.connect() as conn:
            conn.execute(text("SELECT pg_advisory_lock(:k)"), {"k": procesador.LOCK_MENSAJERIA})
            try:
                llm, _ = self.tick(NO_PEDIDO, (200, {}))
            finally:
                conn.execute(text("SELECT pg_advisory_unlock(:k)"),
                             {"k": procesador.LOCK_MENSAJERIA})
        llm.assert_not_called()


if __name__ == "__main__":
    unittest.main()
