"""Regla B de aceptacion de OC (seccion 6 del diseno, docs/04).

Se acepta si lo que hay en stock, mas lo que llega antes del vencimiento con
margen, menos lo ya prometido a otras OC, cubre la cantidad pedida.
"""
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone

from app import custodia, stock
from app.config import FARMA_GROUP, MARGEN_DESPACHO_MIN

MARGEN_DESPACHO = timedelta(minutes=MARGEN_DESPACHO_MIN)


def _fecha(iso: str | None) -> datetime | None:
    """Fecha ISO de la API. Si viene sin zona horaria se asume UTC."""
    if not iso:
        return None
    f = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return f if f.tzinfo is not None else f.replace(tzinfo=timezone.utc)


@dataclass(frozen=True)
class Evaluacion:
    sku: str
    cantidad: int
    stock: int
    en_camino: int
    comprometido: int

    @property
    def disponible(self) -> int:
        return self.stock + self.en_camino - self.comprometido

    @property
    def acepta(self) -> bool:
        return self.disponible >= self.cantidad

    @property
    def reservar_ahora(self) -> int:
        """Unidades que se reservan al aceptar: las que hay en stock y no estan
        prometidas a OC anteriores. El resto lo asigna el despachador al nacer."""
        return max(0, min(self.cantidad, self.stock - self.comprometido))

    def como_dict(self) -> dict:
        return {**asdict(self), "disponible": self.disponible, "acepta": self.acepta,
                "reservar_ahora": self.reservar_ahora}


def validar_oc(oc: dict, ahora: datetime, es_kit) -> tuple[str | None, str | None]:
    """Revisa la OC oficial antes de mirar el stock. Devuelve (accion, motivo):
    - ("descartar", ...): no se le puede responder (no es nuestra o ya no esta creada);
    - ("rechazar", ...): es nuestra y esta creada, pero no se puede cumplir;
    - (None, None): pasa a la regla de stock."""
    if str(oc.get("proveedor")) != str(FARMA_GROUP):
        return "descartar", f"la OC es para el grupo {oc.get('proveedor')}"
    if oc.get("estado") != "creada":
        return "descartar", f"la OC ya esta {oc.get('estado')}"
    if not es_kit(oc.get("sku")):
        return "rechazar", f"{oc.get('sku')} no es un kit del catalogo"
    if not isinstance(oc.get("cantidad"), int) or oc["cantidad"] < 1:
        return "rechazar", f"cantidad invalida: {oc.get('cantidad')!r}"
    vencimiento = _fecha(oc.get("vencimiento"))
    if vencimiento is None or vencimiento <= ahora + MARGEN_DESPACHO:
        return "rechazar", "el plazo no alcanza para despachar"
    return None, None


def evaluar(sku: str, cantidad: int, vencimiento: datetime) -> Evaluacion:
    """Hay que llamarla con stock.candado_stock tomado."""
    return Evaluacion(
        sku=sku,
        cantidad=cantidad,
        stock=custodia.stock_disponible(sku),
        en_camino=stock.en_camino_antes(sku, vencimiento - MARGEN_DESPACHO),
        comprometido=stock.comprometido(sku),
    )
