"""Validacion de la interpretacion de un mensaje, sin confiar en el modelo.

Modulo puro (sin red ni base). Recibe lo que respondio el modelo y decide si
se registra como pedido o se descarta. Comprometerse con un pedido mal
interpretado es peor que descartarlo: ante cualquier duda se descarta.
"""
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

ZONA_CHILE = ZoneInfo("America/Santiago")
CANTIDAD_MAX = 12  # los pedidos reales son de uno o dos kits; cubre "una docena"
# La plataforma exige una fecha futura: margen para la latencia hasta que llegue
MARGEN_FUTURO = timedelta(minutes=2)
HORIZONTE = timedelta(days=7)
MOTIVO_MAX = 500

_FECHA_LOCAL = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?$")


@dataclass
class Resultado:
    registrar: bool
    cuerpo: dict  # cuerpo para POST /messaging/messages/{id}/response
    motivo: str | None = None
    pasos: list[str] = field(default_factory=list)


def skus_kit(catalogo: dict[str, dict]) -> set[str]:
    """Kits del catalogo: los productos vendibles."""
    return {sku for sku, p in catalogo.items() if p.get("sellable")}


def iso_utc(f: datetime) -> str:
    return f.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def local_a_utc(texto: str) -> datetime:
    """'YYYY-MM-DDTHH:MM' en hora de Chile -> datetime en UTC. ValueError si no calza."""
    if not isinstance(texto, str) or not _FECHA_LOCAL.match(texto.strip()):
        raise ValueError(f"fecha local con formato invalido: {texto!r}")
    local = datetime.fromisoformat(texto.strip()).replace(tzinfo=ZONA_CHILE)
    return local.astimezone(timezone.utc)


def _descartar(motivo: str, pasos: list[str]) -> Resultado:
    motivo = (motivo or "").strip() or "No corresponde a un pedido que se pueda registrar"
    pasos.append(f"descartar: {motivo}")
    return Resultado(False, {"status": "discarded", "reason": motivo[:MOTIVO_MAX]}, motivo, pasos)


def _cantidad(valor) -> int | None:
    if isinstance(valor, bool):
        return None
    if isinstance(valor, int):
        return valor
    if isinstance(valor, float) and valor.is_integer():
        return int(valor)
    if isinstance(valor, str) and valor.strip().isdigit():
        return int(valor.strip())
    return None


def _entrega(salida: dict, recibido_en: datetime) -> datetime:
    """Fecha de entrega en UTC. El modelo da hora local o minutos desde el mensaje."""
    local = salida.get("entrega_local")
    minutos = salida.get("en_minutos")
    if local not in (None, "") and minutos not in (None, ""):
        raise ValueError("el modelo dio fecha local y minutos a la vez")
    if minutos not in (None, ""):
        n = _cantidad(minutos)
        if n is None or n <= 0:
            raise ValueError(f"minutos invalidos: {minutos!r}")
        return recibido_en + timedelta(minutes=n)
    if local in (None, ""):
        raise ValueError("no se indico fecha de entrega")
    return local_a_utc(local)


def validar(salida, kits: set[str], recibido_en: datetime, ahora: datetime) -> Resultado:
    pasos: list[str] = []
    if not isinstance(salida, dict):
        return _descartar("No se pudo interpretar el mensaje", pasos)
    motivo_modelo = str(salida.get("motivo") or "").strip()

    if salida.get("es_pedido") is not True:
        pasos.append("el modelo indica que no es un pedido")
        return _descartar(f"No corresponde a un pedido: {motivo_modelo}" if motivo_modelo
                          else "No corresponde a un pedido", pasos)
    pasos.append("el modelo indica que es un pedido")
    if salida.get("cumplible") is not True:
        return _descartar(f"Pedido no se puede cumplir tal como esta escrito: {motivo_modelo}"
                          if motivo_modelo else "Pedido ambiguo o imposible de cumplir", pasos)

    sku = salida.get("sku")
    sku = sku.strip().upper() if isinstance(sku, str) else ""
    if sku not in kits:
        return _descartar(f"El producto pedido no es un kit del catalogo ({sku or 'sin SKU'})",
                          pasos)
    pasos.append(f"sku {sku} es un kit del catalogo")

    cantidad = _cantidad(salida.get("cantidad"))
    if cantidad is None or not 1 <= cantidad <= CANTIDAD_MAX:
        return _descartar(f"Cantidad no especificada o invalida ({salida.get('cantidad')!r})",
                          pasos)
    pasos.append(f"cantidad {cantidad}")

    try:
        entrega = _entrega(salida, recibido_en)
    except ValueError as e:
        return _descartar(f"Fecha de entrega no especificada o invalida: {e}", pasos)
    pasos.append(f"entrega {iso_utc(entrega)} (local {entrega.astimezone(ZONA_CHILE):%Y-%m-%d %H:%M})")
    if entrega <= recibido_en or entrega <= ahora + MARGEN_FUTURO:
        return _descartar("El plazo pedido ya paso", pasos)
    if entrega > recibido_en + HORIZONTE:
        return _descartar("El plazo pedido es demasiado lejano para confirmarlo", pasos)

    pasos.append("registrar como pedido")
    return Resultado(True, {"status": "order", "interpretation": {
        "sku": sku, "quantity": cantidad, "deliveryDate": iso_utc(entrega)}}, None, pasos)
