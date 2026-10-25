"""Stock comprometido con OC y stock que puede vender el portal.

Las OC tienen prioridad sobre el portal: el portal solo vende lo que esta
sobre el minimo de cada kit y no esta comprometido con una OC aceptada.
"""
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, text

from app import custodia
from app.config import STOCK_MINIMO, STOCK_MINIMO_DEFAULT
from app.db import SessionLocal, engine
from app.models import OrdenCompra, Solicitud, VentaUnidad

# Mismo id que usaba el candado de ventas del portal: portal y OC deciden
# sobre el mismo stock, asi que comparten candado
LOCK_STOCK = 4_000_003
ESTADOS_COMPROMETIDOS = ("aceptando", "aceptada")


@contextmanager
def candado_stock(esperar_s: float = 0):
    """Un solo proceso a la vez reserva stock (portal u OC). Es un candado de
    Postgres: se libera solo si el proceso muere. Si no se obtiene en
    esperar_s segundos, levanta RuntimeError."""
    limite = time.monotonic() + esperar_s
    with engine.connect() as conn:
        while not conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": LOCK_STOCK}).scalar():
            if time.monotonic() >= limite:
                raise RuntimeError("Hay otra operacion de stock en curso; reintenta")
            time.sleep(0.2)
        try:
            yield
        finally:
            conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": LOCK_STOCK})


def parsear_minimos(texto: str) -> dict[str, int]:
    """Lee "KIT-A=2,KIT-B=4". Un error de formato detiene el arranque:
    es mejor no partir que partir con minimos equivocados."""
    minimos: dict[str, int] = {}
    for parte in (p.strip() for p in texto.split(",")):
        if not parte:
            continue
        sku, sep, n = parte.partition("=")
        sku, n = sku.strip(), n.strip()
        if not sep or not sku or not n.isdigit():
            raise ValueError(f"STOCK_MINIMO mal escrito: {parte!r} (se espera SKU=N)")
        minimos[sku] = int(n)
    return minimos


_MINIMOS = parsear_minimos(STOCK_MINIMO)


def minimo(sku: str) -> int:
    return _MINIMOS.get(sku, STOCK_MINIMO_DEFAULT)


def comprometido(sku: str) -> int:
    """Unidades prometidas a OC aceptadas que todavia no tienen unidad asignada.
    Sin esto, una misma unidad en camino se contaria para varias OC."""
    with SessionLocal() as s:
        filas = s.execute(
            select(OrdenCompra.cantidad, OrdenCompra.venta_id)
            .where(OrdenCompra.sku == sku, OrdenCompra.estado.in_(ESTADOS_COMPROMETIDOS))
        ).all()
        total = 0
        for cantidad, venta_id in filas:
            asignadas = 0
            if venta_id is not None:
                asignadas = s.scalar(select(func.count()).select_from(VentaUnidad)
                                     .where(VentaUnidad.venta_id == venta_id)) or 0
            total += max(0, (cantidad or 0) - asignadas)
        return total


def en_camino_antes(sku: str, limite: datetime,
                    max_atraso: timedelta = timedelta(minutes=30)) -> int:
    """Unidades pedidas (compra o fabricacion) que llegan antes de `limite`.
    Igual que custodia.en_camino, las atrasadas mas de max_atraso se dan por perdidas."""
    ahora = datetime.now(timezone.utc)
    with SessionLocal() as s:
        return s.scalar(
            select(func.coalesce(func.sum(Solicitud.cantidad), 0))
            .where(Solicitud.sku == sku, Solicitud.estado == "pendiente",
                   Solicitud.llega_en <= limite, Solicitud.llega_en > ahora - max_atraso)
        ) or 0


def vendible_portal(sku: str) -> int:
    return max(0, custodia.stock_disponible(sku) - minimo(sku) - comprometido(sku))
