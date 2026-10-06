"""Orquestador de produccion: fabrica N unidades de uno o mas kits.

No sigue un plan fijo. Da vueltas y en cada vuelta mira el estado actual
(stock, lo que viene en camino, el espacio libre) y hace lo que se pueda:

  1. Saca de acondicionamiento los kits que ya nacieron (a la bodega).
  2. Arma los kits para los que ya hay intermedios.
  3. Fabrica los intermedios que faltan, si ya llegaron sus insumos.
  4. Compra los insumos que faltan (descontando lo que viene en camino).

Si algo se atrasa (una compra que llega tarde), simplemente lo hace en la
vuelta siguiente. Para limitar compras grandes que caerian en la bodega
externa, trabaja de a "tandas" de kits.

En la Entrega 2 este mismo codigo puede correr solo, con metas que salgan
de las ordenes de compra en vez de la terminal.
"""
import logging
import math
import time
from collections import defaultdict
from contextlib import contextmanager

from sqlalchemy import text

from app import custodia
from app import espacios as esp
from app.db import engine
from app.operaciones import (FaltanInsumos, catalogo, comprar, es_frio, fabricar, mover,
                             receta, tamano_lote)

log = logging.getLogger("produccion")

ESPERA = 20                 # segundos entre vueltas
LOCK_PRODUCCION = 4_000_002


@contextmanager
def _candado():
    """Dos orquestadores a la vez comprarian dos veces lo mismo."""
    with engine.connect() as conn:
        if not conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": LOCK_PRODUCCION}).scalar():
            raise RuntimeError("Ya hay otro proceso de produccion corriendo")
        try:
            yield
        finally:
            conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": LOCK_PRODUCCION})


# ---------------------------------------------------------------------------
# Planificacion
# ---------------------------------------------------------------------------

def _profundidad(sku: str) -> int:
    comps = catalogo()[sku]["components"]
    return 0 if not comps else 1 + max(_profundidad(c["sku"]) for c in comps)


def _redondear(sku: str, cantidad: int) -> int:
    lote = tamano_lote(sku)
    return math.ceil(cantidad / lote) * lote


def planificar(kits: dict[str, int]) -> dict[str, int]:
    """Cuanto falta pedir de cada SKU (fabricar o comprar) para hacer estos kits.

    kits: {sku_kit: cantidad a fabricar}. Para los niveles de abajo descuenta
    lo que ya hay en stock y lo que viene en camino, y redondea al tamano de lote.
    Se recorre de arriba hacia abajo (kits -> intermedios -> insumos) para que
    la demanda de un insumo compartido sume la de todos los productos que lo usan.
    """
    necesidad = defaultdict(int, kits)
    faltante = {}
    for sku in sorted(catalogo(), key=_profundidad, reverse=True):
        if necesidad[sku] <= 0:
            continue
        if sku in kits:
            deficit = necesidad[sku]
        else:
            tengo = len(custodia.unidades_disponibles(sku)) + custodia.en_camino(sku)
            deficit = max(0, necesidad[sku] - tengo)
        if deficit == 0:
            continue
        pedir = _redondear(sku, deficit)
        faltante[sku] = pedir
        for comp, n in receta(sku, pedir).items():
            necesidad[comp] += n
    return faltante


