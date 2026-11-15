# Issue 17 — ofertas y unidades reservadas

https://github.com/arturopachecoh/Proyecto_Integracion/issues/17

## Qué quedó

Tablas `ofertas_mercado`, `oferta_unidades` y `mercado_faltantes`. Migración nueva `e3d1a0mercado` (revisa `e2c7a3f1b8d2`). No se editó ninguna migración ya aplicada. No se agregó `lotes.parent_id`.

`apartar_para_oferta` deja la unidad en `reservada` y la anota en `oferta_unidades` **antes** de moverla a `checkOut`. Si alguna no está `en_stock`, no aparta ninguna. `liberar_oferta` devuelve a `en_stock` solo las que siguen `reservada` y borra el vínculo, para que la misma unidad se pueda ofrecer después. El historial queda en `movimientos` y, si se vendió, en `venta_unidades`.

## Supuestos

- No hay un estado nuevo de unidad. `reservada` ya existe y el despacho solo toma `en_stock`. La fila de `oferta_unidades` es el candado extra: `unidades_disponibles` y `stock_disponible` también la excluyen, y `devolver_desde_checkout` no se lleva lo que está en una oferta viva (issue 22 permitía ese filtro). `worker/pedidos.py` no se tocó.
- Estados de más, fuera de los cuatro del enunciado: `publicando`, `aceptando`, `cancelando`. Sirven si el proceso muere entre el POST y la anotación. Una oferta `pend-...` que a los 70 minutos sigue sin id remoto se suelta (la oferta en Farma dura 60).
- El id local es `pend-{uuid}` hasta que el POST devuelve el id. Se renombra con `UPDATE` y la FK de `oferta_unidades` es `ON UPDATE CASCADE`.
- `stock_disponible` ahora lee `ofertas_mercado`. Sin la migración, esa consulta falla. Alembic va antes del restart. Ver [README](README.md).

## Prueba

`tests/test_mercado_db.py` contra `TEST_DATABASE_URL` (Postgres desechable, nunca la VM). Apartar 2 de 5 deja 3 vendibles; liberar las devuelve. Una unidad ya reservada por una OC no se aparta.
