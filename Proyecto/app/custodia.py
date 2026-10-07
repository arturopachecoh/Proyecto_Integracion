"""Registro de trazabilidad y custodia.

Este modulo es el UNICO lugar que escribe en las tablas de custodia.
Cada funcion publica es una transaccion: o se guarda todo el evento, o nada.

Espacios validos: checkIn, bodega, cold, buffer, packaging, checkOut, quarantine
"""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.db import SessionLocal
from sqlalchemy import func as sqlfunc

from app.models import (
    Consumo, Lote, LotRelation, Movimiento, Solicitud, Unidad, Venta, VentaItem, VentaUnidad,
)

log = logging.getLogger("custodia")

# Margen para comparar la hora de llegada con el reloj local
TOLERANCIA_LLEGADA = timedelta(minutes=2)


def _fecha(iso: str | None) -> datetime | None:
    return datetime.fromisoformat(iso.replace("Z", "+00:00")) if iso else None


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Solicitudes a Farma Central
# ---------------------------------------------------------------------------

def registrar_compra(sku: str, cantidad: int, challenge_id: str, llega_en: str) -> int:
    """Llamar justo despues de que POST /products confirma una compra de insumo."""
    with SessionLocal.begin() as s:
        sol = Solicitud(tipo="compra", sku=sku, cantidad=cantidad,
                        challenge_id=challenge_id, llega_en=_fecha(llega_en))
        s.add(sol)
        s.flush()
        log.info("Compra registrada #%d: %d x %s", sol.id, cantidad, sku)
        return sol.id


def registrar_fabricacion(sku: str, cantidad: int, challenge_id: str, llega_en: str,
                          unidades_consumidas: list[str]) -> int:
    """Llamar justo despues de que POST /products confirma una fabricacion.

    unidades_consumidas: los _id de las unidades que se dejaron en acondicionamiento
    para esta fabricacion. Solicitud y consumos se guardan en la misma transaccion.
    """
    with SessionLocal.begin() as s:
        sol = Solicitud(tipo="fabricacion", sku=sku, cantidad=cantidad,
                        challenge_id=challenge_id, llega_en=_fecha(llega_en))
        s.add(sol)
        s.flush()

        unidades = s.scalars(select(Unidad).where(Unidad.id.in_(unidades_consumidas))).all()
        faltan = set(unidades_consumidas) - {u.id for u in unidades}
        if faltan:
            # No se registra a medias: si falta alguna unidad, se revierte todo
            raise ValueError(f"Unidades no registradas en custodia: {sorted(faltan)}")

        for u in unidades:
            s.add(Consumo(solicitud_id=sol.id, unidad_id=u.id, lote_id=u.lote_id))
            s.add(Movimiento(unidad_id=u.id, lote_id=u.lote_id, tipo="consumo",
                             desde=u.espacio_actual, hacia=None, solicitud_id=sol.id))
            u.estado = "consumida"
            u.espacio_actual = None

        log.info("Fabricacion registrada #%d: %d x %s, consume %d unidades",
                 sol.id, cantidad, sku, len(unidades))
        return sol.id


# ---------------------------------------------------------------------------
# Llegadas (las llama el sincronizador del worker)
# ---------------------------------------------------------------------------

def registrar_llegadas(productos: list[dict], espacio: str) -> int:
    """Registra unidades que aparecieron en un espacio y aun no estan en custodia.

    productos: lo que devuelve GET /spaces/{id}/products (con _id, sku, batch, expiresAt).
    Es idempotente: las unidades ya registradas se ignoran.
    Devuelve cuantas unidades nuevas se registraron.
    """
    if not productos:
        return 0

    with SessionLocal.begin() as s:
        ids = [p["_id"] for p in productos]
        conocidas = set(s.scalars(select(Unidad.id).where(Unidad.id.in_(ids))))
        nuevas = [p for p in productos if p["_id"] not in conocidas]

        por_lote: dict[str, list[dict]] = {}
        for p in nuevas:
            if not p.get("batch"):
                log.error("Unidad %s (%s) sin batch: no se registra", p["_id"], p["sku"])
                continue
            por_lote.setdefault(p["batch"], []).append(p)

        registradas = 0
        for codigo, unidades in por_lote.items():
            sku = unidades[0]["sku"]
            lote = s.scalar(select(Lote).where(Lote.codigo == codigo))

            if lote is None:
                lote = _crear_lote(s, codigo, sku, unidades)
                if lote is None:
                    continue

            tipo_mov = "generacion" if lote.origen == "produccion" else "recepcion"
            for p in unidades:
                s.add(Unidad(id=p["_id"], lote_id=lote.id, sku=sku, espacio_actual=espacio,
                             estado="en_stock", vence_en=_fecha(p.get("expiresAt"))))
            s.flush()  # las unidades deben existir antes que sus movimientos (llave foranea)
            for p in unidades:
                s.add(Movimiento(unidad_id=p["_id"], lote_id=lote.id, tipo=tipo_mov,
                                 desde=None, hacia=espacio, solicitud_id=lote.solicitud_id))
                registradas += 1

            log.info("Llegada: %d unidades del lote %s (%s) en %s",
                     len(unidades), codigo, lote.origen, espacio)
        return registradas


