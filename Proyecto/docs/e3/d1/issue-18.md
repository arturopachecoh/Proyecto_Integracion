# Issue 18 — worker de mercado

https://github.com/arturopachecoh/Proyecto_Integracion/issues/18

## Qué quedó

`worker/mercado.py` corre `ciclo.tick` cada `MERCADO_TICK_SECONDS` (60). `os.nice(10)`. Tope `MERCADO_MAX_REQUESTS` (20) por tick. Candado de Postgres `4_000_012`: si ya hay otra copia, el tick se salta.

No se editaron `docker-compose.yml`, `app/main.py`, `worker/main.py`, `worker/pedidos.py`, `worker/reponedor.py` ni mensajería. El servicio entra por `docker-compose.mercado.yml`.

Cada tick: reconcilia publicaciones a medias, refresca las ofertas vivas, compra lo que falta y publica el excedente.

## Supuestos

- El piso de compra y la reserva de venta son el mismo número: `MERCADO_LOTE` (10). No se publica una venta si el excedente es menor que ese lote, y no se acepta una venta ajena más grande que `min(faltante, MERCADO_LOTE)`. El enunciado no fija el tamaño; 10 es una tanda corta que cabe en el espacio y no vacía la bodega.
- Lo “comprometido” de materia prima se trata como 0. Las OC piden kits, no estos SKU. `reposicion.faltantes` sigue siendo de kits y este worker no la usa.
- El reloj de escasez vive en `mercado_faltantes`. Un reinicio no pone la espera de 30 minutos en cero.
- Precio de venta: parte en 1,0× y baja 0,1× por cada venta propia seguida que expiró, con piso 0,5×. Precio de compra: el piso de la banda. Sin precio vigente no se publica ni se acepta.
- No se abre una segunda compra o venta del mismo SKU mientras haya una en `publicando`, `abierta` o `aceptando`.
- Si la oferta ajena no trae grupo, igual se intenta aceptar. Un 4xx la deja `cancelada` y no se reintenta ese id. Si el grupo es el nuestro, no se acepta.
- No se compra el producto terminado cuando el insumo no aparece. La historia lo mencionaba. Quedó afuera: `catalogo()` pega a Farma, y lo que Farma le niega al grupo son los insumos, no los kits. El worker compra el insumo. Si en la evaluación hiciera falta el kit, es un cambio aparte.
- No se consulta la API de espacios para ver si caben 10 unidades. El tope es `MERCADO_LOTE`. Si el move a `checkOut` falla, la oferta se revierte y las unidades vuelven a stock.
- Reconciliar une una fila `publicando` con una oferta remota del mismo SKU, lado, cantidad y precio, por si el POST llegó y el proceso murió antes de guardar el id.

## Prueba

`tests/test_mercado.py`: toma la sell más barata dentro de la banda, no repite una oferta ya vista, no publica otra venta si ya hay una abierta, y no publica a 1,6×.
