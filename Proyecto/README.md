# Distribuidora 4 — IIC3103 Entrega 1

Grupo 4. Portal de venta, visor de trazabilidad y custodia local (FastAPI + worker + Postgres + SPA Vite).

- Portal: `https://choripan4.ing.uc.cl/`
- Visor: `https://choripan4.ing.uc.cl/trazabilidad`
- Pedidos: `https://choripan4.ing.uc.cl/pedidos`
- Health: `/health`

El hostname del enunciado (`distribuidor4.ing.uc.cl`) no resuelve; el HTTPS público es **choripan4**.

**Diseño entregado (Canvas):** [`docs/informe-e1/Informe_Entrega1_Distribuidora4.pdf`](docs/informe-e1/Informe_Entrega1_Distribuidora4.pdf). Fuente: [`docs/informe-e1/`](docs/informe-e1/). Diagramas a tamaño real: [`docs/informe-e1/diagramas.md`](docs/informe-e1/diagramas.md).

Otros docs: `docs/01_enunciado_proyecto_llm.md` (requisitos), `docs/02_arquitectura_decisiones_entrega1.md` (propuesta inicial, **no** es lo implementado).

## Correr en local

```bash
cp .env.example .env        # solo nombres; completar secretos en .env
# CHECKOUT_MODE=mock por defecto; DISPATCH_FARMA=0
docker compose up --build
docker compose run --rm web alembic upgrade head
# opcional, NUNCA en PROD:
# docker compose run --rm worker python -m app.scripts.sembrar_demo
python -m unittest tests/test_checkout_pow.py
npx --yes playwright@1.55.1 install chromium
npx --yes playwright@1.55.1 test --config playwright.config.ts
# http://127.0.0.1:3000  y  /trazabilidad?lote=...
```

El frontend se construye en la imagen (Vite → `web/dist`). En el servidor no corre Node.

## Deploy (PROD)

```bash
cd ~/Proyecto_Integracion/Proyecto
git pull
docker compose stop worker
docker compose build web
docker compose up -d web
docker compose up -d worker
docker compose ps
curl -sS http://127.0.0.1:3000/health
```

**NUNCA** `docker compose down -v`: borra `pgdata` y el registro de custodia.

Logs: `docker compose logs -f web` / `worker`.

PoW: `docker compose run --rm worker python -m app.pow`

## Declaración de uso de IA

El enunciado (§18) exige declararlo en el informe. Resumen para el README:

- **Herramientas:** Cursor (agente, modelo Grok) para código e informe; Graphify y Codebase Memory para mapa de módulos y símbolos; Playwright para verificar el portal y el visor; OpenAPI de Farma/Integrapay para los contratos HTTP.
- **Tareas:** completar custodia N:M, portal, adapter de pagos, visor, deploy en la VM, y redactar `docs/informe-e1/` con diagramas instanciados (no genéricos).
- **Verificación:** tests `tests/test_checkout_pow.py`, click-through Playwright, contrastar Graphify/`trace_path` con `app/operaciones.py` y `app/ventas.py`, números de `logs.txt` y ventas PROD. Cada integrante tiene que poder explicar reserva FEFO, visor solo-Postgres y por qué el PoW no corre dentro de Uvicorn.

Detalle: [`docs/informe-e1/06-declaracion-ia.md`](docs/informe-e1/06-declaracion-ia.md).
