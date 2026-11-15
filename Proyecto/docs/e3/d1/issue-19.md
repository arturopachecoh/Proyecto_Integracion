# Issue 19 — la compra llega con el lote del vendedor

https://github.com/arturopachecoh/Proyecto_Integracion/issues/19

## Qué quedó

`registrar_llegadas` no se movió de sitio y `worker/main.py` no se editó. Cuando un lote nuevo no tiene solicitud, `_aplicar_origen_mercado` pregunta si esa llegada cubre una compra de mercado.

Si el JSON trae un solo grupo vendedor, o si hay una oferta `rol=comprador` en `cerrada` o `aceptando` con `recibidas < cantidad`, el lote queda:

- `origen = distribuidora`
- `origen_grupo` = ese grupo
- `lote_proveedor` = el batch original

`recibidas` sube para no atribuirle llegadas de más. La investigación de retiros busca por `lotes.codigo` o por `lotes.lote_proveedor`, así que un recall del lote del vendedor encuentra estas unidades.

## Supuestos

- La oferta local se inserta en `aceptando` **antes** del POST de accept. Si las unidades aparecen mientras el request sigue abierto, la llegada ya tiene a quién atribuirse.
- Grupo en el producto: `sellerGroup`, `group`, `fromGroup`, `ownerGroup`, `providerGroup`, `grupo`. Si hay más de un grupo distinto en la misma llegada, no se usa el JSON y se toma `contraparte_grupo` de la oferta.
- Batch original: `originalBatch`, `sourceBatch`, `lotId`, `lote`. Si no viene ninguno, se guarda el `batch` que muestra Farma (es el código con el que la unidad entra a custodia).
- Si la tabla de ofertas no existe, el savepoint se deshace y el lote queda `farma_central`, como hasta ahora. La recepción no se pierde.
- Una llegada que sí calza con una `Solicitud` no se reetiqueta. Eso sigue siendo compra o fabricación nuestra.

## Prueba

`tests/test_mercado_db.py`: con una oferta de compra cerrada, la llegada queda `origen=distribuidora`, grupo 2, y `investigar` la encuentra por el código del lote.
