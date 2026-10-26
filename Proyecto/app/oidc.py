"""Verificacion de los webhooks que firma Google (token OIDC de una cuenta de servicio).

verify_oauth2_token revisa la firma, la vigencia, la audiencia y que el emisor
sea Google. Aca se agrega que el remitente sea la cuenta esperada.
"""
import requests
from cachecontrol import CacheControl
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from app.config import GCP_PROYECTO_CURSO

# Los certificados de Google se cachean segun sus cabeceras HTTP: sin esto
# cada webhook los descargaria de nuevo
_request = google_requests.Request(session=CacheControl(requests.Session()))


class TokenInvalido(Exception):
    """El request no trae un token valido de la cuenta esperada: responder 401."""


def verificar(authorization: str | None, audiencia: str, email: str | None) -> dict:
    """email: cuenta exacta esperada. Si es None o vacio, se acepta cualquier
    cuenta de servicio del proyecto del curso. Devuelve el payload del token."""
    if not authorization or not authorization.startswith("Bearer "):
        raise TokenInvalido("falta el token Bearer")
    token = authorization[len("Bearer "):].strip()
    try:
        payload = id_token.verify_oauth2_token(token, _request, audience=audiencia)
    except ValueError as e:
        raise TokenInvalido(f"token invalido: {e}") from e
    remitente = payload.get("email") or ""
    if not payload.get("email_verified"):
        raise TokenInvalido(f"email no verificado: {remitente}")
    if email:
        if remitente != email:
            raise TokenInvalido(f"remitente no autorizado: {remitente}")
    elif not remitente.endswith(f"@{GCP_PROYECTO_CURSO}.iam.gserviceaccount.com"):
        raise TokenInvalido(f"remitente fuera del proyecto del curso: {remitente}")
    return payload
