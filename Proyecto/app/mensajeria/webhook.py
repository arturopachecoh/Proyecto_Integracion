"""Webhook del canal de mensajeria: POST /api/messaging.

Verifica el token OIDC, anota el mensaje y confirma de inmediato (la
plataforma exige 2xx en menos de 15 s). La interpretacion corre despues, en
el procesador. Un mensaje repetido (mismo messageId) tambien responde 200.
"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError
from starlette.concurrency import run_in_threadpool

from app import config, oidc
from app.mensajeria import registro

log = logging.getLogger("mensajeria")

router = APIRouter()


class Remitente(BaseModel):
    name: str | None = Field(default=None, max_length=160)
    phone: str | None = Field(default=None, max_length=40)


class MensajeIn(BaseModel):
    messageId: str = Field(min_length=1, max_length=80)
    sender: Remitente = Field(default_factory=Remitente)
    text: str = Field(max_length=10_000)
    receivedAt: datetime


def audiencia() -> str:
    return f"{config.PUBLIC_BASE_URL}/api/messaging"


@router.post("/api/messaging")
async def recibir_mensaje(request: Request):
    # Primero la autenticacion: un request sin token valido no merece mas
    try:
        await run_in_threadpool(oidc.verificar, request.headers.get("authorization"),
                                audiencia(), config.MESSAGING_OIDC_EMAIL)
    except oidc.TokenInvalido as e:
        log.warning("Webhook de mensajeria rechazado: %s", e)
        return JSONResponse({"error": "no autorizado"}, status_code=401)

    try:
        m = MensajeIn.model_validate(await request.json())
    except (ValueError, ValidationError) as e:
        log.warning("Webhook de mensajeria con cuerpo invalido: %s", e)
        return JSONResponse({"error": "cuerpo invalido"}, status_code=400)

    recibido = m.receivedAt if m.receivedAt.tzinfo else m.receivedAt.replace(tzinfo=timezone.utc)
    nuevo = await run_in_threadpool(registro.guardar, m.messageId, m.sender.name,
                                    m.sender.phone, m.text, recibido)
    log.info("Mensaje %s %s", m.messageId, "recibido" if nuevo else "repetido")
    return {"ok": True, "messageId": m.messageId, "duplicado": not nuevo}
