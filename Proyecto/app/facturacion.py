"""Facturacion: emite la factura de cada OC cumplida en la que somos proveedor.

Exactamente una vez: solo se intentan las OC con factura_id vacio, y se
marcan cuando el servicio confirma (200, o 409 si ya estaba emitida porque
el servidor se cayo justo despues de emitir). Cualquier otro error deja la
OC pendiente y se reintenta en el proximo tick."""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select, update

from app import billing_client
from app.db import SessionLocal
from app.models import OrdenCompra

log = logging.getLogger("facturacion")

MAX_POR_TICK = 10  # el SOAP acepta 60 llamadas por minuto: 10 emisiones + 10 pagos + listas


def por_facturar(limite=MAX_POR_TICK):
    """Ids de OC cumplidas segun Farma, sin factura, en las que somos proveedor.
    Las compras del mercado (rol comprador) las factura el otro grupo."""
    with SessionLocal() as s:
        return s.scalars(
            select(OrdenCompra.id)
            .where(OrdenCompra.estado_remoto == "cumplida",
                   OrdenCompra.factura_id.is_(None),
                   or_(OrdenCompra.canal != "mercado",
                       OrdenCompra.decision["rol"].as_string() == "vendedor"))
            .order_by(OrdenCompra.factura_error.is_not(None))  # las que fallaron, al final
            .limit(limite)  # None = sin limite (lo usa el panel)
        ).all()


def _guardar(oc_id, **campos):
    with SessionLocal() as s:
        s.execute(update(OrdenCompra).where(OrdenCompra.id == oc_id).values(**campos))
        s.commit()


def emitir_pendientes():
    for oc_id in por_facturar():
        try:
            f = billing_client.emitir(oc_id)
            _guardar(oc_id, factura_id=f["id"], factura_error=None)
            log.info("OC %s facturada: %s por $%.0f (%s)", oc_id, f["id"], f["price"], f["status"])
        except billing_client.SoapError as e:
            if e.codigo == "HTTP 429":  # Farma pide esperar: se sigue en el proximo tick
                log.warning("SOAP con limite de llamadas; se sigue en el proximo tick")
                break
            if e.codigo == "DUPLICATE_OPERATION":
                _guardar(oc_id, factura_id="duplicada", factura_error=None)
                log.info("OC %s ya estaba facturada", oc_id)
            else:
                _guardar(oc_id, factura_error=str(e))
                log.warning("OC %s no se pudo facturar: %s", oc_id, e)


def pagar_pendientes():
    """Paga lo que nos cobran: Farma (fabric), bodega externa (buffer) y mercado.
    No guarda nada: la lista de pendientes del SOAP es la fuente de verdad, y lo
    que no se alcance a pagar sigue pendiente en el proximo tick."""
    ahora = datetime.now(timezone.utc)
    pendientes = billing_client.facturas("pending", "client",
                                         ahora - timedelta(hours=71),   # el SOAP acepta max 3 dias
                                         ahora + timedelta(minutes=5))  # por si nuestro reloj va atrasado
    for f in sorted(pendientes, key=lambda f: f["createdAt"])[:MAX_POR_TICK]:
        try:
            pagada = billing_client.pagar(f["id"])
            log.info("Factura %s pagada (%s): $%.0f + interes $%.0f",
                     f["id"], f["channel"], pagada["price"], pagada["interest"])
        except billing_client.SoapError as e:
            if e.codigo == "HTTP 429":  # Farma pide esperar: se sigue en el proximo tick
                log.warning("SOAP con limite de llamadas; se sigue en el proximo tick")
                break
            log.warning("Factura %s no se pudo pagar: %s", f["id"], e)


def resumen():
    """Margen de las ultimas 71 h, como lo mide la rubrica:
    ingresos facturados - costos facturados - intereses (pagados o no)."""
    ahora = datetime.now(timezone.utc)
    desde, hasta = ahora - timedelta(hours=71), ahora + timedelta(minutes=5)
    emitidas = (billing_client.facturas("paid", "supplier", desde, hasta)
                + billing_client.facturas("pending", "supplier", desde, hasta))
    recibidas = (billing_client.facturas("paid", "client", desde, hasta)
                 + billing_client.facturas("pending", "client", desde, hasta))
    ingresos, costos = _por_canal(emitidas), _por_canal(recibidas)
    intereses = sum(f["interest"] for f in recibidas)
    return {
        "margen": sum(ingresos.values()) - sum(costos.values()) - intereses,
        "ingresos": ingresos,
        "costos": costos,
        "intereses": intereses,
        "saldo_banco": billing_client.saldo(),
        "por_pagar": sum(1 for f in recibidas if f["status"] == "pending"),
        "oc_sin_facturar": len(por_facturar(limite=None)),
    }


def _por_canal(facturas):
    """{"pubsub": 6174.0, "fabric": 8080.0, ...}"""
    totales = {}
    for f in facturas:
        totales[f["channel"]] = totales.get(f["channel"], 0) + f["price"]
    return totales
