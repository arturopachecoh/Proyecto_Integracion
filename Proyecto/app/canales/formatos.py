"""Leer el id de OC desde un archivo XML del sFTP o un mensaje de Pub/Sub.

El XML se lee con defusedxml: rechaza DTD y entidades, asi un archivo
malicioso no puede reventar la memoria del proceso.
"""
import json

from defusedxml import DefusedXmlException
from defusedxml.ElementTree import ParseError, fromstring

from app.pedidos.bandeja import ID_OC


def parsear_xml(contenido: bytes) -> str:
    """Formato del Anexo 1: <order><id>..</id><sku>..</sku><qty>..</qty></order>."""
    try:
        raiz = fromstring(contenido, forbid_dtd=True)
    except (ParseError, DefusedXmlException) as e:
        raise ValueError(f"XML invalido: {e}") from e
    if raiz.tag != "order":
        raise ValueError(f"XML sin <order> (raiz: {raiz.tag})")
    oc_id = (raiz.findtext("id") or "").strip()
    if not ID_OC.fullmatch(oc_id):
        raise ValueError(f"id de OC invalido en el XML: {oc_id!r}")
    return oc_id


def parsear_mensaje(data: bytes, atributos: dict) -> str:
    """El enunciado solo dice que el mensaje trae el id de la OC. Se aceptan
    JSON ({"id"} u {"orderId"}), el mismo XML del sFTP, el id solo, o el id en
    los atributos del mensaje. Cualquier otra cosa es un error con el contenido."""
    texto = data.decode("utf-8", errors="replace").strip()
    candidatos: list[str] = []
    if texto.startswith("{"):
        try:
            obj = json.loads(texto)
        except json.JSONDecodeError as e:
            raise ValueError(f"JSON invalido: {e}") from e
        candidatos += [str(obj[k]) for k in ("id", "orderId", "idOrden", "_id") if obj.get(k)]
    elif texto.startswith("<"):
        candidatos.append(parsear_xml(data))
    elif texto:
        candidatos.append(texto)
    candidatos += [str(atributos[k]) for k in ("id", "orderId") if atributos.get(k)]
    for c in candidatos:
        if ID_OC.fullmatch(c.strip()):
            return c.strip()
    raise ValueError(f"mensaje sin id de OC reconocible: {texto[:200]!r}")
