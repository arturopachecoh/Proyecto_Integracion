"""Operaciones con Farma Central que dejan registro en custodia.

Cualquier script u orquestador que compre, fabrique o mueva productos debe usar
estas funciones, nunca llamar a farma_client directamente, para que nada quede
sin trazabilidad.
"""
import logging
import time
from collections import defaultdict
from contextlib import contextmanager

import httpx
from sqlalchemy import text

from app import custodia, farma_client
from app import espacios as esp
from app.db import engine
from app.pow import solve

log = logging.getLogger("operaciones")

MAX_INTENTOS = 3
LOCK_FABRICACION = 4_000_001  # id arbitrario del candado de Postgres
_catalogo: dict[str, dict] | None = None


class FaltanInsumos(Exception):
    def __init__(self, faltantes: dict[str, int]):
        self.faltantes = faltantes
        detalle = ", ".join(f"{sku}: faltan {n}" for sku, n in faltantes.items())
        super().__init__(f"No hay suficientes componentes ({detalle})")


class SinEspacio(Exception):
    """Farma Central rechazo un movimiento: el espacio de destino esta lleno."""


# ---------------------------------------------------------------------------
# Catalogo
# ---------------------------------------------------------------------------

def catalogo() -> dict[str, dict]:
    global _catalogo
    if _catalogo is None:
        _catalogo = {p["sku"]: p for p in farma_client.available_products()}
    return _catalogo


def tamano_lote(sku: str) -> int:
    return catalogo()[sku]["production"]["batch"]


def es_frio(sku: str) -> bool:
    return bool(catalogo()[sku]["storage"]["cold"])


def receta(sku: str, cantidad: int) -> dict[str, int]:
    """Cuanto de cada componente se necesita. Ej: receta("BLI-AMOXI-500", 3)
    -> {"API-AMOXI-500": 36, "EXC-LACTOSA-DC": 24, "LAM-BLISTER-PVC": 3}"""
    total = defaultdict(int)
    for c in catalogo()[sku]["components"]:
        total[c["sku"]] += c["req"] * cantidad
    return dict(total)


# ---------------------------------------------------------------------------
# Piezas comunes
# ---------------------------------------------------------------------------

def _validar_cantidad(sku: str, cantidad: int) -> None:
    lote = tamano_lote(sku)
    if cantidad <= 0 or cantidad % lote != 0:
        raise ValueError(f"{sku}: la cantidad {cantidad} debe ser multiplo de {lote}")


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


def mover(unidad_id: str, hacia: str) -> None:
    """Mueve una unidad en Farma Central y registra el traslado."""
    farma_client.move_product(unidad_id, esp.store_id(hacia))
    custodia.registrar_traslado(unidad_id, hacia)


@contextmanager
def _candado_fabricacion():
    """Impide que dos fabricaciones corran a la vez (elegirian las mismas unidades).
    Es un candado de Postgres: se libera solo si el proceso muere."""
    with engine.connect() as conn:
        if not conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": LOCK_FABRICACION}).scalar():
            raise RuntimeError("Ya hay otra fabricacion en curso; espera a que termine")
        try:
            yield
        finally:
            conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": LOCK_FABRICACION})


# ---------------------------------------------------------------------------
# Compra
# ---------------------------------------------------------------------------

def comprar(sku: str, cantidad: int) -> int:
    """Compra un insumo a Farma Central y lo registra en custodia.
    Devuelve el id de la solicitud registrada."""
    _validar_cantidad(sku, cantidad)
    if catalogo()[sku]["components"]:
        raise ValueError(f"{sku} no es un insumo: se fabrica, no se compra")

    resp, challenge_id = _pedir_con_pow(sku, cantidad)
    solicitud_id = custodia.registrar_compra(sku, cantidad, challenge_id, resp["availableAt"])
    log.info("Compra #%d: %d x %s, llega %s", solicitud_id, cantidad, sku, resp["availableAt"])
    return solicitud_id


# ---------------------------------------------------------------------------
# Fabricacion
# ---------------------------------------------------------------------------

def verificar_componentes(sku: str, cantidad: int) -> dict[str, list]:
    """Elige las unidades a usar para cada componente. Si falta algo, lanza
    FaltanInsumos con el detalle. No mueve ni modifica nada."""
    elegidas, faltantes = {}, {}
    for comp, necesarias in receta(sku, cantidad).items():
        disponibles = custodia.unidades_disponibles(comp)
        if len(disponibles) < necesarias:
            faltantes[comp] = necesarias - len(disponibles)
        else:
            elegidas[comp] = disponibles[:necesarias]
    if faltantes:
        raise FaltanInsumos(faltantes)
    return elegidas


