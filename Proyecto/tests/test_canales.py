"""Tests de los lectores de canales (sin red ni Postgres)."""
from __future__ import annotations

import base64
import io
import json
import os
import time
import unittest
from contextlib import contextmanager
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://farma:x@localhost/farma")

from app.canales import formatos, sftp  # noqa: E402
from app.canales import pubsub  # noqa: E402

OC = "64abc123def456789012abcd"
XML = f"""<?xml version="1.0" encoding="UTF-8"?>
<order><id>{OC}</id><sku>KIT-RESP-ADULTO</sku><qty>2</qty></order>""".encode()


class FormatosTest(unittest.TestCase):
    def test_xml_del_anexo(self):
        self.assertEqual(formatos.parsear_xml(XML), OC)

    def test_xml_mal_formado(self):
        with self.assertRaises(ValueError):
            formatos.parsear_xml(b"<order><id>")

    def test_xml_con_id_invalido(self):
        with self.assertRaises(ValueError):
            formatos.parsear_xml(b"<order><id>no-es-un-id</id></order>")

    def test_xml_con_entidades_se_rechaza(self):
        bomba = b'<?xml version="1.0"?><!DOCTYPE a [<!ENTITY b "x">]><order><id>&b;</id></order>'
        with self.assertRaises(ValueError):
            formatos.parsear_xml(bomba)

    def test_mensaje_json_xml_o_id_solo(self):
        for data in (json.dumps({"id": OC}).encode(), json.dumps({"orderId": OC}).encode(),
                     XML, OC.encode()):
            with self.subTest(data=data[:20]):
                self.assertEqual(formatos.parsear_mensaje(data, {}), OC)

    def test_mensaje_con_id_en_atributos(self):
        self.assertEqual(formatos.parsear_mensaje(b"", {"orderId": OC}), OC)

    def test_id_con_salto_de_linea_o_largo_no_pasa(self):
        # JSON con salto de linea final: se normaliza al id de 24
        self.assertEqual(formatos.parsear_mensaje(json.dumps({"id": OC + "\n"}).encode(), {}), OC)
        # 25 caracteres: se rechaza
        with self.assertRaises(ValueError):
            formatos.parsear_mensaje(json.dumps({"id": OC + "a"}).encode(), {})

    def test_mensaje_sin_id(self):
        with self.assertRaises(ValueError):
            formatos.parsear_mensaje(b'{"hola": 1}', {})


class FakeAttr:
    def __init__(self, nombre, mtime=0):
        self.filename = nombre
        self.st_mtime = mtime  # por defecto antiguo
        self.st_mode = 0o100644  # archivo regular


class FakeSftp:
    def __init__(self, archivos: dict[str, bytes], mtimes: dict[str, float] | None = None):
        self.archivos = archivos
        self.mtimes = mtimes or {}
        self.abiertos: list[str] = []

    def listdir_attr(self, ruta):
        return [FakeAttr(n, self.mtimes.get(n, 0)) for n in self.archivos]

    def open(self, ruta, modo):
        nombre = ruta.rsplit("/", 1)[-1]
        self.abiertos.append(nombre)
        return io.BytesIO(self.archivos[nombre])


