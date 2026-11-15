"""Consultas de estado: el cliente pregunta por un pedido que hizo antes por mensajeria.

Se identifica al cliente por su telefono: sus pedidos son los mensajes de ese
telefono que quedaron con OC. El texto de respuesta lo armamos nosotros con el
estado que entrega Farma en ese momento (no el modelo), asi nunca se inventa.
"""
import re

from sqlalchemy import select

from app import ordenes_client
from app.db import SessionLocal
from app.models import Mensaje, OrdenCompra
from app.operaciones import catalogo


def elegir_oc(telefono: str | None, texto: str, candidatos: list | None) -> str | None:
    """La OC del cliente por la que pregunta: la que cita por id; si no, la mas
    reciente del kit que nombra; si no, la mas reciente. None si no tiene pedidos."""
    citada = re.findall(r"\b[0-9a-f]{24}\b", texto.lower())
    if citada:
        return citada[0]
    with SessionLocal() as s:
        filas = s.execute(
            select(Mensaje.oc_id, OrdenCompra.sku)
            .outerjoin(OrdenCompra, OrdenCompra.id == Mensaje.oc_id)
            .where(Mensaje.telefono == telefono, Mensaje.oc_id.is_not(None))
            .order_by(Mensaje.recibido_en.desc())
        ).all()
    kits = {str(c).strip().upper() for c in candidatos or []}
    del_kit = [oc for oc, sku in filas if sku in kits]
    todas = [oc for oc, _ in filas]
    return (del_kit or todas or [None])[0]


def texto_estado(oc_id: str, nombre: str | None) -> str:
    """El estado real de la OC, leido de Farma al momento de responder."""
    oc = ordenes_client.obtener(oc_id)
    kit = catalogo().get(oc.get("sku"), {}).get("name", oc.get("sku"))
    cantidad = oc.get("cantidad")
    pedido = f"su pedido {oc_id} ({cantidad} x {kit})"
    hecho = f"{oc.get('despachado') or 0} de {cantidad} unidades despachadas"
    frases = {
        "creada": f"recibimos {pedido} y lo estamos revisando; aun no despachamos unidades.",
        "aceptada": f"{pedido} fue aceptado y va en camino: llevamos {hecho}.",
        "cumplida": f"{pedido} esta cumplido: {hecho}.",
        "rechazada": f"{pedido} fue rechazado, no despachamos unidades.",
        "vencida": f"{pedido} vencio; alcanzamos a tener {hecho}.",
    }
    estado = oc.get("estado")
    frase = frases.get(estado, f"{pedido} esta {estado}: {hecho}.")
    return f"Hola {nombre}: {frase}" if nombre else f"Hola: {frase}"
