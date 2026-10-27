"""Lector de la casilla sFTP (Anexo 1 del enunciado E2).

El servidor no avisa: se revisa cada minuto. Cada revision abre una sesion y
la cierra siempre, tambien ante un error: las sesiones que quedan abiertas
ocupan cupos y al llegar al limite el servidor bloquea la casilla.

La llave del servidor se verifica contra keys/known_hosts (RejectPolicy):
si cambia, no se conecta.
"""
import logging
import posixpath
import stat
import time
from contextlib import contextmanager

import paramiko

from app.canales import formatos
from app.config import (SFTP_DIR, SFTP_HOST, SFTP_KNOWN_HOSTS, SFTP_PASSWORD, SFTP_PORT,
                        SFTP_USER)
from app.pedidos import bandeja

log = logging.getLogger("sftp")

MAX_BYTES = 64 * 1024  # una OC son unas pocas lineas de XML
RECIENTE_S = 120  # un archivo modificado hace menos que esto puede seguir escribiendose


@contextmanager
def _sesion():
    cliente = paramiko.SSHClient()
    try:
        cliente.load_host_keys(SFTP_KNOWN_HOSTS)
        cliente.set_missing_host_key_policy(paramiko.RejectPolicy())
        cliente.connect(SFTP_HOST, port=SFTP_PORT, username=SFTP_USER, password=SFTP_PASSWORD,
                        timeout=15, banner_timeout=15, auth_timeout=15,
                        allow_agent=False, look_for_keys=False)
        # sin esto, una red cortada sin aviso deja la lectura colgada para siempre
        cliente.get_transport().set_keepalive(15)
        canal = cliente.open_sftp()
        canal.get_channel().settimeout(30)
        try:
            yield canal
        finally:
            canal.close()
    finally:
        cliente.close()


def revisar(sesion=_sesion) -> int:
    """Lee los archivos nuevos de la casilla. Devuelve cuantas OC nuevas anoto."""
    nuevas = 0
    with sesion() as canal:
        modificados = {a.filename: (a.st_mtime or 0) for a in canal.listdir_attr(SFTP_DIR)
                       if stat.S_ISREG(a.st_mode)}
        nombres = list(modificados)
        for nombre in bandeja.archivos_no_leidos(nombres):
            with canal.open(posixpath.join(SFTP_DIR, nombre), "rb") as f:
                contenido = f.read(MAX_BYTES + 1)
            if len(contenido) > MAX_BYTES:
                bandeja.recibir_archivo(nombre, None, "archivo demasiado grande")
                log.error("Archivo %s demasiado grande: no se procesa", nombre)
                continue
            try:
                oc_id = formatos.parsear_xml(contenido)
            except ValueError as e:
                if time.time() - modificados[nombre] < RECIENTE_S:
                    # puede estar truncado porque aun se escribe: se reintenta
                    # en la proxima revision en vez de anotarlo como invalido
                    log.warning("Archivo %s reciente e ilegible (%s): se reintenta", nombre, e)
                    continue
                bandeja.recibir_archivo(nombre, None, str(e))
                log.error("Archivo %s invalido: %s", nombre, e)
                continue
            if bandeja.recibir_archivo(nombre, oc_id):
                nuevas += 1
                log.info("OC %s recibida por sFTP (%s)", oc_id, nombre)
    return nuevas