def _cuantos_caben(sku: str, maximo: int) -> int:
    """Mayor multiplo del lote <= maximo cuyos componentes caben en acondicionamiento."""
    lote = tamano_lote(sku)
    huella_lote = sum(receta(sku, lote).values())
    lotes = min(maximo // lote, esp.libres("packaging") // huella_lote)
    return max(0, lotes) * lote


def _cuantos_alcanzan(sku: str, maximo: int) -> int:
    """Cuantos se pueden fabricar con el stock actual (multiplo del lote)."""
    lote = tamano_lote(sku)
    posibles = min(len(custodia.unidades_disponibles(c)) // n
                   for c, n in receta(sku, 1).items())
    return (min(posibles, maximo) // lote) * lote


# ---------------------------------------------------------------------------
# Acciones de cada vuelta
# ---------------------------------------------------------------------------

def _despejar(skus: set[str]) -> int:
    """Saca de acondicionamiento las unidades de estos SKU que nacieron ahi.
    Los frios los deja: de esos se encarga el worker (a la camara)."""
    movidas = 0
    for u in custodia.nacidas_en_acondicionamiento(skus):
        if es_frio(u.sku):
            continue
        try:
            mover(u.id, "bodega")
            movidas += 1
        except Exception:
            log.exception("No se pudo sacar %s de acondicionamiento", u.id)
    if movidas:
        log.info("Despejadas %d unidades de acondicionamiento a la bodega", movidas)
    return movidas


def _liberar_buffer(maximo: int = 100) -> int:
    """La bodega externa cobra por hora: lo que no requiere frio se pasa a la
    bodega principal (gratis). Lo refrigerado se queda si la camara esta llena."""
    libres = esp.libres("bodega")
    movidas = 0
    for u in custodia.unidades_en("buffer"):
        if movidas >= min(maximo, libres):
            break
        if es_frio(u.sku):
            continue
        try:
            mover(u.id, "bodega")
            movidas += 1
        except Exception:
            log.exception("No se pudo sacar %s de la bodega externa", u.id)
    if movidas:
        log.info("Sacadas %d unidades de la bodega externa a la bodega principal", movidas)
    return movidas


def _intentar_fabricar(sku: str, maximo: int) -> int:
    """Fabrica lo mas que se pueda de sku (hasta maximo). Devuelve cuantos pidio."""
    cantidad = min(_cuantos_alcanzan(sku, maximo), _cuantos_caben(sku, maximo))
    if cantidad <= 0:
        return 0
    try:
        fabricar(sku, cantidad)
        return cantidad
    except FaltanInsumos:
        return 0  # algo cambio entre el calculo y la fabricacion; reintenta la proxima vuelta
    except Exception:
        log.exception("Fallo fabricando %d x %s", cantidad, sku)
        return 0


def producir(objetivos: dict[str, int], tanda: int = 10, max_horas: float = 12) -> dict[str, int]:
    """Fabrica objetivos = {kit: cantidad}. Devuelve cuantos se pidieron de cada kit."""
    for kit, n in objetivos.items():
        if not catalogo()[kit]["sellable"]:
            raise ValueError(f"{kit} no es un kit")
        if n % tamano_lote(kit):
            raise ValueError(f"{kit}: {n} no es multiplo del lote {tamano_lote(kit)}")

    kits = set(objetivos)
    pedidos = defaultdict(int)
    limite = time.time() + max_horas * 3600

    with _candado():
        while True:
            restantes = {k: n - pedidos[k] for k, n in objetivos.items() if n > pedidos[k]}
            if not restantes:
                break
            if time.time() > limite:
                log.error("Se alcanzo el limite de %s horas; quedan %s", max_horas, restantes)
                break

            _despejar(kits)
            _liberar_buffer()

            # 1. Kits: armar todo lo que alcance
            for kit, r in restantes.items():
                pedidos[kit] += _intentar_fabricar(kit, r)

            # 2. Planificar la tanda actual con lo que queda
            en_tanda = {k: min(tanda, objetivos[k] - pedidos[k])
                        for k in objetivos if objetivos[k] > pedidos[k]}
            plan = planificar(en_tanda)

            # 3. Intermedios (primero los de nivel mas alto)
            sin_espacio = False
            for sku in sorted(plan, key=_profundidad, reverse=True):
                if sku in kits or not catalogo()[sku]["components"]:
                    continue
                if _intentar_fabricar(sku, plan[sku]) == 0 and _cuantos_caben(sku, plan[sku]) == 0:
                    sin_espacio = True

            # Si acondicionamiento esta lleno de intermedios esperando, se sacan a bodega
            if sin_espacio and not any(_cuantos_alcanzan(k, 1) for k in restantes):
                intermedios = {s for s in catalogo() if catalogo()[s]["components"] and s not in kits}
                _despejar(intermedios)

            # 4. Insumos: comprar lo que falta y no viene en camino
            for sku, cantidad in plan.items():
                if not catalogo()[sku]["components"]:
                    try:
                        comprar(sku, cantidad)
                    except Exception:
                        log.exception("Fallo comprando %d x %s", cantidad, sku)

            avance = ", ".join(f"{k} {pedidos[k]}/{n}" for k, n in objetivos.items())
            log.info("Avance: %s", avance)
            time.sleep(ESPERA)

        # Esperar que nazcan los ultimos kits y sacarlos de acondicionamiento
        log.info("Kits pedidos. Esperando que lleguen los ultimos para despejar...")
        fin = time.time() + 15 * 60
        while time.time() < fin and any(custodia.en_camino(k) for k in kits):
            time.sleep(ESPERA)
        time.sleep(ESPERA)  # que el worker alcance a registrarlos
        _despejar(kits)
        _liberar_buffer(maximo=10_000)

    log.info("Produccion terminada: %s", dict(pedidos))
    return dict(pedidos)
