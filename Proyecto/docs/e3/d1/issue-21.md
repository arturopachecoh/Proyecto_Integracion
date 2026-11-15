# Issue 21 — recall de un lote que no pasó, y venta de mercado sin aviso

https://github.com/arturopachecoh/Proyecto_Integracion/issues/21

## Qué quedó

Si `investigar` no encuentra el lote ni por `codigo` ni por `lote_proveedor`, loguea en info «el lote no paso por esta distribuidora» y devuelve la investigación vacía. El reporte vacío se sigue enviando. No hay cuarentena ni notificación, porque no hay unidades. Antes ese caso era `log.error`.

Las entregas de una OC `canal=mercado` siguen en el reporte (`deliveries`) y no entran a `notificar_retiro`. Si no hay OC local, se notifica como en la E2: puede ser una venta por sFTP, Pub/Sub o mensajería que todavía no está en esta base, y el enunciado solo pide callar las del mercado.

No se tocó el webhook ni `worker/pedidos.py`. El filtro está en `procesamiento._notificables`.

Si el lote retirado tenía unidades en una oferta viva, el retiro las pasa a cuarentena, borra el vínculo y deja la oferta en `cancelando`. El worker de mercado manda el POST de cancel en el tick siguiente. Si la tabla no existe, el savepoint se deshace y la cuarentena igual queda.

## Supuestos

- «No pasó por aquí» es lote desconocido, no un lote nuestro con cero unidades en stock. Ese segundo caso ya reportaba vacío y se dejó igual.
- El aviso que se omite es solo `notificar_retiro`. El reporte a Farma sí incluye la entrega, porque el enunciado pide reportar las entregas y no notificar al comprador del mercado (Farma ya armó esa OC).
- Cancelar una oferta por recall puede recibir 404 o 409. Los dos se toman como «ya no está abierta» y la fila local pasa a `cancelada`.

## Prueba

`tests/test_mercado_db.py`: un código que no existe no loguea ERROR y la investigación vuelve vacía. Una venta de mercado queda en `entregas` y `_notificables` la saca.

`tests/test_retiros_db.py` sigue en verde: las OC de sFTP se notifican como antes. `tests/test_mercado.py` cubre el filtro sin base.
