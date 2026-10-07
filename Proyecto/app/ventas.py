"""Flujo de venta del portal: reserva FEFO, pago y despacho."""
from __future__ import annotations

import logging
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from app import catalogo, custodia
from app.config import DISPATCH_FARMA, PUBLIC_BASE_URL
from app.db import engine
from app.integrations import checkout

log = logging.getLogger("ventas")
LOCK_VENTA = 4_000_003
RESERVA_MINUTOS = 60  # una sesion de Integrapay no dura tanto; despues se libera el stock


@contextmanager
def _candado_venta():
    with engine.connect() as conn:
        if not conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": LOCK_VENTA}).scalar():
            raise RuntimeError("Hay otra venta en curso; reintenta")
        try:
            yield
        finally:
            conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": LOCK_VENTA})


def iniciar_checkout(nombre: str, email: str, items: list[dict]) -> dict:
    validado = catalogo.validar_carrito(items)
    if not validado["ok"]:
        raise ValueError("; ".join(validado["errores"]))

    with _candado_venta():
        unidad_ids: list[str] = []
        for linea in validado["items"]:
            disponibles = custodia.unidades_disponibles(linea["sku"])
            if len(disponibles) < linea["cantidad"]:
                raise ValueError(
                    f"{linea['sku']}: stock insuficiente al reservar "
                    f"(hay {len(disponibles)}, se piden {linea['cantidad']})"
                )
            unidad_ids.extend(u.id for u in disponibles[: linea["cantidad"]])

        venta_id = custodia.crear_venta(
            comprador_nombre=nombre,
            comprador_email=email,
            total=validado["total"],
            items=[
                {
                    "sku": l["sku"],
                    "cantidad": l["cantidad"],
                    "precio_unitario": l["precio"],
                }
                for l in validado["items"]
            ],
        )
        try:
            custodia.asignar_unidades_a_venta(venta_id, unidad_ids)
        except Exception:
            custodia.marcar_pago(venta_id, "error")
            raise

        urls = {
            "success": f"{PUBLIC_BASE_URL}/pago/exito?venta={venta_id}",
            "error": f"{PUBLIC_BASE_URL}/pago/error?venta={venta_id}",
            "cancelled": f"{PUBLIC_BASE_URL}/pago/cancelado?venta={venta_id}",
        }
        tx = checkout.crear_transaccion(validado["total"], venta_id, urls)
        custodia.marcar_pago(venta_id, "pendiente_pago", transaccion_id=tx["id"])
        return {"venta_id": venta_id, "redirect_url": tx["redirect_url"], "transaccion_id": tx["id"]}


RESULTADO_PAGO = {
    "exito": "exito",
    "success": "exito",
    "cancelado": "cancelado",
    "cancelled": "cancelado",
    "cancel": "cancelado",
    "error": "error",
}


def normalizar_resultado(resultado: str) -> str | None:
    return RESULTADO_PAGO.get((resultado or "").strip().lower())


def finalizar(venta_id: int, resultado: str) -> dict:
    """Idempotente. resultado: exito | cancelado | error (también aliases Integrapay)."""
    resultado = normalizar_resultado(resultado) or ""
    if resultado not in {"exito", "cancelado", "error"}:
        raise ValueError("resultado inválido")
    venta = custodia.venta(venta_id)
    if venta is None:
        raise ValueError("Venta no encontrada")
    if venta["estado"] == "pagada":
        return {"venta_id": venta_id, "estado": "pagada"}
    if venta["estado"] in {"cancelada", "error"}:
        return {"venta_id": venta_id, "estado": venta["estado"]}

    if resultado == "exito":
        custodia.marcar_pago(venta_id, "pagada")
        _despachar(venta_id)
        return {"venta_id": venta_id, "estado": "pagada"}

    estado = "cancelada" if resultado == "cancelado" else "error"
    custodia.marcar_pago(venta_id, estado)
    custodia.liberar_reserva(venta_id)
    return {"venta_id": venta_id, "estado": estado}


def _despachar(venta_id: int) -> None:
    pendientes = [uid for vid, uid in custodia.despachos_pendientes() if vid == venta_id]
    for unidad_id in pendientes:
        if DISPATCH_FARMA:
            try:
                from app.operaciones import mover
                mover(unidad_id, "checkOut")
            except Exception:
                log.exception("No se pudo mover %s a checkOut; queda pendiente", unidad_id)
                continue
        try:
            custodia.confirmar_despacho(unidad_id)
        except Exception:
            log.exception("No se pudo confirmar despacho de %s", unidad_id)


def expirar_reservas(minutos: int = RESERVA_MINUTOS) -> list[int]:
    """Cancela las ventas que llevan mas de `minutos` sin pago y libera sus unidades.
    Si el cliente abandona Integrapay, la reserva no puede bloquear stock para siempre."""
    limite = datetime.now(timezone.utc) - timedelta(minutes=minutos)
    expiradas = custodia.ventas_sin_pagar(limite)
    for venta_id in expiradas:
        finalizar(venta_id, "cancelado")
        log.info("Venta %s sin pago tras %d min: cancelada y reserva liberada", venta_id, minutos)
    return expiradas


def recuperar_pendientes() -> None:
    """Reintenta despachos de ventas ya pagadas (caída entre pago y Farma)."""
    vistos: set[int] = set()
    for venta_id, _unidad_id in custodia.despachos_pendientes():
        if venta_id in vistos:
            continue
        vistos.add(venta_id)
        venta = custodia.venta(venta_id)
        if venta and venta["estado"] == "pagada":
            _despachar(venta_id)
