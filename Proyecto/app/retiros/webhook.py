"""Aviso de retiro de lote (webhook de Farma Central) y registro para /recalls.

POST /api/recalls: mismas reglas que la mensajeria. Se verifica el token OIDC
(firma, emisor, audiencia exacta, vigencia y cuenta), se anota el retiro por
su recallId y se responde 200 de inmediato; el trabajo lo hace el worker.
Un aviso repetido responde 200 sin hacer nada.
"""
import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool

from app import oidc
from app.config import PUBLIC_BASE_URL, RECALLS_OIDC_EMAIL
from app.retiros import registro

log = logging.getLogger("retiros")

AUDIENCIA = f"{PUBLIC_BASE_URL}/api/recalls"

router = APIRouter()


@router.post("/api/recalls")
async def recibir_aviso(request: Request):
    # El token se revisa antes de leer el cuerpo: sin token valido no se mira nada
    authorization = request.headers.get("authorization")
    try:
        await run_in_threadpool(oidc.verificar, authorization, AUDIENCIA, RECALLS_OIDC_EMAIL)
    except oidc.TokenInvalido as e:
        log.warning("Aviso de retiro rechazado: %s", e)
        raise HTTPException(status_code=401, detail="token invalido") from e
    try:
        aviso = registro.aviso_desde_farma(await request.json())
    except ValueError as e:  # incluye JSON mal formado
        log.error("Aviso de retiro invalido: %s", e)
        raise HTTPException(status_code=400, detail=str(e)) from e
    nuevo = await run_in_threadpool(registro.recibir, aviso)
    if nuevo:
        log.warning("Retiro %s del lote %s recibido (plazo %s)",
                    aviso["id"], aviso["lote"], aviso["plazo"])
    return {"ok": True, "nuevo": nuevo}


@router.get("/api/recalls")
def listar_retiros():
    return registro.listar()


@router.get("/api/recalls/{retiro_id}")
def detalle_retiro(retiro_id: str):
    data = registro.detalle(retiro_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Retiro no encontrado")
    return data
