# Distribuidora 4 - IIC3103

Portal: `/` · Trazabilidad: `/trazabilidad` · Health: `/health`

## Correr en local (ambiente dev)

    cp .env.example .env        # completar secretos; CHECKOUT_MODE=mock por defecto
    docker compose up --build
    docker compose run --rm web alembic upgrade head
    # abrir http://localhost:3000  (compose publica 127.0.0.1:3000)

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
