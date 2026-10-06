"""Consultas de las cuatro preguntas de trazabilidad (solo Postgres, sin Farma).

1. Unidades del lote X en inventario y dónde.
2. Lotes generados consumiendo X (aguas abajo).
3. Clientes a los que se entregaron unidades del lote X.
4. Lotes de insumo que originaron X (aguas arriba).
"""
from sqlalchemy import literal, select

from app.db import SessionLocal
from app.models import Lote, LotRelation, Unidad, Venta, VentaUnidad

MAX_PROFUNDIDAD = 20


def _lote_por_codigo(s, codigo: str) -> Lote | None:
    return s.scalar(select(Lote).where(Lote.codigo == codigo))


def _serializar_lote(lote: Lote) -> dict:
    return {
        "id": lote.id,
        "codigo": lote.codigo,
        "sku": lote.sku,
        "cantidad_inicial": lote.cantidad_inicial,
        "vence_en": lote.vence_en.isoformat() if lote.vence_en else None,
        "origen": lote.origen,
        "origen_grupo": lote.origen_grupo,
        "solicitud_id": lote.solicitud_id,
    }


def unidades_en_inventario(codigo: str) -> list[dict] | None:
    """Pregunta 1: unidades de X en inventario y su espacio."""
    with SessionLocal() as s:
        lote = _lote_por_codigo(s, codigo)
        if lote is None:
            return None
        filas = s.execute(
            select(Unidad.id, Unidad.espacio_actual, Unidad.estado, Unidad.vence_en)
            .where(Unidad.lote_id == lote.id, Unidad.estado.in_(("en_stock", "reservada")))
            .order_by(Unidad.espacio_actual, Unidad.id)
        ).all()
        return [
            {
                "id": u.id,
                "espacio": u.espacio_actual,
                "estado": u.estado,
                "vence_en": u.vence_en.isoformat() if u.vence_en else None,
            }
            for u in filas
        ]


def _recorrer(s, lote_id: int, direccion: str) -> list[dict]:
    """CTE recursivo sobre lot_relations. direccion=upstream|downstream."""
    if direccion == "upstream":
        ancla = (
            select(
                LotRelation.parent_lote_id.label("lote_id"),
                LotRelation.child_lote_id.label("desde_lote_id"),
                LotRelation.cantidad,
                LotRelation.solicitud_id,
                literal(1).label("profundidad"),
            ).where(LotRelation.child_lote_id == lote_id)
        )
        cte = ancla.cte(name="genealogia", recursive=True)
        rec = (
            select(
                LotRelation.parent_lote_id,
                LotRelation.child_lote_id,
                LotRelation.cantidad,
                LotRelation.solicitud_id,
                (cte.c.profundidad + 1).label("profundidad"),
            )
            .where(LotRelation.child_lote_id == cte.c.lote_id)
            .where(cte.c.profundidad < MAX_PROFUNDIDAD)
        )
    else:
        ancla = (
            select(
                LotRelation.child_lote_id.label("lote_id"),
                LotRelation.parent_lote_id.label("desde_lote_id"),
                LotRelation.cantidad,
                LotRelation.solicitud_id,
                literal(1).label("profundidad"),
            ).where(LotRelation.parent_lote_id == lote_id)
        )
        cte = ancla.cte(name="genealogia", recursive=True)
        rec = (
            select(
                LotRelation.child_lote_id,
                LotRelation.parent_lote_id,
                LotRelation.cantidad,
                LotRelation.solicitud_id,
                (cte.c.profundidad + 1).label("profundidad"),
            )
            .where(LotRelation.parent_lote_id == cte.c.lote_id)
            .where(cte.c.profundidad < MAX_PROFUNDIDAD)
        )

    genealogia = cte.union_all(rec)
    filas = s.execute(
        select(
            genealogia.c.lote_id,
            genealogia.c.desde_lote_id,
            genealogia.c.cantidad,
            genealogia.c.solicitud_id,
            genealogia.c.profundidad,
            Lote.codigo,
            Lote.sku,
            Lote.origen,
            Lote.origen_grupo,
            Lote.cantidad_inicial,
            Lote.vence_en,
        )
        .join(Lote, Lote.id == genealogia.c.lote_id)
        .order_by(genealogia.c.profundidad, Lote.codigo)
    ).all()

    vistos = set()
    nodos = []
    for f in filas:
        if f.lote_id in vistos:
            continue
        vistos.add(f.lote_id)
        nodos.append({
            "id": f.lote_id,
            "codigo": f.codigo,
            "sku": f.sku,
            "origen": f.origen,
            "origen_grupo": f.origen_grupo,
            "cantidad_inicial": f.cantidad_inicial,
            "vence_en": f.vence_en.isoformat() if f.vence_en else None,
            "cantidad_relacion": f.cantidad,
            "desde_lote_id": f.desde_lote_id,
            "solicitud_id": f.solicitud_id,
            "profundidad": f.profundidad,
        })
    return nodos