class SftpTest(unittest.TestCase):
    def _sesion(self, fake, cerrada: list):
        @contextmanager
        def sesion():
            try:
                yield fake
            finally:
                cerrada.append(True)
        return sesion

    def test_lee_solo_los_nuevos_y_cierra_la_sesion(self):
        fake = FakeSftp({"a.xml": XML, "b.xml": XML})
        cerrada: list = []
        with patch.object(sftp.bandeja, "archivos_no_leidos", return_value=["b.xml"]), \
             patch.object(sftp.bandeja, "recibir_archivo", return_value=True) as recibir:
            self.assertEqual(sftp.revisar(sesion=self._sesion(fake, cerrada)), 1)
        self.assertEqual(fake.abiertos, ["b.xml"])
        recibir.assert_called_once_with("b.xml", OC)
        self.assertEqual(cerrada, [True])

    def test_archivo_invalido_se_anota_con_su_error(self):
        fake = FakeSftp({"malo.xml": b"<nada"})
        with patch.object(sftp.bandeja, "archivos_no_leidos", return_value=["malo.xml"]), \
             patch.object(sftp.bandeja, "recibir_archivo", return_value=False) as recibir:
            sftp.revisar(sesion=self._sesion(fake, []))
        nombre, oc_id, error = recibir.call_args.args
        self.assertEqual((nombre, oc_id), ("malo.xml", None))
        self.assertIn("XML", error)

    def test_truncado_reciente_no_se_anota_y_antiguo_si(self):
        ahora = time.time()
        fake = FakeSftp({"nuevo.xml": b"<order><id>", "viejo.xml": b"<order><id>"},
                        {"nuevo.xml": ahora - 5, "viejo.xml": ahora - 600})
        with patch.object(sftp.bandeja, "archivos_no_leidos",
                          return_value=["nuevo.xml", "viejo.xml"]), \
             patch.object(sftp.bandeja, "recibir_archivo", return_value=False) as recibir:
            sftp.revisar(sesion=self._sesion(fake, []))
        recibir.assert_called_once()
        self.assertEqual(recibir.call_args.args[0], "viejo.xml")
        self.assertIn("XML", recibir.call_args.args[2])

    def test_error_al_leer_igual_cierra_la_sesion(self):
        fake = FakeSftp({"a.xml": XML})
        fake.open = lambda *a: (_ for _ in ()).throw(OSError("se corto"))
        cerrada: list = []
        with patch.object(sftp.bandeja, "archivos_no_leidos", return_value=["a.xml"]):
            with self.assertRaises(OSError):
                sftp.revisar(sesion=self._sesion(fake, cerrada))
        self.assertEqual(cerrada, [True])


def _msg(ack: str, data: bytes, mid: str = "m1") -> dict:
    return {"ackId": ack, "message": {"messageId": mid, "attributes": {},
                                      "data": base64.b64encode(data).decode()}}


class PubsubTest(unittest.TestCase):
    def setUp(self):
        p = patch.object(pubsub, "_token", return_value="t")
        p.start()
        self.addCleanup(p.stop)

    def test_ack_solo_despues_de_guardar(self):
        orden: list[str] = []
        recibidos = {"receivedMessages": [_msg("a1", OC.encode())]}

        def post(ruta, cuerpo, timeout=30):
            orden.append(ruta.rsplit(":", 1)[-1])
            return recibidos if ruta.endswith(":pull") else {}

        with patch.object(pubsub, "_post", side_effect=post), \
             patch.object(pubsub.bandeja, "recibir",
                          side_effect=lambda *a: orden.append("guardar") or True):
            self.assertEqual(pubsub.revisar(), 1)
        self.assertEqual(orden, ["pull", "guardar", "acknowledge"])

    def test_si_falla_al_guardar_no_hace_ack(self):
        recibidos = {"receivedMessages": [_msg("a1", OC.encode())]}
        with patch.object(pubsub, "_post", return_value=recibidos) as post, \
             patch.object(pubsub.bandeja, "recibir", side_effect=RuntimeError("db caida")):
            with self.assertRaises(RuntimeError):
                pubsub.revisar()
        self.assertEqual(post.call_count, 1)  # solo el pull

    def test_mensaje_ilegible_se_confirma_para_no_repetirlo(self):
        recibidos = {"receivedMessages": [_msg("a1", b'{"x": 1}')]}
        llamadas: list = []
        with patch.object(pubsub, "_post", side_effect=lambda r, c, timeout=30:
                          llamadas.append((r, c)) or (recibidos if r.endswith(":pull") else {})):
            self.assertEqual(pubsub.revisar(), 0)
        self.assertEqual(llamadas[-1][1], {"ackIds": ["a1"]})

    def test_base64_roto_se_trata_como_ilegible(self):
        roto = {"ackId": "a1", "message": {"messageId": "m1", "attributes": {}, "data": "abc"}}
        llamadas: list = []
        with patch.object(pubsub, "_post", side_effect=lambda r, c, timeout=30:
                          llamadas.append((r, c)) or ({"receivedMessages": [roto]}
                                                      if r.endswith(":pull") else {})):
            self.assertEqual(pubsub.revisar(), 0)
        self.assertEqual(llamadas[-1][1], {"ackIds": ["a1"]})

    def test_sin_mensajes_no_hace_ack(self):
        with patch.object(pubsub, "_post", return_value={}) as post:
            self.assertEqual(pubsub.revisar(), 0)
        self.assertEqual(post.call_count, 1)


if __name__ == "__main__":
    unittest.main()
