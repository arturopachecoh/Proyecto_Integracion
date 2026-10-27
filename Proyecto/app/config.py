import os

FARMA_ENV = os.getenv("FARMA_ENV", "dev")
DATABASE_URL = os.environ["DATABASE_URL"]

# Farma Central
FARMA_BASE_URL = os.getenv("FARMA_BASE_URL", "").rstrip("/")
FARMA_GROUP = int(os.getenv("FARMA_GROUP", "0"))
FARMA_API_KEY = os.getenv("FARMA_API_KEY", "")

# Integrapay: mismos group/secret que Farma salvo que se sobreescriban.
CHECKOUT_BASE_URL = os.getenv("CHECKOUT_BASE_URL", "").rstrip("/")
CHECKOUT_MODE = os.getenv("CHECKOUT_MODE", "mock")  # mock | real
CHECKOUT_FORCE = os.getenv("CHECKOUT_FORCE", "")  # exito | cancelado | error
CHECKOUT_GROUP = int(os.getenv("CHECKOUT_GROUP") or FARMA_GROUP or "0")
CHECKOUT_SECRET = os.getenv("CHECKOUT_SECRET") or FARMA_API_KEY

DISPATCH_FARMA = os.getenv("DISPATCH_FARMA", "0") == "1"
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:3000").rstrip("/")

# Sistema de ordenes de compra (mismo host que Farma Central)
ORDENES_BASE_URL = (os.getenv("ORDENES_BASE_URL") or FARMA_BASE_URL).rstrip("/")
ORDENES_SECRET = os.getenv("ORDENES_SECRET") or FARMA_API_KEY

# Casilla sFTP del grupo (Anexo 1 del enunciado E2)
SFTP_HOST = os.getenv("SFTP_HOST", "")
SFTP_PORT = int(os.getenv("SFTP_PORT", "22"))
SFTP_USER = os.getenv("SFTP_USER", "")
SFTP_PASSWORD = os.getenv("SFTP_PASSWORD", "")
SFTP_DIR = os.getenv("SFTP_DIR", ".")
SFTP_KNOWN_HOSTS = os.getenv("SFTP_KNOWN_HOSTS", "keys/known_hosts")

# Pub/Sub (Anexo 2): suscripcion pull propia del grupo
PUBSUB_PROJECT = "taller-integracion-310700"
PUBSUB_TOPIC = os.getenv(
    "PUBSUB_TOPIC",
    f"projects/{PUBSUB_PROJECT}/topics/{FARMA_ENV}.proyecto.2026-2.grupo{FARMA_GROUP}",
)
PUBSUB_SUBSCRIPTION = os.getenv(
    "PUBSUB_SUBSCRIPTION",
    f"projects/{PUBSUB_PROJECT}/subscriptions/grupo{FARMA_GROUP}-{FARMA_ENV}",
)
PUBSUB_KEY_FILE = os.getenv("PUBSUB_KEY_FILE", f"keys/pubsub-{FARMA_ENV}.json")

# Pedidos
MARGEN_DESPACHO_MIN = int(os.getenv("MARGEN_DESPACHO_MIN", "20"))
STOCK_MINIMO_DEFAULT = int(os.getenv("STOCK_MINIMO_DEFAULT", "5"))
STOCK_MINIMO = os.getenv("STOCK_MINIMO", "")  # excepciones: "KIT-DIABETES=2,KIT-GASTRO=4"
STOCK_EXTRA_PORTAL = int(os.getenv("STOCK_EXTRA_PORTAL", "2"))  # sobre el minimo, para vender en el portal

# Webhooks firmados por Google (token OIDC de una cuenta de servicio del curso)
GCP_PROYECTO_CURSO = "taller-integracion-310700"
MESSAGING_OIDC_EMAIL = os.getenv(
    "MESSAGING_OIDC_EMAIL", f"mensajeria@{GCP_PROYECTO_CURSO}.iam.gserviceaccount.com")
# Cuenta que firma los avisos de retiro. Si no se define, se acepta cualquier
# cuenta de servicio del proyecto del curso (con la audiencia exacta del endpoint)
RECALLS_OIDC_EMAIL = os.getenv("RECALLS_OIDC_EMAIL", "")

# Plataforma de mensajeria (mismo host que Farma Central)
MESSAGING_BASE_URL = (os.getenv("MESSAGING_BASE_URL") or FARMA_BASE_URL).rstrip("/")
MESSAGING_SECRET = os.getenv("MESSAGING_SECRET") or FARMA_API_KEY

# Gateway de modelos de lenguaje (API compatible con OpenAI)
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "").rstrip("/")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "")
