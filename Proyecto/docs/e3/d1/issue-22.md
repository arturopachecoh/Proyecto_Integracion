# Issue 22 — banda de precio y unidades que el despacho no puede tocar

https://github.com/arturopachecoh/Proyecto_Integracion/issues/22

## Qué quedó

La banda es 0,5× a 1,5× el precio de `market_prices()` en el momento de publicar o aceptar. El redondeo es medio hacia arriba (`int(valor + 0.5)`), solo para precios positivos. El lector es el mismo del portal: `catalogo._mapa_precios`. No hay otro modelo ni SOAP.

Un precio a 1,6× no se publica. Uno a 0,4× no se acepta. Si no hay precio vigente, no se publica ni se acepta: Farma rechazaría la oferta y no tiene sentido gastar el intento.

Las unidades de una oferta de venta están `reservada` y listadas en `oferta_unidades`. `unidades_disponibles` no las devuelve, así que una OC de cliente no se las lleva. `devolver_desde_checkout` tampoco: aunque estuvieran `en_stock` en `checkOut`, el id está en la oferta viva. Ese es el único cambio en `app/pedidos/despachador.py`. El worker de pedidos no se editó.

`app/main.py` no importa el mercado. El portal no cambia.

## Supuestos

- El precio vigente es un entero, como lo parsea el portal. No se vuelve a consultar Farma dentro de la misma decisión de banda: una llamada a `vigente(sku)` arma el mapa y se usa ese número para el piso y el techo.
- La baja de 0,1× por oferta expirada mira solo las ventas propias de ese SKU, las más recientes, y se corta en la primera que no está `expirada`. Una cancelación corta la racha.
- Los tests no abren red. El ciclo se prueba con el cliente y la custodia parcheados. La base, cuando corre, es `TEST_DATABASE_URL`.

## Prueba

`tests/test_mercado.py` (banda, 1,6×, portal) y `tests/test_pedidos_db.py` (`devolver_desde_checkout` sigue sin tocar reservadas, ahora con la tabla de ofertas creada).
