# Distribuidora 4 - IIC3103

Portal: `/` · Trazabilidad: `/trazabilidad` · Health: `/health`

## Correr en local (ambiente dev)

    cp .env.example .env        # completar secretos; CHECKOUT_MODE=mock por defecto
    docker compose up --build
    docker compose run --rm web alembic upgrade head
    docker compose run --rm worker python -m app.scripts.sembrar_demo   # grafo + stock demo (opcional)
    python -m unittest tests/test_checkout_pow.py
    npx --yes playwright@1.55.1 install chromium
    npx --yes playwright@1.55.1 test --config playwright.config.ts
    # abrir http://localhost:3000  y  /trazabilidad?lote=L-DEMO-BLIAMOXI-7F3A

El frontend se construye en la imagen (Vite → `web/dist`). En el servidor no corre Node.

## Deploy en el servidor (ambiente prod)

    cd ~/distribuidora4
    git pull
    docker compose up -d --build
    docker compose ps
    curl http://127.0.0.1:3000/health

Ver logs:

    docker compose logs -f web
    docker compose logs -f worker

NUNCA usar `docker compose down -v`: borra la base de datos (y el registro de custodia).

## Probar el solver de PoW

    docker compose run --rm worker python -m app.pow