def _crear_lote(s, codigo: str, sku: str, unidades: list[dict]) -> Lote | None:
    """Crea el lote y lo asocia a la solicitud pendiente mas antigua de ese SKU
    cuya hora de llegada ya paso."""
    sol = s.scalar(
        select(Solicitud)
        .where(Solicitud.sku == sku, Solicitud.estado == "pendiente",
               Solicitud.llega_en <= _ahora() + TOLERANCIA_LLEGADA)
        .order_by(Solicitud.llega_en)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if sol is None:
        log.error("Lote %s (%s) llego sin una solicitud pendiente que lo explique", codigo, sku)
        return None

    lote = Lote(codigo=codigo, sku=sku, cantidad_inicial=sol.cantidad,
                vence_en=_fecha(unidades[0].get("expiresAt")),
                origen="produccion" if sol.tipo == "fabricacion" else "farma_central",
                solicitud_id=sol.id)
    s.add(lote)
    sol.estado = "recibida"
    s.flush()
    if sol.tipo == "fabricacion":
        _materializar_relaciones(s, sol.id, lote.id)
    return lote


def _materializar_relaciones(s, solicitud_id: int, child_lote_id: int) -> None:
    """Agrega lot_relations a partir de los consumos de la fabricacion."""
    filas = s.execute(
        select(Consumo.lote_id, sqlfunc.count())
        .where(Consumo.solicitud_id == solicitud_id)
        .group_by(Consumo.lote_id)
    ).all()
    for parent_id, cantidad in filas:
        existe = s.scalar(
            select(LotRelation.id).where(
                LotRelation.parent_lote_id == parent_id,
                LotRelation.child_lote_id == child_lote_id,
            )
        )
        if existe is None:
            s.add(LotRelation(
                parent_lote_id=parent_id,
                child_lote_id=child_lote_id,
                cantidad=int(cantidad),
                solicitud_id=solicitud_id,
            ))


# ---------------------------------------------------------------------------
# Traslados, vencimientos
# ---------------------------------------------------------------------------

def registrar_traslado(unidad_id: str, hacia: str) -> bool:
    """Llamar despues de que PATCH /products/{id} movio la unidad con exito."""
    with SessionLocal.begin() as s:
        u = s.get(Unidad, unidad_id)
        if u is None:
            log.error("Traslado de unidad %s que no esta en custodia", unidad_id)
            return False
        s.add(Movimiento(unidad_id=u.id, lote_id=u.lote_id, tipo="traslado",
                         desde=u.espacio_actual, hacia=hacia))
        u.espacio_actual = hacia
        return True


def actualizar_vencimientos(productos: list[dict]) -> None:
    """Guarda el expiresAt actual (cambia si la unidad se degrado fuera del frio)."""
    with SessionLocal.begin() as s:
        for p in productos:
            u = s.get(Unidad, p["_id"])
            if u is not None and p.get("expiresAt"):
                u.vence_en = _fecha(p["expiresAt"])


def registrar_vencidas(unidad_ids: list[str]) -> None:
    """Unidades en stock que desaparecieron de Farma Central porque vencieron."""
    with SessionLocal.begin() as s:
        for u in s.scalars(select(Unidad).where(Unidad.id.in_(unidad_ids))):
            s.add(Movimiento(unidad_id=u.id, lote_id=u.lote_id, tipo="vencimiento",
                             desde=u.espacio_actual, hacia=None))
            u.estado = "vencida"
            u.espacio_actual = None


# ---------------------------------------------------------------------------
# Ventas y despacho (con estado pendiente para no quedar a medias)
# ---------------------------------------------------------------------------

def crear_venta(comprador_nombre: str, comprador_email: str, total: int,
                canal: str = "portal", orden_externa_id: str | None = None,
                items: list[dict] | None = None,
                transaccion_id: str | None = None) -> int:
    """items: [{sku, cantidad, precio_unitario}, ...]"""
    with SessionLocal.begin() as s:
        v = Venta(comprador_nombre=comprador_nombre, comprador_email=comprador_email,
                  total=total, canal=canal, orden_externa_id=orden_externa_id,
                  transaccion_id=transaccion_id)
        s.add(v)
        s.flush()
        for item in items or []:
            s.add(VentaItem(
                venta_id=v.id,
                sku=item["sku"],
                cantidad=item["cantidad"],
                precio_unitario=item["precio_unitario"],
            ))
        return v.id


def asignar_unidades_a_venta(venta_id: int, unidad_ids: list[str]) -> None:
    """Paso 1 del despacho: se anota la intencion ANTES de llamar a la API.
    Las unidades quedan reservadas para esta venta."""
    with SessionLocal.begin() as s:
        for u in s.scalars(select(Unidad).where(Unidad.id.in_(unidad_ids))):
            if u.estado != "en_stock":
                raise ValueError(f"Unidad {u.id} no esta disponible ({u.estado})")
            s.add(VentaUnidad(venta_id=venta_id, unidad_id=u.id, lote_id=u.lote_id,
                              estado="pendiente"))
            s.add(Movimiento(unidad_id=u.id, lote_id=u.lote_id, tipo="venta",
                             desde=u.espacio_actual, hacia=u.espacio_actual, venta_id=venta_id))
            u.estado = "reservada"


def liberar_reserva(venta_id: int) -> None:
    """Pago cancelado o con error: las unidades vuelven a estar vendibles."""
    with SessionLocal.begin() as s:
        filas = list(s.scalars(
            select(VentaUnidad).where(
                VentaUnidad.venta_id == venta_id,
                VentaUnidad.estado == "pendiente",
            )
        ))
        for vu in filas:
            u = s.get(Unidad, vu.unidad_id)
            if u is not None and u.estado == "reservada":
                u.estado = "en_stock"
            s.delete(vu)


def marcar_pago(venta_id: int, estado: str, transaccion_id: str | None = None) -> None:
    with SessionLocal.begin() as s:
        v = s.get(Venta, venta_id)
        if v is None:
            raise ValueError(f"Venta {venta_id} no existe")
        if transaccion_id:
            v.transaccion_id = transaccion_id
        if v.estado == "pagada":
            return
        v.estado = estado
        if estado == "pagada":
            v.pagada_en = _ahora()


def venta(venta_id: int) -> dict | None:
    with SessionLocal() as s:
        v = s.get(Venta, venta_id)
        if v is None:
            return None
        return {
            "id": v.id,
            "estado": v.estado,
            "total": v.total,
            "transaccion_id": v.transaccion_id,
            "comprador_nombre": v.comprador_nombre,
            "comprador_email": v.comprador_email,
        }


def venta_por_transaccion(tx_id: str) -> dict | None:
    with SessionLocal() as s:
        v = s.scalar(select(Venta).where(Venta.transaccion_id == tx_id))
        if v is None:
            return None
        return venta(v.id)


def confirmar_despacho(unidad_id: str) -> None:
    """Paso 2 del despacho: llamar cuando Farma Central confirmo que la unidad salio."""
    with SessionLocal.begin() as s:
        vu = s.scalar(select(VentaUnidad).where(VentaUnidad.unidad_id == unidad_id))
        u = s.get(Unidad, unidad_id)
        if vu is None or u is None:
            raise ValueError(f"No hay despacho pendiente para {unidad_id}")
        vu.estado = "despachada"
        vu.despachada_en = _ahora()
        s.add(Movimiento(unidad_id=u.id, lote_id=u.lote_id, tipo="despacho",
                         desde=u.espacio_actual, hacia=None, venta_id=vu.venta_id))
        u.estado = "despachada"
        u.espacio_actual = None


def despachos_pendientes() -> list[tuple[int, str]]:
    """Para recuperarse de una caida: (venta_id, unidad_id) que quedaron a medias.
    Para cada una hay que preguntarle a Farma Central si la unidad salio o no."""
    with SessionLocal() as s:
        filas = s.execute(select(VentaUnidad.venta_id, VentaUnidad.unidad_id)
                          .where(VentaUnidad.estado == "pendiente")).all()
        return [tuple(f) for f in filas]


# ---------------------------------------------------------------------------
# Consultas para fabricar y para la cadena de frio
# ---------------------------------------------------------------------------

ESPACIOS_USABLES = ("packaging", "checkIn", "bodega", "cold", "buffer")


def unidades_disponibles(sku: str, margen: timedelta = timedelta(hours=1)) -> list[Unidad]:
    """Unidades en stock de un SKU que se pueden usar para fabricar.
    Primero las que ya estan en acondicionamiento (no hay que moverlas),
    despues por vencimiento: las que vencen antes se usan primero (FEFO)."""
    with SessionLocal() as s:
        return list(s.scalars(
            select(Unidad)
            .where(Unidad.sku == sku, Unidad.estado == "en_stock",
                   Unidad.espacio_actual.in_(ESPACIOS_USABLES),
                   (Unidad.vence_en.is_(None)) | (Unidad.vence_en > _ahora() + margen))
            .order_by((Unidad.espacio_actual != "packaging"), Unidad.vence_en.asc().nulls_last())
        ))


def nacidas_en_acondicionamiento(skus: set[str]) -> list[Unidad]:
    """Unidades de esos SKU que estan en acondicionamiento porque NACIERON ahi
    (su ultimo movimiento es una generacion). Las que llegaron por traslado
    estan esperando ser fabricadas y no se tocan."""
    if not skus:
        return []
    with SessionLocal() as s:
        ultimo = (select(Movimiento.tipo)
                  .where(Movimiento.unidad_id == Unidad.id)
                  .order_by(Movimiento.id.desc()).limit(1)
                  .correlate(Unidad).scalar_subquery())
        return list(s.scalars(
            select(Unidad).where(Unidad.sku.in_(skus), Unidad.estado == "en_stock",
                                 Unidad.espacio_actual == "packaging", ultimo == "generacion")
        ))


def en_camino(sku: str, max_atraso: timedelta = timedelta(minutes=30)) -> int:
    """Unidades de un SKU pedidas (compra o fabricacion) que aun no llegan.
    Las solicitudes atrasadas mas de max_atraso se consideran perdidas."""
    from sqlalchemy import func as f
    with SessionLocal() as s:
        return s.scalar(
            select(f.coalesce(f.sum(Solicitud.cantidad), 0))
            .where(Solicitud.sku == sku, Solicitud.estado == "pendiente",
                   Solicitud.llega_en > _ahora() - max_atraso)
        )


def unidades_en(espacio: str) -> list[Unidad]:
    with SessionLocal() as s:
        return list(s.scalars(select(Unidad).where(Unidad.espacio_actual == espacio,
                                                   Unidad.estado == "en_stock")))


def fabricaciones_en_camino() -> int:
    """Unidades de productos fabricados que aun no nacen (ocuparan acondicionamiento)."""
    with SessionLocal() as s:
        return s.scalar(
            select(sqlfunc.coalesce(sqlfunc.sum(Solicitud.cantidad), 0))
            .where(Solicitud.tipo == "fabricacion", Solicitud.estado == "pendiente",
                   Solicitud.llega_en > _ahora() - timedelta(minutes=30))
        ) or 0


def stock_disponible(sku: str, margen: timedelta = timedelta(hours=1)) -> int:
    """Unidades vendibles de un SKU (en stock, no vencidas, en espacios usables)."""
    with SessionLocal() as s:
        return s.scalar(
            select(sqlfunc.count())
            .select_from(Unidad)
            .where(
                Unidad.sku == sku,
                Unidad.estado == "en_stock",
                Unidad.espacio_actual.in_(ESPACIOS_USABLES),
                (Unidad.vence_en.is_(None)) | (Unidad.vence_en > _ahora() + margen),
            )
        ) or 0

