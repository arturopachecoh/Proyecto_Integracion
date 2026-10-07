# Plan de implementación y decisiones E1

El informe de diseño entregable está en `docs/informe-e1/`. Este archivo es la nota operativa de implementación.

Rama de integración: `develop`. Épicas ya mergeadas:
`epic/modelo-trazabilidad`, `epic/portal-venta`, `epic/pagos-despacho`,
`epic/visor-trazabilidad`, `epic/informe-infra`.

## Tres decisiones (informe)

1. **Python + worker, no Next.js.** Farma, PoW y custodia ya corrían. Un runtime Node extra no cabe bien en 2 GB. El portal es estático servido por FastAPI.
2. **Custodia local como fuente de verdad interna.** Farma no guarda el historial del grupo. Stock del portal sale de `unidades`, no del inventory crudo de Farma.
3. **`consumos` (unidad) + `lot_relations` (lote↔lote).** La N:M del enunciado queda explícita para el visor, sin borrar la granularidad de unidad.

## Estrategia operativa (números)

Alineada a `produccion.producir(..., tanda=10)`:

- **Reposición:** fabricar/comprar cuando `stock + en_camino` del kit no cubre una tanda de 10, respetando `tamano_lote` de Farma.
- **Cantidad de compra:** siempre múltiplo del batch; el orquestador redondea hacia arriba.
- **Bodega externa (`buffer`):** solo overflow de frío si la cámara está llena. Productos de ambiente se sacan del buffer a bodega.
- **Vencimiento:** FEFO con margen de 1 hora; el portal no ofrece vencidos ni reservados.
- **Precio +50%:** no adelantar tandas extra. **Precio −50%:** una tanda adicional solo si hay espacio en bodega/cámara, no en buffer de pago.

## Checkout

`CHECKOUT_MODE=mock` (default). ~20% error, ~10% cancelación, el resto éxito.
`DISPATCH_FARMA=0`: el despacho se registra en custodia sin mover en Farma.
No llamar Checkout/Farma reales sin autorización explícita.

## Levantar local

```bash
cp .env.example .env   # completar secretos propios
docker compose up --build
# migraciones: docker compose run --rm web alembic upgrade head
# http://localhost:3000  (mapeado a 127.0.0.1:3000)
```
