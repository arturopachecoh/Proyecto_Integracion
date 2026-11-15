# Issue 16 — cliente HTTP de `/trades`

https://github.com/arturopachecoh/Proyecto_Integracion/issues/16

## Qué quedó

`app/trades_client.py` publica, cancela, acepta, obtiene y lista. Aceptar es `POST /trades/offers/{id}/accept` sin cuerpo: la oferta es todo o nada.

401 renueva el token una vez. 429 espera `Ratelimit-Reset` (tope 60 s) más un segundo, hasta 6 intentos. 5xx no es éxito. Un 4xx de negocio se devuelve y lo decide quien llamó.

## Supuestos (no se llamó al servidor del curso)

- La auth no está descrita. Se asumió el mismo contrato que el resto de los sistemas del curso: `POST {TRADES_BASE_URL}/trades/auth` con `{group, secret}`.
- `TRADES_BASE_URL` vacío usa `FARMA_BASE_URL`.
- `TRADES_AUTH_PATH` cambia la ruta si el curso usa otra.
- `TRADES_TOKEN_MODE=farma` reutiliza el token de Farma Central, por si `/trades` acepta el mismo JWT. El default es `propio`.
- El JSON puede venir con distintos nombres. Se leen `offerId` / `id` / `_id`, `unitPrice` / `unit_price` / `precio`, `quantity` / `cantidad`, `orderId` / `order_id`, `status` / `estado`, y el grupo en `group`, `sellerGroup`, `buyerGroup`, `ownerGroup`, `fromGroup`, `grupo`. Si el cuerpo trae un objeto `offer` u `oferta`, se aplana.
- Estados remotos: `open|abierta|active|opened` → `abierta`; `closed|cerrada|accepted|filled|completed|matched` → `cerrada`; `expired|expirada`; `cancelled|canceled|cancelada`.
- El listado pide `status=open|closed|expired|cancelled` y además filtra en local, por si el servidor ignora el query.

## Prueba

`tests/test_trades_client.py`. No hay red: `httpx.post` y `httpx.request` están parcheados.