def fabricar(sku: str, cantidad: int) -> int:
    """Fabrica `cantidad` unidades de `sku` (producto acondicionado o kit).

    1. Valida y elige las unidades (FEFO). Si falta algo, no hace nada.
    2. Mueve a acondicionamiento: primero las de ambiente, al final las frias.
    3. Resuelve el desafio y pide la fabricacion.
    4. Registra la fabricacion y sus consumos.

    No espera a que el producto llegue: lo registra el worker, que tambien
    lleva al frio los productos frios que nacen en acondicionamiento.
    Devuelve el id de la solicitud registrada.
    """
    _validar_cantidad(sku, cantidad)
    if not catalogo()[sku]["components"]:
        raise ValueError(f"{sku} es un insumo: se compra, no se fabrica")

    with _candado_fabricacion():
        elegidas = verificar_componentes(sku, cantidad)
        todas = [u for unidades in elegidas.values() for u in unidades]
        por_mover = [u for u in todas if u.espacio_actual != "packaging"]

        libres = esp.libres("packaging")
        if len(por_mover) > libres:
            raise RuntimeError(f"No cabe en acondicionamiento: hay que mover {len(por_mover)} "
                               f"y quedan {libres} espacios libres")

        # Las frias al final, para que pasen el menor tiempo fuera del frio
        por_mover.sort(key=lambda u: es_frio(u.sku))
        frias_movidas = []
        try:
            for u in por_mover:
                try:
                    mover(u.id, "packaging")
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 400:
                        raise SinEspacio(f"Acondicionamiento lleno al mover insumos de {sku}") from e
                    raise
                if es_frio(u.sku):
                    frias_movidas.append(u)
        except Exception:
            log.error("Fallo moviendo insumos para %s; devuelvo %d unidades frias a la camara",
                      sku, len(frias_movidas))
            _devolver_al_frio(frias_movidas)
            raise
        log.info("%d unidades movidas a acondicionamiento (%d ya estaban)",
                 len(por_mover), len(todas) - len(por_mover))

        try:
            resp, challenge_id = _pedir_con_pow(sku, cantidad)
        except httpx.HTTPStatusError as e:
            # Un 400 puede ser porque custodia cree tener unidades que Farma ya no
            # tiene: si no se sacan, se eligen otra vez y la fabricacion nunca resulta
            perdidas = _no_estan_en_farma(todas) if e.response.status_code == 400 else set()
            if perdidas:
                log.error("Fabricacion de %s rechazada: %d unidades ya no estan en Farma, "
                          "se sacan de custodia: %s", sku, len(perdidas), sorted(perdidas))
                custodia.registrar_vencidas(sorted(perdidas))
            _devolver_al_frio([u for u in frias_movidas if u.id not in perdidas])
            raise
        except Exception:
            _devolver_al_frio(frias_movidas)
            raise

        ids = [u.id for u in todas]
        try:
            solicitud_id = custodia.registrar_fabricacion(
                sku, cantidad, challenge_id, resp["availableAt"], ids)
        except Exception:
            # La API ya acepto la fabricacion: dejar todo en el log para corregir a mano
            log.critical("FABRICACION ACEPTADA PERO NO REGISTRADA: sku=%s cantidad=%d "
                         "challenge=%s llega=%s unidades=%s",
                         sku, cantidad, challenge_id, resp["availableAt"], ids)
            raise

        log.info("Fabricacion #%d: %d x %s, llega %s", solicitud_id, cantidad, sku,
                 resp["availableAt"])
        return solicitud_id


def _no_estan_en_farma(unidades) -> set[str]:
    """Ids de las unidades (ya movidas a acondicionamiento) que Farma no tiene ahi.
    Si no se puede consultar, no se marca nada."""
    store = esp.store_id("packaging")
    presentes: set[str] = set()
    try:
        for sku in {u.sku for u in unidades}:
            presentes |= {p["_id"] for p in farma_client.space_products(store, sku, limit=200) or []}
    except Exception:
        log.exception("No se pudo revisar acondicionamiento en Farma")
        return set()
    return {u.id for u in unidades} - presentes


def _devolver_al_frio(unidades) -> None:
    for u in unidades:
        destino = "cold" if esp.libres("cold") > 0 else "buffer"
        try:
            mover(u.id, destino)
        except Exception:
            log.exception("No se pudo devolver %s (%s) al frio", u.id, u.sku)