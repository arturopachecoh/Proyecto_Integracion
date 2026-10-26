"""Registro de retiros de lote.

Unico modulo que escribe retiros, retiro_unidades y retiro_notificaciones.
La clave de retiros es el recallId: un aviso repetido (webhook o polling) no
entra dos veces.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert

from app.db import SessionLocal
from app.models import Retiro, RetiroNotificacion, RetiroUnidad, Unidad

PLAZO_RETIRO = timedelta(minutes=30)
# Un retiro que no se pudo cerrar se sigue intentando hasta este tiempo despues
# del plazo; despues solo queda en el log
REINTENTAR_HASTA = timedelta(hours=6)


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _fecha(valor) -> datetime | None:
    """Fecha ISO de la API (o datetime). Sin zona horaria se asume UTC.
    Una fecha invalida se ignora: no se pierde un retiro por eso."""
    if not valor:
        return None
    if isinstance(valor, datetime):
        f = valor
    else:
        try:
            f = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
        except ValueError:
            return None
    return f if f.tzinfo is not None else f.replace(tzinfo=timezone.utc)


def _texto(valor, largo: int) -> str | None:
    return str(valor).strip()[:largo] if valor is not None and str(valor).strip() else None


def aviso_desde_farma(d) -> dict:
    """Traduce un retiro de Farma Central (webhook o GET /recalls) a las columnas
    de retiros. Levanta ValueError si falta el recallId o el lote."""
    if not isinstance(d, dict):
        raise ValueError("el aviso no es un objeto")
    recall_id, lote = _texto(d.get("recallId"), 60), _texto(d.get("batch"), 60)
    if not recall_id or not lote:
        raise ValueError("faltan recallId o batch")
    emitido = _fecha(d.get("issuedAt"))
    plazo = _fecha(d.get("deadline")) or (emitido + PLAZO_RETIRO if emitido else None)
    return {"id": recall_id, "lote": lote, "sku": _texto(d.get("sku"), 50),
            "motivo": _texto(d.get("reason"), 2000), "emitido_en": emitido, "plazo": plazo}


def recibir(aviso: dict) -> bool:
    """Anota un retiro. Devuelve False si ya estaba."""
    with SessionLocal.begin() as s:
        r = s.execute(
            insert(Retiro)
            .values(id=aviso["id"], lote=aviso["lote"], sku=aviso.get("sku"),
                    motivo=aviso.get("motivo"), emitido_en=aviso.get("emitido_en"),
                    plazo=aviso.get("plazo"), estado="pendiente", intentos=0)
            .on_conflict_do_nothing(index_elements=["id"])
            .returning(Retiro.id)
        )
        # Con este driver rowcount no es confiable (-1): se mira si devolvio la fila
        return r.first() is not None


def por_procesar() -> list[Retiro]:
    """Retiros a trabajar en este tick: todos hasta REINTENTAR_HASTA despues del
    plazo, aunque esten cerrados. Una unidad del lote puede aparecer despues
    (registro atrasado, o un derivado de una fabricacion que estaba en camino) y
    tambien hay que aislarla. Un retiro sin plazo se trabaja hasta cerrarse."""
    ahora = _ahora()
    with SessionLocal() as s:
        return list(s.scalars(
            select(Retiro).where(
                (Retiro.plazo.is_(None) & (Retiro.estado != "completo"))
                | (Retiro.plazo > ahora - REINTENTAR_HASTA))
            .order_by(Retiro.plazo.asc().nulls_last(), Retiro.recibido_en)
        ))


def pendientes_recientes(desde: datetime) -> list[str]:
    """Retiros en estado pendiente recibidos despues de `desde`."""
    with SessionLocal() as s:
        return list(s.scalars(select(Retiro.id).where(Retiro.estado == "pendiente",
                                                      Retiro.recibido_en > desde)))


def get(retiro_id: str) -> Retiro | None:
    with SessionLocal() as s:
        return s.get(Retiro, retiro_id)


def registrar_error(retiro_id: str, error: str) -> None:
    with SessionLocal.begin() as s:
        s.execute(update(Retiro).where(Retiro.id == retiro_id)
                  .values(intentos=Retiro.intentos + 1, ultimo_error=error[:2000]))


def guardar_reporte(retiro_id: str, cuerpo: dict) -> None:
    """Llamar despues de que Farma Central recibio el reporte."""
    with SessionLocal.begin() as s:
        r = s.get(Retiro, retiro_id, with_for_update=True)
        r.reporte = cuerpo
        r.reportado_en = _ahora()
        if r.estado == "pendiente":
            r.estado = "reportado"


def marcar_completo(retiro_id: str, completo: bool) -> None:
    """completo=False reabre un retiro cerrado si aparecio algo nuevo."""
    with SessionLocal.begin() as s:
        r = s.get(Retiro, retiro_id, with_for_update=True)
        if completo and r.estado != "completo":
            r.estado = "completo"
            r.completado_en = _ahora()
        elif not completo and r.estado == "completo":
            r.estado = "reportado" if r.reportado_en else "pendiente"


# ---------------------------------------------------------------------------
# Unidades retiradas
# ---------------------------------------------------------------------------

def anotar_unidades(retiro_id: str, unidades: list[dict]) -> int:
    """unidades: [{unidad_id, sku, lote_codigo, espacio}] tal como estaban al
    investigar. Se anotan ANTES de moverlas; las ya anotadas conservan su
    espacio original. Devuelve cuantas son nuevas."""
    if not unidades:
        return 0
    with SessionLocal.begin() as s:
        r = s.execute(
            insert(RetiroUnidad)
            .values([{"retiro_id": retiro_id, "unidad_id": u["unidad_id"], "sku": u["sku"],
                      "lote_codigo": u["lote_codigo"], "espacio_original": u["espacio"],
                      "en_cuarentena": u["espacio"] == "quarantine"} for u in unidades])
            .on_conflict_do_nothing(constraint="uq_retiro_unidades_retiro_unidad")
            .returning(RetiroUnidad.id)
        )
        return len(r.all())


def unidades(retiro_id: str) -> list[RetiroUnidad]:
    with SessionLocal() as s:
        return list(s.scalars(select(RetiroUnidad).where(RetiroUnidad.retiro_id == retiro_id)
                              .order_by(RetiroUnidad.id)))


def unidades_reportables(retiro_id: str) -> list[RetiroUnidad]:
    """Anotadas que siguen existiendo: fuera las que se confirmaron inexistentes
    en Farma (vencida) y las que vencieron antes de llegar a cuarentena."""
    ahora = _ahora()
    with SessionLocal() as s:
        return list(s.scalars(
            select(RetiroUnidad)
            .join(Unidad, Unidad.id == RetiroUnidad.unidad_id)
            .where(RetiroUnidad.retiro_id == retiro_id, Unidad.estado != "vencida",
                   RetiroUnidad.en_cuarentena.is_(True)
                   | Unidad.vence_en.is_(None) | (Unidad.vence_en > ahora))
            .order_by(RetiroUnidad.id)
        ))


def ids_por_retirar(retiro_id: str) -> list[str]:
    """Anotadas que siguen en circulacion (en stock o reservadas)."""
    with SessionLocal() as s:
        return list(s.scalars(
            select(RetiroUnidad.unidad_id)
            .join(Unidad, Unidad.id == RetiroUnidad.unidad_id)
            .where(RetiroUnidad.retiro_id == retiro_id, RetiroUnidad.en_cuarentena.is_(False),
                   Unidad.estado.in_(("en_stock", "reservada")))
        ))


def por_aislar(retiro_id: str) -> list[tuple[str, str, str | None, str, datetime | None]]:
    """(unidad_id, sku, espacio_actual, estado, vence_en) de las anotadas que aun
    no estan en el area de cuarentena. Las vencidas o perdidas ya no se mueven."""
    with SessionLocal() as s:
        filas = s.execute(
            select(Unidad.id, Unidad.sku, Unidad.espacio_actual, Unidad.estado, Unidad.vence_en)
            .join(RetiroUnidad, RetiroUnidad.unidad_id == Unidad.id)
            .where(RetiroUnidad.retiro_id == retiro_id, RetiroUnidad.en_cuarentena.is_(False),
                   Unidad.estado.in_(("en_stock", "reservada", "cuarentena")))
            .order_by(RetiroUnidad.id)
        ).all()
        return [tuple(f) for f in filas]


def marcar_aislada(unidad_id: str) -> None:
    """La unidad ya esta en el area de cuarentena (vale para todos sus retiros)."""
    with SessionLocal.begin() as s:
        s.execute(update(RetiroUnidad).where(RetiroUnidad.unidad_id == unidad_id)
                  .values(en_cuarentena=True))


# ---------------------------------------------------------------------------
# Notificaciones (una por OC afectada)
# ---------------------------------------------------------------------------

def anotar_notificaciones(retiro_id: str, cuerpos: list[dict]) -> None:
    """Se anota ANTES de enviar. Una OC ya anotada no se vuelve a anotar."""
    if not cuerpos:
        return
    with SessionLocal.begin() as s:
        s.execute(
            insert(RetiroNotificacion)
            .values([{"retiro_id": retiro_id, "oc_id": c["orderId"], "cuerpo": c}
                     for c in cuerpos])
            .on_conflict_do_nothing(constraint="uq_retiro_notificaciones_retiro_oc")
        )


def notificaciones_pendientes(retiro_id: str) -> list[tuple[str, dict]]:
    with SessionLocal() as s:
        return [tuple(f) for f in s.execute(
            select(RetiroNotificacion.oc_id, RetiroNotificacion.cuerpo)
            .where(RetiroNotificacion.retiro_id == retiro_id,
                   RetiroNotificacion.enviada_en.is_(None))
            .order_by(RetiroNotificacion.id)
        ).all()]


def marcar_notificada(retiro_id: str, oc_id: str) -> None:
    with SessionLocal.begin() as s:
        s.execute(update(RetiroNotificacion)
                  .where(RetiroNotificacion.retiro_id == retiro_id,
                         RetiroNotificacion.oc_id == oc_id)
                  .values(enviada_en=_ahora()))


# ---------------------------------------------------------------------------
# Lectura para el portal (/recalls)
# ---------------------------------------------------------------------------

def _iso(f: datetime | None) -> str | None:
    return f.isoformat() if f else None


def _resumen(r: Retiro, n_unidades: int) -> dict:
    return {"id": r.id, "lote": r.lote, "sku": r.sku, "motivo": r.motivo,
            "emitido_en": _iso(r.emitido_en), "plazo": _iso(r.plazo), "estado": r.estado,
            "recibido_en": _iso(r.recibido_en), "reportado_en": _iso(r.reportado_en),
            "completado_en": _iso(r.completado_en), "unidades_retiradas": n_unidades}


def listar() -> list[dict]:
    with SessionLocal() as s:
        conteo = (select(RetiroUnidad.retiro_id, func.count().label("n"))
                  .group_by(RetiroUnidad.retiro_id).subquery())
        filas = s.execute(
            select(Retiro, func.coalesce(conteo.c.n, 0))
            .outerjoin(conteo, conteo.c.retiro_id == Retiro.id)
            .order_by(Retiro.emitido_en.desc().nulls_last(), Retiro.recibido_en.desc())
        ).all()
        return [_resumen(r, n) for r, n in filas]


def detalle(retiro_id: str) -> dict | None:
    """Productos retirados de circulacion (SKU e ID de cada unidad), lotes
    derivados, entregas afectadas y el ultimo reporte enviado."""
    with SessionLocal() as s:
        r = s.get(Retiro, retiro_id)
        if r is None:
            return None
        filas = s.execute(
            select(RetiroUnidad, Unidad.estado, Unidad.espacio_actual)
            .join(Unidad, Unidad.id == RetiroUnidad.unidad_id)
            .where(RetiroUnidad.retiro_id == retiro_id)
            .order_by(RetiroUnidad.sku, RetiroUnidad.lote_codigo, RetiroUnidad.unidad_id)
        ).all()
        notifs = s.scalars(select(RetiroNotificacion)
                           .where(RetiroNotificacion.retiro_id == retiro_id)
                           .order_by(RetiroNotificacion.id)).all()
        reporte = r.reporte or {}
        data = _resumen(r, len(filas))
        data.update({
            "unidades": [{"id": ru.unidad_id, "sku": ru.sku, "lote": ru.lote_codigo,
                          "espacio_original": ru.espacio_original,
                          "en_cuarentena": ru.en_cuarentena, "estado": estado,
                          "espacio_actual": espacio} for ru, estado, espacio in filas],
            "derivados": reporte.get("derivedBatches", []),
            "entregas": reporte.get("deliveries", []),
            "notificaciones": [{"oc_id": n.oc_id, "cliente": (n.cuerpo or {}).get("customerName"),
                                "unidades": len((n.cuerpo or {}).get("productIds") or []),
                                "enviada_en": _iso(n.enviada_en)} for n in notifs],
            "reporte": r.reporte,
            "intentos": r.intentos,
            "ultimo_error": r.ultimo_error,
        })
        return data
