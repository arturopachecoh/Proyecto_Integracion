# Estado actual (Entrega 1)

El grupo opera un backend Python (FastAPI) + worker + PostgreSQL 16.
Farma Central, PoW, custodia de compra/fabricación/traslado y producción de kits
ya existían. Encima se agregó genealogía `lot_relations`, portal estático y checkout mock.

## Qué corre

- `web`: FastAPI en `0.0.0.0:8000`, publicado en `127.0.0.1:3000` para Nginx.
- `worker`: cadena de frío cada 20s y reintento de despachos pagados pendientes.
- `db`: Postgres 16, volumen `pgdata` (no usar `docker compose down -v`).
- Frontend: SPA Vite/React compilada a `web/dist`, servida por FastAPI. En producción no corre Node.

## Módulos

- `app/farma_client.py` — único HTTP a Farma.
- `app/operaciones.py` / `app/produccion.py` — comprar, fabricar, orquestar kits.
- `app/custodia.py` — único writer de trazabilidad.
- `app/trazabilidad.py` — las cuatro preguntas (solo Postgres).
- `app/catalogo.py` / `app/ventas.py` — portal y checkout.
- `app/integrations/checkout.py` — pasarela mock por defecto.

## Modelo

`solicitudes`, `lotes`, `unidades`, `movimientos`, `consumos`, `lot_relations`,
`ventas`, `venta_items`, `venta_unidades`.

No se migró a TypeScript ni a Next.js. No se renombraron las tablas del compañero.
