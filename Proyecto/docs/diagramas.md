# Diagramas de secuencia — Entrega 1

Instancias de PROD (6–7 oct 2026): compra **#1** 250 × `API-AMOXI-500`; fabricación **#32** 6 × `BLI-AMOXI-500`; fabricación **#56** 6 × `KIT-RESP-ADULTO`; venta **#6** lote `L-KIT-RESP-ADULTO-261006-60e8`.

Los tres flujos que pide el enunciado no son genéricos. El código que los ejecuta es `producir` / `comprar` / `fabricar`, el worker (`worker/main.py`) y `iniciar_checkout`.

PNG para Word: [`docs/img/`](img/).

---

## Abastecimiento — pedir `API-AMOXI-500`

`producir` arma una tanda, `planificar` calcula el faltante y `comprar` pide el desafío, resuelve el PoW y deja una solicitud pendiente. Farma responde `availableAt`; el lote todavía no existe en nuestra base.

```mermaid
sequenceDiagram
    autonumber
    actor Planta
    participant Backend
    participant Farma as Farma Central
    participant DB as Postgres

    Planta->>Backend: producir (objetivo de kits, tanda 10)
    Backend->>Backend: planificar receta, redondeo a batch
    Backend->>Farma: POST /fabrication/challenge 250 x API-AMOXI-500
    Farma-->>Backend: prefix, difficulty 12 bits
    Backend->>Backend: PoW sha256(prefix:nonce)
    Backend->>Farma: POST /products qty 250
    Farma-->>Backend: availableAt
    Backend->>DB: solicitud 1 pendiente
```

---

## Abastecimiento — recepción

El worker, cada 20 s, registra las unidades nuevas donde Farma las dejó. `API-AMOXI-500` no es frío: **no** se mueve a bodega. Queda usable en checkIn (o en buffer si Farma no cupo en recepción). Solo lo frío va a cámara, o a buffer si la cámara está llena.

```mermaid
sequenceDiagram
    autonumber
    participant Worker
    participant Farma as Farma Central
    participant DB as Postgres

    Worker->>Farma: GET spaces/.../products
    Farma-->>Worker: unidades con batch
    Worker->>DB: lote origen farma_central
    Worker->>DB: unidades en_stock en el espacio de llegada
    Worker->>DB: movimiento recepcion
    Note over Worker,DB: insumo de ambiente: no hay PATCH a bodega
```

---

## Acondicionamiento — fabricar `BLI-AMOXI-500`

Lote de 6 (PROD #32). Consume 72 API + 48 EXC + 6 LAM. `fabricar` elige FEFO, mueve a packaging, PoW y POST. El lote hijo lo registra el worker cuando aparece, no en este request.

```mermaid
sequenceDiagram
    autonumber
    actor Planta
    participant Backend
    participant Farma as Farma Central
    participant DB as Postgres

    Planta->>Backend: fabricar BLI-AMOXI-500 x 6
    Backend->>DB: FEFO 126 insumos
    Backend->>Farma: PATCH insumos a packaging
    Backend->>Farma: challenge + PoW 12 bits
    Backend->>Farma: POST /products x 6
    Farma-->>Backend: availableAt
    Backend->>DB: solicitud 32, consumos, unidades consumida
    Note over Backend,DB: el lote hijo lo registra el worker al llegar
```

---

## Acondicionamiento — armar `KIT-RESP-ADULTO`

Lote de 6 (PROD #56). Consume 18 acondicionados (6+6+6). `lot_relations` se escribe cuando el worker ve el kit nacido, no en el POST de fabricación. El kit de ambiente lo saca `producir` (`_despejar`) de packaging a bodega en una vuelta siguiente.

```mermaid
sequenceDiagram
    autonumber
    actor Planta
    participant Backend
    participant Farma as Farma Central
    participant Worker
    participant DB as Postgres

    Planta->>Backend: fabricar KIT-RESP-ADULTO x 6
    Backend->>DB: FEFO 6 BLI-AMOXI + 6 BLI-IBUPRO + 6 FRA-SALBUTA
    Backend->>Farma: PATCH a packaging
    Backend->>Farma: challenge + PoW 13 bits
    Backend->>Farma: POST /products x 6
    Backend->>DB: solicitud 56, 18 consumos
    Worker->>Farma: GET packaging/products
    Worker->>DB: lote hijo + lot_relations N:M
    Backend->>Farma: PATCH kit a bodega
```

---

## Venta — reserva FEFO e Integrapay

Pedido #6. 1 × `KIT-RESP-ADULTO`, lote `L-KIT-RESP-ADULTO-261006-60e8`. La reserva es **antes** de `POST /payments/init`. Si Integrapay no arranca, se libera.

```mermaid
sequenceDiagram
    autonumber
    actor Cliente
    participant Portal
    participant Backend
    participant Integrapay
    participant DB as Postgres

    Cliente->>Portal: catálogo + carro 1 kit
    Portal->>Backend: POST /api/checkout
    Backend->>DB: FEFO, unidades reservadas
    Backend->>DB: venta pendiente_pago
    Backend->>Integrapay: POST /payments/auth
    Backend->>Integrapay: POST /payments/init
    Integrapay-->>Portal: redirect_url
    Cliente->>Integrapay: paga en la pasarela
```

---

## Venta — resultado y despacho

`DISPATCH_FARMA=0`: se confirma el despacho en custodia **sin** mover la unidad a checkOut en Farma.

```mermaid
sequenceDiagram
    autonumber
    actor Cliente
    participant Portal
    participant Backend
    participant Pasarela as Integrapay
    participant DB as Postgres

    alt pago ok
        Pasarela->>Portal: /pago/exito?venta=6
        Portal->>Backend: POST /api/checkout/confirmar exito
        Backend->>DB: venta pagada
        Backend->>DB: unidad despachada
        Portal-->>Cliente: visor con el código de lote
    else error o cancelado
        Pasarela->>Portal: /pago/error o cancelado
        Portal->>Backend: POST /api/checkout/confirmar
        Backend->>DB: libera reserva
    end
```

---

## Modelo de datos (custodia)

Tablas en `app/models.py`. Relación consumido↔generado: `lot_relations` (N:M), al nacer el lote hijo.

```mermaid
erDiagram
    solicitudes ||--o| lotes : genera
    solicitudes ||--|{ consumos : consume
    lotes ||--|{ unidades : contiene
    lotes ||--o{ lot_relations : padre
    lotes ||--o{ lot_relations : hijo
    unidades ||--o| consumos : se_consume
    unidades ||--o{ movimientos : historial
    unidades ||--o| venta_unidades : se_vende
    ventas ||--|{ venta_items : lineas
    ventas ||--|{ venta_unidades : unidades
```
