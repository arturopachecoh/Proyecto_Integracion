"""Investigacion de un retiro: responde las preguntas 1, 2 y 3 de trazabilidad
para el lote retirado y todos sus derivados. Solo lee custodia (Postgres, sin
Farma Central): son tres consultas indexadas mas el CTE recursivo de
lot_relations, asi que termina en milisegundos.

1. Unidades en stock del lote y de sus derivados, y el espacio donde estan.
2. Lotes generados a partir del lote, recursivamente, con su lote padre.
3. Unidades despachadas a clientes en OC, agrupadas por OC.

Las ventas del portal no tienen OC: Farma Central solo recibe notificaciones
y entregas por OC (orderId), asi que no se reportan como entregas.
PENDIENTE (viene de la E1): el portal no llama a POST /dispatch (ver
app/ventas.py _despachar), asi que sus unidades "despachadas" siguen
fisicamente en los espacios del grupo en Farma. Para Farma son stock del
grupo, pero aqui no se reportan en inStock ni se ponen en cuarentena. Se
arregla haciendo que el portal despache de verdad, o ubicando esas unidades
con GET /spaces/{id}/products e incluyendolas aqui.
"""
import logging
from datetime import datetime, timezone

from sqlalchemy import or_, select

from app import trazabilidad
from app.db import SessionLocal
from app.models import Lote, LotRelation, OrdenCompra, Unidad, Venta, VentaUnidad

log = logging.getLogger("retiros")

# Unidades que siguen en el inventario de la distribuidora. "cuarentena" cuenta:
# una unidad que ya se aislo (por este u otro retiro) sigue estando en stock.
ESTADOS_EN_STOCK = ("en_stock", "reservada", "cuarentena")


def _vacia() -> dict:
    return {"lote": None, "derivados": [], "en_stock": [], "entregas": []}


def _lote(s, codigo: str) -> Lote | None:
    """Por codigo; si no, por el batch del proveedor. Prefiere el codigo exacto."""
    return s.scalar(select(Lote)
                    .where(or_(Lote.codigo == codigo, Lote.lote_proveedor == codigo))
                    .order_by(Lote.codigo != codigo, Lote.id)
                    .limit(1))


def investigar(codigo: str) -> dict:
    """{lote, derivados: [{batch, sku, sourceBatch}],
        en_stock: [{unidad_id, sku, lote_codigo, espacio}],
        entregas: [{orderId, customerName, productIds}]}"""
    with SessionLocal() as s:
        lote = _lote(s, codigo)
        if lote is None:
            log.error("Retiro del lote %s: el lote no esta en custodia", codigo)
            return _vacia()
        raiz_id, raiz_codigo = lote.id, lote.codigo

    # Pregunta 2: el sourceBatch es el padre directo de cada derivado. Un lote
    # fabricado con insumos de dos lotes afectados va una vez por cada padre
    # (asi lo cuenta Farma Central; aguas_abajo deja solo el primero)
    nodos = trazabilidad.aguas_abajo(raiz_codigo) or []
    codigos = {raiz_id: raiz_codigo} | {n["id"]: n["codigo"] for n in nodos}
    skus = {n["id"]: n["sku"] for n in nodos}
    ids = list(codigos)
    with SessionLocal() as s:
        pares = s.execute(
            select(LotRelation.child_lote_id, LotRelation.parent_lote_id).distinct()
            .where(LotRelation.child_lote_id.in_(list(skus)),
                   LotRelation.parent_lote_id.in_(ids))
        ).all()
    derivados = sorted(
        ({"batch": codigos[hijo], "sku": skus[hijo], "sourceBatch": codigos[padre]}
         for hijo, padre in pares),
        key=lambda d: (d["batch"], d["sourceBatch"]))

    ahora = datetime.now(timezone.utc)
    with SessionLocal() as s:
        # Pregunta 1
        en_stock = [
            {"unidad_id": f.id, "sku": f.sku, "lote_codigo": f.codigo, "espacio": f.espacio_actual}
            for f in s.execute(
                select(Unidad.id, Unidad.sku, Unidad.espacio_actual, Lote.codigo)
                .join(Lote, Lote.id == Unidad.lote_id)
                .where(Unidad.lote_id.in_(ids), Unidad.estado.in_(ESTADOS_EN_STOCK),
                       # una unidad vencida ya no existe en Farma: reportarla seria de mas
                       Unidad.vence_en.is_(None) | (Unidad.vence_en > ahora))
                .order_by(Unidad.id)
            ).all()
        ]

        # Pregunta 3
        filas = s.execute(
            select(Venta.orden_externa_id, Venta.comprador_nombre, OrdenCompra.cliente,
                   VentaUnidad.unidad_id)
            .join(Venta, Venta.id == VentaUnidad.venta_id)
            .outerjoin(OrdenCompra, OrdenCompra.id == Venta.orden_externa_id)
            .where(VentaUnidad.lote_id.in_(ids), VentaUnidad.estado == "despachada",
                   Venta.orden_externa_id.is_not(None))
            .order_by(Venta.orden_externa_id, VentaUnidad.unidad_id)
        ).all()
    por_oc: dict[str, dict] = {}
    for f in filas:
        e = por_oc.setdefault(f.orden_externa_id, {
            "orderId": f.orden_externa_id,
            "customerName": f.comprador_nombre or f.cliente or "",
            "productIds": [],
        })
        e["productIds"].append(f.unidad_id)

    return {"lote": raiz_codigo, "derivados": derivados, "en_stock": en_stock,
            "entregas": list(por_oc.values())}
