# Logística de operación y huecos (Entrega 1)

Esta sección no sustituye A–D; deja por escrito cómo está levantado el grupo 4 y qué queda fuera del software.

---

## Servidor y URL

El enunciado asigna `https://distribuidorX.ing.uc.cl`. El hostname `distribuidor4.ing.uc.cl` **no resuelve en DNS** (comprobado). El servicio público que corre es:

**https://choripan4.ing.uc.cl**

| Ruta | Qué es |
|---|---|
| `/` | Portal de venta (catálogo) |
| `/carrito`, `/checkout`, `/pago/{exito\|error\|cancelado}` | Compra e Integrapay `backUrls` |
| `/trazabilidad` | Visor (query `?lote=`) |
| `/pedidos` | Bitácora local de ventas |
| `/api/...` | JSON |
| `/health` | Postgres |

TLS termina en Nginx del host; proxea a `127.0.0.1:3000` (Uvicorn). Ejemplo de config: `deploy/nginx.example.conf`. `PUBLIC_BASE_URL=https://choripan4.ing.uc.cl` para que Integrapay redirija al HTTPS real.

SSH: usuario `integracion` en ese host. Firewall del curso: no tocar `ufw`. Disco de Postgres: volumen Docker `pgdata`. **Prohibido** `docker compose down -v`.

RAM: db 512m, web 512m, worker 256m / 1 CPU. Al redesplegar se para el worker, se buildea `web` y se vuelve a subir; no se recrea `db`.

---

## Código y Canvas

- **GitHub:** todo el código en el repositorio asignado al grupo. Rama de trabajo reciente: `deploy/entrega1` sobre lo que ya estaba en `origin/main`.
- **Canvas:** este informe (PDF generado desde `INFORME.md`). El Markdown en el repo no reemplaza la tarea de Canvas.
- Invitación al cuerpo docente al repo: proceso del curso (el staff invita al grupo). Si piden acceso extra, se gestiona aparte; no es un entregable de este directorio.

---

## Treinta kits

Cumplido en PROD el 6–7 de octubre de 2026. `logs.txt` arranca la campaña de 10 SKU × 30. Ejemplos de lote: fabricación #56 = 6 × `KIT-RESP-ADULTO`; más tarde el portal vendió `L-KIT-RESP-ADULTO-261006-60e8` (pedido #6) y `L-KIT-DERMATO-261007-0c20` (pedido #4).

`sembrar_demo` (`L-DEMO-*`) **no** se corre en PROD: ensuciaría genealogía con lotes ficticios.

---

## Pagos y Farma en el ambiente evaluado

| Variable | Valor en PROD al cerrar E1 | Efecto |
|---|---|---|
| `CHECKOUT_MODE` | `real` | Integrapay de verdad, ~20 % error simulado por ellos |
| `DISPATCH_FARMA` | `0` | Despacho solo en custodia |
| `FARMA_ENV` | `prod` | Espacios y catálogo de producción |
| `CHECKOUT_BASE_URL` | host `prod.proyecto.2026-2...` **sin** `/checkout` | `auth` + `init` |

En local el default es `CHECKOUT_MODE=mock` (`.env.example`).

---

## Huecos conscientes (no se venden como hechos)

1. Job de vencimiento en el worker (`registrar_vencidas` existe, no está en el tick).
2. TTL de reservas si el cliente abandona Integrapay.
3. `POST /api/checkout/confirmar` sin autenticar al comprador (confía en la `backUrl`).
4. Política ±50 % documentada, no cron.
5. DNS `distribuidor4.ing.uc.cl`.
6. Despacho físico Farma apagado.
7. `02_arquitectura_...md` describe un stack que **no** se implementó; el diseño válido es este directorio.

Nada de eso impide cumplir el checklist de E1 (portal, visor, 30 kits, HTTPS, custodia, informe). Sí condiciona E2 si hay recall o autonomía 48 h.
