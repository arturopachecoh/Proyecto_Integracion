# Distribuidora 4 — IIC3103

Grupo 4. Portal de venta, visor de trazabilidad y custodia (FastAPI + worker + Postgres + SPA Vite).

## URLs

| Qué | Dónde |
|---|---|
| Portal | https://choripan4.ing.uc.cl/ |
| Visor | https://choripan4.ing.uc.cl/trazabilidad |
| Pedidos | https://choripan4.ing.uc.cl/pedidos |
| Health | https://choripan4.ing.uc.cl/health |

El hostname del enunciado (`distribuidor4.ing.uc.cl`) no resuelve. El HTTPS público es **choripan4**.

Local: `http://127.0.0.1:3000` (Docker publica Uvicorn ahí; Nginx en el servidor hace proxy a ese puerto).

Diagramas de secuencia: [`docs/diagramas.md`](docs/diagramas.md). Prompts de IA: [`docs/prompts/`](docs/prompts/). Declaración: [`docs/declaracion-uso-ia.md`](docs/declaracion-uso-ia.md).

## Levantar en local

```bash
cp .env.example .env
# Completar secretos en .env. Defaults razonables:
#   CHECKOUT_MODE=mock
#   DISPATCH_FARMA=0

docker compose up --build
docker compose run --rm web alembic upgrade head
```

Portal en `http://127.0.0.1:3000`. El frontend se construye en la imagen (Vite → `web/dist`). En el servidor no corre Node.

Producir kits (el worker tiene que estar arriba: registra llegadas y cuida el frío):

```bash
docker compose run --rm worker python -m app.scripts.producir KIT-RESP-ADULTO 3 --plan
```

En PROD el script pide confirmar. No correr `sembrar_demo` en PROD.

Tests:

```bash
python -m unittest tests/test_checkout_pow.py
```

## Deploy (PROD)

En la VM, directorio `~/Proyecto_Integracion/Proyecto`:

```bash
git pull
docker compose stop worker
docker compose build web
docker compose up -d web
docker compose up -d worker
docker compose ps
curl -sS http://127.0.0.1:3000/health
```

**Nunca** `docker compose down -v`: borra el volumen `pgdata` y el registro de custodia.

Logs: `docker compose logs -f web` / `worker`.

## Declaración de uso de IA

Texto completo: [`docs/declaracion-uso-ia.md`](docs/declaracion-uso-ia.md).

Los dos prompts con los que se trabajó en Cursor:

- [`docs/prompts/prompt-analisis-plan.md`](docs/prompts/prompt-analisis-plan.md)
- [`docs/prompts/prompt-arquitectura-decisiones.md`](docs/prompts/prompt-arquitectura-decisiones.md)
