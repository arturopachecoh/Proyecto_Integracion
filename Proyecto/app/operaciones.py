"""Operaciones con Farma Central que dejan registro en custodia.

Cualquier script u orquestador que compre o fabrique debe usar estas funciones,
nunca llamar a farma_client directamente, para que nada quede sin trazabilidad.
"""
import logging
import time

import httpx

from app import custodia, farma_client
from app.pow import solve

log = logging.getLogger("operaciones")

MAX_INTENTOS = 3
_catalogo: dict[str, dict] | None = None


def catalogo() -> dict[str, dict]:
    global _catalogo
    if _catalogo is None:
        _catalogo = {p["sku"]: p for p in farma_client.available_products()}
    return _catalogo


def tamano_lote(sku: str) -> int:
    return catalogo()[sku]["production"]["batch"]


def _pedir_con_pow(sku: str, cantidad: int) -> tuple[dict, str]:
    """Pide desafio, lo resuelve y hace POST /products.
    Reintenta si el desafio expira o ya fue usado (409).
    Devuelve (respuesta de la API, challenge_id)."""
    for intento in range(1, MAX_INTENTOS + 1):
        ch = farma_client.fabrication_challenge(sku, cantidad)
        t0 = time.time()
        nonce = solve(ch["prefix"], ch["difficulty"])
        if nonce is None:
            log.warning("Desafio de %s no resuelto a tiempo (intento %d)", sku, intento)
            continue
        log.info("PoW %s: %d bits en %.2fs", sku, ch["difficulty"], time.time() - t0)
        try:
            resp = farma_client.request_products(sku, cantidad, ch["challengeId"], nonce)
            return resp, ch["challengeId"]
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 409:
                log.warning("Desafio expirado o usado (intento %d), pido otro", intento)
                continue
            raise
    raise RuntimeError(f"No se pudo completar la solicitud de {sku} tras {MAX_INTENTOS} intentos")


def comprar(sku: str, cantidad: int) -> int:
    """Compra un insumo a Farma Central y lo registra en custodia.
    Devuelve el id de la solicitud registrada."""
    lote = tamano_lote(sku)
    if cantidad <= 0 or cantidad % lote != 0:
        raise ValueError(f"{sku}: la cantidad {cantidad} debe ser multiplo de {lote}")
    if catalogo()[sku]["components"]:
        raise ValueError(f"{sku} no es un insumo: se fabrica, no se compra")

    resp, challenge_id = _pedir_con_pow(sku, cantidad)
    solicitud_id = custodia.registrar_compra(sku, cantidad, challenge_id, resp["availableAt"])
    log.info("Compra #%d: %d x %s, llega %s", solicitud_id, cantidad, sku, resp["availableAt"])
    return solicitud_id