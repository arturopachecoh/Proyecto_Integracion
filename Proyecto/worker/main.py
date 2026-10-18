"""Mini worker de cadena de frio.

Al inicio de cada tick sincroniza las llegadas: registra en custodia las unidades
nuevas que aparecieron en cualquier espacio salvo cuarentena, para que los
traslados posteriores queden trazados.

Cada TICK_SECONDS revisa la recepcion y la bodega principal (que no refrigeran)
y mueve los productos que requieren frio a la camara de frio. Si la camara
esta llena, los manda a la bodega externa (refrigerada, pero cobra por hora).

En el area de acondicionamiento solo mueve los productos frios que NACIERON
ahi (fabricados). Los insumos frios que se dejaron para fabricar no se tocan:
sacarlos arruinaria la fabricacion.
"""
import logging
import os
import time

import httpx

from app import custodia, farma_client, ventas
from app import espacios as esp

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("frio")

TICK_SECONDS = 20          # 1% de vida util por minuto: hay que reaccionar rapido
MAX_MOVES_PER_TICK = 100   # el rate limit es 250 requests por minuto
CATALOG_REFRESH = 3600     # recargar catalogo cada hora
# Todos menos cuarentena: las compras que no caben en recepcion, el sandbox y
# parte de lo fabricado llegan directo a la bodega externa u otros espacios
ESPACIOS_LLEGADA = ("checkIn", "bodega", "cold", "buffer", "packaging", "checkOut")


def sincronizar_llegadas():
    for espacio in ESPACIOS_LLEGADA:
        store_id = esp.store_id(espacio)
        for item in farma_client.space_inventory(store_id):
            productos = farma_client.space_products(store_id, item["sku"], limit=200)
            custodia.registrar_llegadas(productos, espacio)


def tick(skus_frio: set[str]):
    try:
        sincronizar_llegadas()
    except Exception:
        # Si falla, igual hay que mover al frio: la cadena de frio va primero
        log.exception("Error sincronizando llegadas")

    libres = esp.libres("cold")
    movidos = 0

    # Productos frios que nacieron en acondicionamiento -> a la camara
    for u in custodia.nacidas_en_acondicionamiento(skus_frio):
        if movidos >= MAX_MOVES_PER_TICK:
            log.warning("Limite de movimientos por tick alcanzado; sigo en el proximo")
            return
        destino = "cold" if libres > 0 else "buffer"
        try:
            farma_client.move_product(u.id, esp.store_id(destino))
        except httpx.HTTPStatusError as e:
            log.error("No se pudo mover %s al frio: %s", u.id, e.response.text)
            if e.response.status_code == 429:
                return  # rate limit: esperar al proximo tick
            continue
        movidos += 1
        if destino == "cold":
            libres -= 1
        custodia.registrar_traslado(u.id, destino)
        log.info("Producto frio %s %s: packaging -> %s", u.sku, u.id, destino)

    for origen in ("checkIn", "bodega"):
        store_id = esp.store_id(origen)
        for item in farma_client.space_inventory(store_id):
            sku = item["sku"]
            if sku not in skus_frio:
                continue
            productos = farma_client.space_products(store_id, sku, limit=200)
            # Por si alguna unidad llego despues de la sincronizacion: asi nunca
            # se mueve algo que no este en custodia (ignora las ya conocidas)
            custodia.registrar_llegadas(productos, origen)
            for p in productos:
                if movidos >= MAX_MOVES_PER_TICK:
                    log.warning("Limite de movimientos por tick alcanzado; sigo en el proximo")
                    return
                destino = "cold" if libres > 0 else "buffer"
                try:
                    farma_client.move_product(p["_id"], esp.store_id(destino))
                except httpx.HTTPStatusError as e:
                    log.error("No se pudo mover %s (%s): %s", p["_id"], sku, e.response.text)
                    if e.response.status_code == 429:
                        return  # rate limit: esperar al proximo tick
                    continue
                movidos += 1
                if destino == "cold":
                    libres -= 1
                custodia.registrar_traslado(p["_id"], destino)
                log.info("Movido %s %s: %s -> %s", sku, p["_id"], origen, destino)

    if movidos:
        log.info("Tick: %d productos movidos al frio. Libres en camara: %d", movidos, libres)


def main():
    os.nice(10)  # prioridad baja frente al portal
    log.info("Worker de frio iniciado")
    skus_frio, cargado = set(), 0
    while True:
        try:
            if time.time() - cargado > CATALOG_REFRESH:
                catalogo = farma_client.available_products()
                skus_frio = {p["sku"] for p in catalogo if p["storage"]["cold"]}
                cargado = time.time()
                log.info("SKUs que requieren frio: %s", sorted(skus_frio))
            # Antes del tick: solo usa Postgres, asi corre aunque Farma este caida
            vencidas = custodia.vencer_expiradas()
            if vencidas:
                log.info("Marcadas %d unidades vencidas", vencidas)
            tick(skus_frio)
            ventas.recuperar_pendientes()
        except Exception:
            log.exception("Error en tick")  # un error no debe matar el worker
        time.sleep(TICK_SECONDS)


if __name__ == "__main__":
    main()