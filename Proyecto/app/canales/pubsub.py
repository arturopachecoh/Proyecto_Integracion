"""Lector de Pub/Sub por suscripcion pull (API REST de Google).

Pull en vez de push: si el servidor esta caido, los mensajes esperan en
Google. El ack se envia recien cuando la OC quedo guardada en la base; si
algo falla antes, Google reenvia el mensaje y la bandeja lo descarta por
clave primaria.

Un mensaje que no se puede leer se registra en el log con su contenido y se
confirma igual: reenviarlo para siempre no lo arregla y bloquearia la cola.
"""
import base64
import binascii
import logging
from pathlib import Path

import google.auth.transport.requests
import httpx
from google.oauth2 import service_account

from app.canales import formatos
from app.config import PUBSUB_KEY_FILE, PUBSUB_SUBSCRIPTION
from app.pedidos import bandeja

log = logging.getLogger("pubsub")

API = "https://pubsub.googleapis.com/v1"
SCOPES = ["https://www.googleapis.com/auth/pubsub"]

_credenciales = None


def habilitado() -> bool:
    return Path(PUBSUB_KEY_FILE).exists()


def _token() -> str:
    global _credenciales
    if _credenciales is None:
        _credenciales = service_account.Credentials.from_service_account_file(
            PUBSUB_KEY_FILE, scopes=SCOPES)
    if not _credenciales.valid:
        _credenciales.refresh(google.auth.transport.requests.Request())
    return _credenciales.token


def _post(ruta: str, cuerpo: dict, timeout: float = 30) -> dict:
    r = httpx.post(f"{API}/{ruta}", json=cuerpo, timeout=timeout,
                   headers={"Authorization": f"Bearer {_token()}"})
    r.raise_for_status()
    return r.json() if r.content else {}


def revisar(max_mensajes: int = 20) -> int:
    """Trae mensajes pendientes, anota sus OC y los confirma. Devuelve cuantas OC nuevas."""
    respuesta = _post(f"{PUBSUB_SUBSCRIPTION}:pull", {"maxMessages": max_mensajes}, timeout=40)
    nuevas = 0
    ack_ids: list[str] = []
    for recibido in respuesta.get("receivedMessages", []):
        mensaje = recibido["message"]
        try:
            data = base64.b64decode(mensaje.get("data", ""))
            oc_id = formatos.parsear_mensaje(data, mensaje.get("attributes") or {})
        except (ValueError, binascii.Error) as e:
            log.error("Mensaje %s ilegible, se confirma sin procesar: %s",
                      mensaje.get("messageId"), e)
            ack_ids.append(recibido["ackId"])
            continue
        if bandeja.recibir(oc_id, "pubsub", mensaje.get("messageId")):
            nuevas += 1
            log.info("OC %s recibida por Pub/Sub (%s)", oc_id, mensaje.get("messageId"))
        ack_ids.append(recibido["ackId"])
    if ack_ids:
        _post(f"{PUBSUB_SUBSCRIPTION}:acknowledge", {"ackIds": ack_ids})
    return nuevas
