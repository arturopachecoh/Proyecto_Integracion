"""Efectos del mercado: publicar, aceptar, refrescar. El ciclo decide cual corre."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from app import config, custodia, operaciones
from app.mercado import orden, registro
from app import trades_client
from app.trades_client import estado_local, normalizar

log = logging.getLogger("mercado")


def publicar_venta(sku: str, cantidad: int, precio: int) -> bool:
    ids = [u.id for u in custodia.unidades_disponibles(sku)[:cantidad]]
    if len(ids) < cantidad:
        return False
    local = f"pend-{uuid.uuid4().hex}"
    registro.crear(local, "sell", sku, cantidad, precio, "publicando", "vendedor")
    try:
        custodia.apartar_para_oferta(local, ids)
    except Exception:
        log.exception("No se pudo apartar %s para la venta", sku)
        registro.marcar(local, estado="cancelada")
        return False
    if not _mover_a_despacho(ids):
        _revertir(local, sku, ids)
        return False
    respuesta = trades_client.publicar("sell", sku, cantidad, precio)
    remoto = _id_remoto(respuesta)
    if not respuesta.ok or not remoto:
        log.warning("Farma no publico la venta de %s (%s)", sku, getattr(respuesta, "status", None))
        _revertir(local, sku, ids)
        return False
    registro.renombrar(local, remoto)
    registro.marcar(remoto, estado="abierta")
    log.info("Oferta de venta %s: %d x %s a %s", remoto, cantidad, sku, precio)
    return True


def publicar_compra(sku: str, cantidad: int, precio: int) -> bool:
    respuesta = trades_client.publicar("buy", sku, cantidad, precio)
    remoto = _id_remoto(respuesta)
    if not respuesta.ok or not remoto:
        log.warning("Farma no publico la compra de %s (%s)", sku, respuesta.status)
        return False
    registro.crear(remoto, "buy", sku, cantidad, precio, "abierta", "comprador")
    log.info("Oferta de compra %s: %d x %s a %s", remoto, cantidad, sku, precio)
    return True


def aceptar_ajena(oferta: dict) -> bool:
    offer_id = oferta.get("id")
    if not offer_id or registro.existe(offer_id):
        return False
    if oferta.get("group") == config.FARMA_GROUP:
        return False
    registro.crear(
        offer_id, oferta.get("side") or "sell", oferta["sku"], int(oferta["quantity"]),
        int(oferta["unitPrice"]), "aceptando", "comprador", contraparte=oferta.get("group"),
    )
    respuesta = trades_client.aceptar(offer_id)
    if not respuesta.ok:
        registro.marcar(offer_id, estado="cancelada")
        log.info("No se acepto %s (%s)", offer_id, respuesta.status)
        return False
    datos = normalizar(respuesta.datos if isinstance(respuesta.datos, dict) else {})
    order_id = datos.get("orderId")
    registro.marcar(offer_id, estado="cerrada" if order_id else "aceptando", order_id=order_id)
    if order_id:
        _cerrar_orden(offer_id, order_id, oferta.get("group"))
    log.info("Oferta aceptada %s", offer_id)
    return True


def refrescar(oferta) -> None:
    if oferta.estado == "cancelando":
        _cancelar(oferta)
        return
    if str(oferta.id).startswith("pend-"):
        # La oferta remota vive 60 min. Si a los 70 todavia no tiene id, se suelta.
        publicada = getattr(oferta, "publicada_en", None)
        if publicada is not None and publicada.tzinfo is None:
            publicada = publicada.replace(tzinfo=timezone.utc)
        if publicada is not None and datetime.now(timezone.utc) - publicada > timedelta(minutes=70):
            _liberar_fisico(oferta)
            registro.marcar(oferta.id, estado="expirada")
        return
    respuesta = trades_client.obtener(oferta.id)
    if not respuesta.ok or not isinstance(respuesta.datos, dict):
        return
    datos = normalizar(respuesta.datos)
    estado = estado_local(datos.get("status"))
    if estado in (None, "abierta"):
        return
    if estado in ("expirada", "cancelada"):
        _liberar_fisico(oferta)
        registro.marcar(oferta.id, estado=estado)
        log.info("Oferta %s %s", oferta.id, estado)
        return
    if estado == "cerrada":
        order_id = datos.get("orderId") or oferta.order_id
        if not order_id:
            return
        _cerrar_orden(oferta.id, order_id, datos.get("group"))


def reconciliar(ofertas_remotas: list[dict]) -> None:
    """Ata un id remoto a una publicacion local que no alcanzo a renombrarse."""
    for remota in ofertas_remotas:
        if not remota.get("id") or registro.existe(remota["id"]):
            continue
        grupo = remota.get("group")
        if grupo not in (None, config.FARMA_GROUP):
            continue
        local = registro.pendiente_parecida(
            remota.get("sku"), remota.get("side"), int(remota.get("quantity") or 0),
            int(remota.get("unitPrice") or 0),
        )
        if local is None:
            continue
        registro.renombrar(local, remota["id"])
        registro.marcar(remota["id"], estado="abierta")
        log.warning("Oferta %s reconciliada con %s", local, remota["id"])


def _cerrar_orden(oferta_id: str, order_id: str, grupo_remoto) -> None:
    from app.db import SessionLocal
    from app.mercado.modelos import OfertaMercado

    with SessionLocal() as s:
        oferta = s.get(OfertaMercado, oferta_id)
        if oferta is None:
            return
        rol = oferta.rol
        sku, cantidad, precio = oferta.sku, oferta.cantidad, oferta.precio_unitario
        contraparte = oferta.contraparte_grupo
    if grupo_remoto is not None and int(grupo_remoto) != config.FARMA_GROUP:
        contraparte = int(grupo_remoto)
    venta_id = None
    if rol == "vendedor":
        venta_id = custodia.cerrar_venta_mercado(
            custodia.ids_de_oferta(oferta_id), sku, cantidad, precio, order_id, contraparte,
        )
    orden.registrar(order_id, sku, cantidad, precio, contraparte, rol, venta_id, oferta_id)
    registro.marcar(oferta_id, estado="cerrada", order_id=order_id, contraparte_grupo=contraparte)


def _cancelar(oferta) -> None:
    if not str(oferta.id).startswith("pend-"):
        respuesta = trades_client.cancelar(oferta.id)
        if not respuesta.ok and respuesta.status not in (404, 409):
            log.warning("No se pudo cancelar %s (%s)", oferta.id, respuesta.status)
            return
    _liberar_fisico(oferta)
    registro.marcar(oferta.id, estado="cancelada")


def _liberar_fisico(oferta) -> None:
    if oferta.rol != "vendedor":
        return
    ids = custodia.liberar_oferta(oferta.id)
    _sacar_de_despacho(oferta.sku, ids)


def _revertir(oferta_id: str, sku: str, ids: list[str]) -> None:
    custodia.liberar_oferta(oferta_id)
    _sacar_de_despacho(sku, ids)
    registro.marcar(oferta_id, estado="cancelada")


def _mover_a_despacho(ids: list[str]) -> bool:
    for uid in ids:
        try:
            operaciones.mover(uid, "checkOut")
        except Exception:
            log.exception("No se pudo mover %s a despacho", uid)
            return False
    return True


def _sacar_de_despacho(sku: str, ids: list[str]) -> None:
    for uid in ids:
        if custodia.espacio_de(uid) != "checkOut":
            continue
        destino = "bodega"
        try:
            if operaciones.es_frio(sku):
                from app import espacios as esp
                destino = "cold" if esp.libres("cold") > 0 else "buffer"
        except Exception:
            log.exception("No se supo si %s es frio; vuelve a bodega", sku)
        try:
            operaciones.mover(uid, destino)
        except Exception:
            log.exception("No se pudo sacar %s de despacho", uid)


def _id_remoto(respuesta) -> str | None:
    if not isinstance(getattr(respuesta, "datos", None), dict):
        return None
    return normalizar(respuesta.datos).get("id")
