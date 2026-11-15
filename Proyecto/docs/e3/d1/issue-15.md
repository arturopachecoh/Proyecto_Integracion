# Issue 15 — no pedirle a Farma lo que va a rechazar

https://github.com/arturopachecoh/Proyecto_Integracion/issues/15

## Qué quedó

`comprar()` pregunta `puede_comprar_en_farma` **antes** de leer el catálogo y antes del PoW. Para el grupo 4, estos cuatro SKU levantan `InsumoNoDisponible` y no sale ningún POST:

- `EXC-LACTOSA-DC`
- `FRA-VIDRIO-120`
- `VIA-VIDRIO-10`
- `EXC-JARABE-BASE`

`LAM-BLISTER-PVC`, `EXC-SUERO-FISIO` y `SOB-PAPEL-EST` siguen el camino de siempre.

## Supuestos

- La tabla es la del enunciado y no cambia durante la entrega. Vive en `app/mercado/escasez.py`. El grupo sale de `FARMA_GROUP`, no está clavado en 4, para que el mismo código sirva si el `.env` es de otro grupo.
- Un SKU que no está entre los siete críticos se puede comprar. El enunciado solo cierra esos insumos.
- `produccion.una_vuelta` atrapa `InsumoNoDisponible` y lo deja en `log.info`. El issue pedía no tocar esa función. La dejé igual para cualquier otro error (`log.exception`), pero este caso es esperable en cada vuelta de las 60 h: si sube como traza, el log del reponedor se llena de un fallo que no es un fallo. El reponedor sigue; el worker de mercado es el que compra ese insumo.

## Prueba

`tests/test_escasez.py`. La lactosa no llama a `catalogo` ni al PoW. El blister sí llega a `registrar_compra`.
