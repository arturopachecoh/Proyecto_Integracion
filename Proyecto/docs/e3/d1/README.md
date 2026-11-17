# Entrega 3 — desarrollador 1 (mercado de insumos)

Epic [#10](https://github.com/arturopachecoh/Proyecto_Integracion/issues/10).
Historias [#11](https://github.com/arturopachecoh/Proyecto_Integracion/issues/11)–[#14](https://github.com/arturopachecoh/Proyecto_Integracion/issues/14).
Tareas [#15](https://github.com/arturopachecoh/Proyecto_Integracion/issues/15)–[#22](https://github.com/arturopachecoh/Proyecto_Integracion/issues/22).

Rama `feat/e3-d1-mercado`, sacada de `develop`. No se tocó la VM, Farma, Checkout, SSH ni el servidor del curso. `CHECKOUT_MODE` y `DISPATCH_FARMA` quedan como estaban.

Este desarrollador mueve unidades y deja la orden de compra de mercado ya cumplida. No factura, no cobra y no interpreta mensajes. Eso es de los desarrolladores 2 y 3.

## Antes de reiniciar web o workers

La migración `e3d1a0mercado` crea `ofertas_mercado`, `oferta_unidades` y `mercado_faltantes`, y permite `canal=mercado` en `ordenes_compra`.

`stock_disponible` y `unidades_disponibles` consultan esas tablas. Si el código nuevo arranca sin la migración, el stock deja de responder. Hay que correr Alembic **antes** de reiniciar:

```bash
# desde Proyecto/, contra la base local, no contra la VM
alembic upgrade head
```

La recepción de llegadas y el retiro de un lote sí aguantan la tabla ausente (savepoint): si la migración no está, la llegada sigue siendo de Farma y la cuarentena igual se anota. El stock no tiene ese salvavidas.

## Cómo se corre

El servicio `mercado` está en `docker-compose.yml`, así que basta con:

```bash
docker compose up -d mercado
```

Variables opcionales en `.env.example` (bloque `# E3 mercado`, comentadas con sus valores por defecto).

## Decisiones por issue

| Issue | Archivo |
| --- | --- |
| #15 no comprar a Farma lo que el grupo no puede | [issue-15.md](issue-15.md) |
| #16 cliente HTTP `/trades` | [issue-16.md](issue-16.md) |
| #17 ofertas y reserva de unidades | [issue-17.md](issue-17.md) |
| #18 worker que publica y toma ofertas | [issue-18.md](issue-18.md) |
| #19 lote comprado con id original y grupo vendedor | [issue-19.md](issue-19.md) |
| #20 OC `canal=mercado` ya cumplida | [issue-20.md](issue-20.md) |
| #21 retiro vacío y venta de mercado sin aviso | [issue-21.md](issue-21.md) |
| #22 banda de precio y unidades que no se despachan | [issue-22.md](issue-22.md) |

## Qué no hace esta rama

- No llama a `emitInvoice` ni a `payInvoice`.
- No publica ni consume mensajes.
- No cambia el portal (`app/main.py` no importa `mercado` ni `trades_client`).
- No compra el producto terminado cuando falta el insumo. El worker compra el insumo. Ver issue 18.
