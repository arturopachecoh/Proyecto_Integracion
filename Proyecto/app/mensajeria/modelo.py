"""Cliente del gateway de modelos de lenguaje (API compatible con OpenAI).

Un solo intento por llamada: si falla, el procesador reintenta en ticks
siguientes con espera creciente, hasta el plazo del mensaje.
"""
import logging

import httpx

from app import config

log = logging.getLogger("mensajeria")
_aviso_sin_configurar = False

TIMEOUT_S = 40
MAX_TOKENS = 600


class ModeloNoDisponible(Exception):
    """El modelo no respondio algo usable: timeout, error HTTP, presupuesto agotado."""


def _url(base: str) -> str:
    base = base.rstrip("/")
    return base if base.endswith("/chat/completions") else f"{base}/chat/completions"


def _post(cuerpo: dict) -> httpx.Response:
    headers = {"Authorization": f"Bearer {config.LLM_API_KEY}"} if config.LLM_API_KEY else {}
    try:
        return httpx.post(_url(config.LLM_BASE_URL), json=cuerpo, headers=headers,
                          timeout=TIMEOUT_S)
    except httpx.HTTPError as e:
        raise ModeloNoDisponible(f"sin respuesta del modelo: {e!r}") from e


def completar(mensajes: list[dict]) -> str:
    """Devuelve el texto que respondio el modelo."""
    global _aviso_sin_configurar
    if not config.LLM_BASE_URL or not config.LLM_MODEL:
        if not _aviso_sin_configurar:
            # Una vez por arranque: sin modelo todos los mensajes terminan descartados
            log.error("LLM_BASE_URL o LLM_MODEL no configurados: no se pueden interpretar "
                      "mensajes")
            _aviso_sin_configurar = True
        raise ModeloNoDisponible("LLM_BASE_URL o LLM_MODEL no configurados")
    minimo = {"model": config.LLM_MODEL, "messages": mensajes}
    r = _post({**minimo, "temperature": 0, "max_tokens": MAX_TOKENS,
               "response_format": {"type": "json_object"}})
    if r.status_code == 400:
        # Algunos modelos no aceptan response_format, temperature o max_tokens (los de
        # razonamiento): se reintenta con lo minimo; el prompt igual pide solo JSON
        log.warning("El modelo respondio 400, se reintenta sin parametros opcionales: %s",
                    r.text[:300])
        r = _post(minimo)
    if r.status_code != 200:
        raise ModeloNoDisponible(f"modelo respondio {r.status_code}: {r.text[:300]}")
    try:
        contenido = r.json()["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as e:
        raise ModeloNoDisponible(f"respuesta del modelo sin contenido: {r.text[:300]}") from e
    if not isinstance(contenido, str) or not contenido.strip():
        raise ModeloNoDisponible("el modelo respondio vacio")
    return contenido
