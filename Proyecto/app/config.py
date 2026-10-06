import os

FARMA_ENV = os.getenv("FARMA_ENV", "dev")
DATABASE_URL = os.environ["DATABASE_URL"]

# Farma Central
FARMA_BASE_URL = os.getenv("FARMA_BASE_URL", "").rstrip("/")
FARMA_GROUP = int(os.getenv("FARMA_GROUP", "0"))
FARMA_API_KEY = os.getenv("FARMA_API_KEY", "")

CHECKOUT_BASE_URL = os.getenv("CHECKOUT_BASE_URL", "")
CHECKOUT_MODE = os.getenv("CHECKOUT_MODE", "mock")  # mock | real
CHECKOUT_FORCE = os.getenv("CHECKOUT_FORCE", "")  # exito | cancelado | error
DISPATCH_FARMA = os.getenv("DISPATCH_FARMA", "0") == "1"
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:3000")
