"""Siembra un grafo de demostración (BLI-AMOXI-500 → KIT-RESP-ADULTO) para probar el visor
y el portal en local sin fabricar en Farma.

Uso (con el stack arriba):
  docker compose run --rm worker python -m app.scripts.sembrar_demo
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.db import SessionLocal
from app.models import (
    Consumo, Lote, LotRelation, Movimiento, Solicitud, Unidad, Venta, VentaItem, VentaUnidad,
)

AHORA = datetime.now(timezone.utc)
VENCE = AHORA + timedelta(days=14)
CODIGO_BLI = "L-DEMO-BLIAMOXI-7F3A"
CODIGO_KIT = "L-DEMO-KITRESP-AXE1"


def _lote(s, codigo: str, **kw) -> Lote:
    existente = s.scalar(select(Lote).where(Lote.codigo == codigo))
    if existente:
        return existente
    lote = Lote(codigo=codigo, **kw)
    s.add(lote)
    s.flush()
    return lote


def _unidad(s, uid: str, lote: Lote, espacio: str | None, estado: str) -> None:
    if s.get(Unidad, uid):
        return
    s.add(Unidad(id=uid, lote_id=lote.id, sku=lote.sku, espacio_actual=espacio,
                 estado=estado, vence_en=VENCE))
    s.flush()
    tipo = "generacion" if lote.origen == "produccion" else "recepcion"
    s.add(Movimiento(unidad_id=uid, lote_id=lote.id, tipo=tipo, desde=None, hacia=espacio))


def _relacion(s, parent: Lote, child: Lote, cantidad: int, solicitud_id: int) -> None:
    existe = s.scalar(select(LotRelation.id).where(
        LotRelation.parent_lote_id == parent.id, LotRelation.child_lote_id == child.id))
    if existe is None:
        s.add(LotRelation(parent_lote_id=parent.id, child_lote_id=child.id,
                          cantidad=cantidad, solicitud_id=solicitud_id))


def main() -> None:
    with SessionLocal.begin() as s:
        if s.scalar(select(Lote).where(Lote.codigo == CODIGO_BLI)):
            print(f"Demo ya existe. Visor: /trazabilidad?lote={CODIGO_BLI}")
            return
        sol_api = Solicitud(tipo="compra", sku="API-AMOXI-500", cantidad=432,
                            challenge_id="demo-ch-api", llega_en=AHORA, estado="recibida")
        sol_exc = Solicitud(tipo="compra", sku="EXC-LACTOSA-DC", cantidad=288,
                            challenge_id="demo-ch-exc", llega_en=AHORA, estado="recibida")
        sol_lam = Solicitud(tipo="compra", sku="LAM-BLISTER-PVC", cantidad=36,
                            challenge_id="demo-ch-lam", llega_en=AHORA, estado="recibida")
        sol_bli = Solicitud(tipo="fabricacion", sku="BLI-AMOXI-500", cantidad=36,
                            challenge_id="demo-ch-bli", llega_en=AHORA, estado="recibida")
        sol_kit = Solicitud(tipo="fabricacion", sku="KIT-RESP-ADULTO", cantidad=12,
                            challenge_id="demo-ch-kit", llega_en=AHORA, estado="recibida")
        s.add_all([sol_api, sol_exc, sol_lam, sol_bli, sol_kit])
        s.flush()

        api = _lote(s, "L-DEMO-APIAMOX-11C2", sku="API-AMOXI-500", cantidad_inicial=432,
                    vence_en=VENCE, origen="farma_central", solicitud_id=sol_api.id)
        exc = _lote(s, "L-DEMO-EXCLACT-9904", sku="EXC-LACTOSA-DC", cantidad_inicial=288,
                    vence_en=VENCE, origen="distribuidora", origen_grupo=12, solicitud_id=sol_exc.id)
        lam = _lote(s, "L-DEMO-LAMBLIS-3077", sku="LAM-BLISTER-PVC", cantidad_inicial=36,
                    vence_en=VENCE, origen="farma_central", solicitud_id=sol_lam.id)
        bli = _lote(s, CODIGO_BLI, sku="BLI-AMOXI-500", cantidad_inicial=36,
                    vence_en=VENCE, origen="produccion", solicitud_id=sol_bli.id)
        kit = _lote(s, CODIGO_KIT, sku="KIT-RESP-ADULTO", cantidad_inicial=12,
                    vence_en=VENCE, origen="produccion", solicitud_id=sol_kit.id)

        _relacion(s, api, bli, 432, sol_bli.id)
        _relacion(s, exc, bli, 288, sol_bli.id)
        _relacion(s, lam, bli, 36, sol_bli.id)
        _relacion(s, bli, kit, 12, sol_kit.id)

        for i in range(4):
            _unidad(s, f"demo-bli-stock-{i:02d}", bli, "packaging", "en_stock")
        for i in range(12):
            uid = f"demo-bli-cons-{i:02d}"
            _unidad(s, uid, bli, None, "consumida")
            if s.scalar(select(Consumo.id).where(Consumo.unidad_id == uid)) is None:
                s.add(Consumo(solicitud_id=sol_kit.id, unidad_id=uid, lote_id=bli.id))
                s.add(Movimiento(unidad_id=uid, lote_id=bli.id, tipo="consumo",
                                 desde="packaging", hacia=None, solicitud_id=sol_kit.id))
        despachadas = []
        for i in range(20):
            uid = f"demo-bli-desp-{i:02d}"
            _unidad(s, uid, bli, None, "despachada")
            despachadas.append(uid)
        for i in range(12):
            _unidad(s, f"demo-kit-stock-{i:02d}", kit, "bodega", "en_stock")

        if s.scalar(select(Venta).where(Venta.transaccion_id == "demo-tx-portal")) is None:
            v = Venta(comprador_nombre="Hospital El Salvador",
                      comprador_email="compras@elsalvador.cl",
                      transaccion_id="demo-tx-portal", estado="pagada",
                      total=10900, pagada_en=AHORA)
            s.add(v)
            s.flush()
            s.add(VentaItem(venta_id=v.id, sku="BLI-AMOXI-500", cantidad=20, precio_unitario=545))
            for uid in despachadas:
                s.add(VentaUnidad(venta_id=v.id, unidad_id=uid, lote_id=bli.id, estado="despachada",
                                  despachada_en=AHORA))
                s.add(Movimiento(unidad_id=uid, lote_id=bli.id, tipo="despacho",
                                 desde="checkOut", hacia=None, venta_id=v.id))

    print(f"Demo lista. Visor: /trazabilidad?lote={CODIGO_BLI}")
    print(f"Kit con stock: {CODIGO_KIT} (12 x KIT-RESP-ADULTO)")


if __name__ == "__main__":
    main()
