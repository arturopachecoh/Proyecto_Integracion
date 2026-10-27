"""Crea la suscripcion pull del grupo. Se corre una vez por ambiente.

  docker compose run --rm --no-deps -v "$PWD/keys:/keys-rw" pedidos \
      python -m app.scripts.crear_suscripcion /keys-rw/pubsub-dev.json

Guarda la llave de la cuenta de servicio en la ruta indicada (permisos 600)
y crea la suscripcion. Si ya existe, no hace nada.
"""
import json
import os
import sys
from pathlib import Path

import google.auth.transport.requests
import httpx
from google.oauth2 import service_account

from app import ordenes_client
from app.canales.pubsub import API, SCOPES
from app.config import PUBSUB_SUBSCRIPTION, PUBSUB_TOPIC


def main(salida: str) -> None:
    llave = ordenes_client.pubsub_key()
    ruta = Path(salida)
    # se crea ya con permisos 600: nunca queda legible por otros usuarios
    fd = os.open(ruta, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(json.dumps(llave))
    os.chmod(ruta, 0o600)  # por si el archivo ya existia con otros permisos
    print(f"Llave guardada en {ruta}")

    cred = service_account.Credentials.from_service_account_info(llave, scopes=SCOPES)
    cred.refresh(google.auth.transport.requests.Request())
    r = httpx.put(
        f"{API}/{PUBSUB_SUBSCRIPTION}",
        json={"topic": PUBSUB_TOPIC, "ackDeadlineSeconds": 60,
              "messageRetentionDuration": "604800s"},
        headers={"Authorization": f"Bearer {cred.token}"},
        timeout=30,
    )
    if r.status_code == 409:
        print(f"La suscripcion {PUBSUB_SUBSCRIPTION} ya existia")
        return
    r.raise_for_status()
    print(f"Suscripcion {PUBSUB_SUBSCRIPTION} creada sobre {PUBSUB_TOPIC}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Uso: python -m app.scripts.crear_suscripcion <ruta de la llave>")
    main(sys.argv[1])
