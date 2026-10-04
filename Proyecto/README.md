# Distribuidora 4 - IIC3103

## Correr en local (ambiente dev)

    cp .env.example .env        # completar con credenciales de DEV
    docker compose up --build
    # abrir http://localhost:3000/health

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