def aguas_abajo(codigo: str) -> list[dict] | None:
    """Pregunta 2: lotes generados consumiendo X, recursivo."""
    with SessionLocal() as s:
        lote = _lote_por_codigo(s, codigo)
        if lote is None:
            return None
        return _recorrer(s, lote.id, "downstream")


def aguas_arriba(codigo: str) -> list[dict] | None:
    """Pregunta 4: insumos que originaron X, recursivo hasta Farma/otra distribuidora."""
    with SessionLocal() as s:
        lote = _lote_por_codigo(s, codigo)
        if lote is None:
            return None
        return _recorrer(s, lote.id, "upstream")


def _clientes(s, lote_ids: list[int]) -> list[dict]:
    if not lote_ids:
        return []
    filas = s.execute(
        select(
            Venta.id,
            Venta.comprador_nombre,
            Venta.comprador_email,
            Venta.estado,
            Venta.transaccion_id,
            Venta.pagada_en,
            Venta.creada_en,
            VentaUnidad.unidad_id,
            VentaUnidad.lote_id,
            VentaUnidad.estado.label("estado_despacho"),
            Lote.codigo,
            Lote.sku,
        )
        .join(VentaUnidad, VentaUnidad.venta_id == Venta.id)
        .join(Lote, Lote.id == VentaUnidad.lote_id)
        .where(VentaUnidad.lote_id.in_(lote_ids))
        .order_by(Venta.id, VentaUnidad.unidad_id)
    ).all()
    por_venta: dict[int, dict] = {}
    for f in filas:
        venta = por_venta.setdefault(f.id, {
            "venta_id": f.id,
            "comprador_nombre": f.comprador_nombre,
            "comprador_email": f.comprador_email,
            "estado": f.estado,
            "transaccion_id": f.transaccion_id,
            "pagada_en": f.pagada_en.isoformat() if f.pagada_en else None,
            "creada_en": f.creada_en.isoformat() if f.creada_en else None,
            "unidades": [],
        })
        venta["unidades"].append({
            "id": f.unidad_id,
            "lote_codigo": f.codigo,
            "sku": f.sku,
            "estado_despacho": f.estado_despacho,
        })
    return list(por_venta.values())


def clientes_del_lote(codigo: str) -> list[dict] | None:
    """Pregunta 3: a qué clientes se entregaron unidades del lote X."""
    with SessionLocal() as s:
        lote = _lote_por_codigo(s, codigo)
        if lote is None:
            return None
        return _clientes(s, [lote.id])


def consultar(codigo: str) -> dict | None:
    """Respuesta completa para el visor y para GET /api/trazabilidad."""
    from sqlalchemy import func

    from app.models import Movimiento

    with SessionLocal() as s:
        lote = _lote_por_codigo(s, codigo)
        if lote is None:
            return None
        ocupacion = dict(
            s.execute(
                select(Unidad.espacio_actual, func.count())
                .where(Unidad.lote_id == lote.id, Unidad.estado.in_(("en_stock", "reservada")))
                .group_by(Unidad.espacio_actual)
            ).all()
        )
        paso_frio = s.scalar(
            select(Movimiento.id)
            .where(
                Movimiento.lote_id == lote.id,
                Movimiento.hacia.in_(("cold", "buffer")),
            )
            .limit(1)
        )
        conservacion = "frio" if paso_frio or ocupacion.get("cold") or ocupacion.get("buffer") else "ambiente"
        arriba = _recorrer(s, lote.id, "upstream")
        abajo = _recorrer(s, lote.id, "downstream")
        ids_abajo = [lote.id] + [n["id"] for n in abajo]
        return {
            "lote": _serializar_lote(lote),
            "conservacion": conservacion,
            "espacios": {k: v for k, v in ocupacion.items()},
            "unidades_inventario": [
                {
                    "id": u.id,
                    "espacio": u.espacio_actual,
                    "estado": u.estado,
                    "vence_en": u.vence_en.isoformat() if u.vence_en else None,
                }
                for u in s.scalars(
                    select(Unidad)
                    .where(Unidad.lote_id == lote.id, Unidad.estado.in_(("en_stock", "reservada")))
                    .order_by(Unidad.espacio_actual, Unidad.id)
                )
            ],
            "aguas_arriba": arriba,
            "aguas_abajo": abajo,
            "clientes": _clientes(s, [lote.id]),
            "clientes_derivados": _clientes(s, ids_abajo),
        }
