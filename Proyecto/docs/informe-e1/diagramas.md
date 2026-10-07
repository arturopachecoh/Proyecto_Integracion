# Diagramas Entrega 1 — Distribuidora 4

Vista grande de los diagramas del informe. En GitHub o en el preview de Cursor se leen mejor que en el PDF (ahí van como imágenes).

Instancias PROD (`logs.txt`, 6–7 oct 2026): compra **#1** 250 × `API-AMOXI-500`; fabricación **#32** 6 × `BLI-AMOXI-500`; fabricación **#56** 6 × `KIT-RESP-ADULTO`; venta **#6** lote `L-KIT-RESP-ADULTO-261006-60e8`.

Prosa y tablas: [01-diagramas.md](01-diagramas.md). PDF: [Informe_Entrega1_Distribuidora4.pdf](Informe_Entrega1_Distribuidora4.pdf).

---

## A1. Abastecimiento — pedir el insumo

Solicitud #1. Destino posterior: bodega (el API no es frío).

```mermaid
%%{init: {"theme": "neutral", "themeVariables": {"fontSize": "18px"}, "sequence": {"useMaxWidth": false, "actorMargin": 90, "messageMargin": 28, "width": 220}}}%%
sequenceDiagram
    autonumber
    actor Planta
    participant Backend
    participant Farma as Farma Central

    Planta->>Backend: producir 30 kits (tanda 10)
    Backend->>Backend: receta pide API-AMOXI-500
    Backend->>Farma: POST challenge 250 x API-AMOXI-500
    Farma-->>Backend: difficulty 12 bits
    Backend->>Backend: PoW sha256(prefix:nonce)
    Backend->>Farma: POST /products qty 250
    Farma-->>Backend: availableAt 22:20:04Z
    Backend->>Backend: solicitud 1 pendiente en Postgres
```

---

## A2. Abastecimiento — recepción y bodega

Worker cada 20 s. Almacenamiento: **checkIn → bodega**.

```mermaid
%%{init: {"theme": "neutral", "themeVariables": {"fontSize": "18px"}, "sequence": {"useMaxWidth": false, "actorMargin": 90, "messageMargin": 28, "width": 220}}}%%
sequenceDiagram
    autonumber
    participant Worker
    participant Farma as Farma Central
    participant DB as Postgres

    Worker->>Farma: GET checkIn/products
    Farma-->>Worker: unidades batch Farma
    Worker->>DB: lote origen farma_central
    Worker->>DB: unidades en_stock en checkIn
    Worker->>DB: movimiento recepcion
    Worker->>Farma: PATCH unidad a bodega
    Worker->>DB: movimiento traslado
    Note over DB: destino = bodega principal
```

---

## A3. Acondicionamiento — fabricar `BLI-AMOXI-500`

Lote de 6 (PROD #32). Consume 72 API + 48 EXC + 6 LAM = 126 unidades.

```mermaid
%%{init: {"theme": "neutral", "themeVariables": {"fontSize": "18px"}, "sequence": {"useMaxWidth": false, "actorMargin": 80, "messageMargin": 26, "width": 200}}}%%
sequenceDiagram
    autonumber
    participant Planta
    participant Backend
    participant Farma as Farma Central
    participant DB as Postgres

    Planta->>Backend: fabricar BLI-AMOXI-500 x 6
    Backend->>DB: FEFO 126 insumos
    Backend->>Farma: PATCH insumos a packaging
    Backend->>Farma: challenge + PoW 12 bits
    Backend->>Farma: POST /products x 6
    Farma-->>Backend: availableAt 22:25:33Z
    Backend->>DB: solicitud 32, consumos, unidades consumida
    Note over Planta,DB: el worker registra el lote hijo al llegar
```

---

## A4. Acondicionamiento — armar `KIT-RESP-ADULTO`

Lote de 6 (PROD #56). Consume 18 acondicionados (6+6+6). Kit ambiente → bodega.

```mermaid
%%{init: {"theme": "neutral", "themeVariables": {"fontSize": "18px"}, "sequence": {"useMaxWidth": false, "actorMargin": 80, "messageMargin": 26, "width": 200}}}%%
sequenceDiagram
    autonumber
    participant Planta
    participant Backend
    participant Farma as Farma Central
    participant DB as Postgres

    Planta->>Backend: fabricar KIT-RESP-ADULTO x 6
    Backend->>DB: FEFO 6 BLI-AMOXI + 6 BLI-IBUPRO + 6 FRA-SALBUTA
    Backend->>Farma: PATCH a packaging
    Backend->>Farma: challenge + PoW 13 bits
    Backend->>Farma: POST /products x 6
    Backend->>DB: solicitud 56, 18 consumos
    Backend->>DB: lot_relations N:M al nacer el kit
    Planta->>Farma: despejar kit packaging a bodega
    Note over DB: stock_disponible listo para el portal
```

---

## A5. Venta — reserva FEFO e Integrapay

Pedido #6. 1 × `KIT-RESP-ADULTO`, $534, lote `L-KIT-RESP-ADULTO-261006-60e8`.

```mermaid
%%{init: {"theme": "neutral", "themeVariables": {"fontSize": "18px"}, "sequence": {"useMaxWidth": false, "actorMargin": 80, "messageMargin": 26, "width": 200}}}%%
sequenceDiagram
    autonumber
    actor Cliente
    participant Portal
    participant Backend
    participant Integrapay

    Cliente->>Portal: catalogo + carro 1 kit
    Portal->>Backend: POST /api/checkout
    Backend->>Backend: FEFO reserva lote 261006-60e8
    Backend->>Backend: venta 6 pendiente_pago
    Backend->>Integrapay: POST /payments/auth
    Backend->>Integrapay: POST /payments/init 534
    Note over Integrapay: backUrl /pago/exito?venta=6
    Integrapay-->>Portal: redirect_url
    Cliente->>Integrapay: paga en la pasarela
```

---

## A6. Venta — resultado y despacho

`DISPATCH_FARMA=0`: custodia confirma el despacho **sin** mover en Farma. ~20 % de error en E1.

```mermaid
%%{init: {"theme": "neutral", "themeVariables": {"fontSize": "18px"}, "sequence": {"useMaxWidth": false, "actorMargin": 70, "messageMargin": 28, "width": 180}}}%%
sequenceDiagram
    autonumber
    actor Cliente
    participant Portal
    participant Backend
    participant Pasarela as Integrapay
    participant DB as Postgres

    alt pago ok
        Pasarela->>Portal: /pago/exito?venta=6
        Portal->>Backend: POST confirmar exito
        Backend->>DB: venta pagada
        Backend->>DB: unidad despachada
        Portal-->>Cliente: visor con el codigo de lote
    else error o cancelado
        Pasarela->>Portal: /pago/error o cancelado
        Portal->>Backend: POST confirmar
        Backend->>DB: libera reserva
    end
```

---

## B. Arquitectura de procesos

Servidor 2 GB. Un HTTP, un worker, Postgres. Node no corre en PROD.

```mermaid
%%{init: {"theme": "neutral", "themeVariables": {"fontSize": "18px"}, "flowchart": {"useMaxWidth": false, "htmlLabels": true, "nodeSpacing": 40, "rankSpacing": 50}}}%%
flowchart TB
    Cliente --> Nginx
    Nginx -->|"TLS a 127.0.0.1:3000"| Web
    subgraph vm [choripan4]
        Web["web: FastAPI + SPA 512 MiB"]
        Worker["worker: frio, llegadas, PoW 256 MiB / 1 CPU"]
        DB[(Postgres 16)]
        Web --> DB
        Worker --> DB
    end
    Web --> Integrapay
    Worker --> Farma
    Web -.->|"scripts producir"| Farma
```

---

## C. Integración Farma e Integrapay

```mermaid
%%{init: {"theme": "neutral", "themeVariables": {"fontSize": "18px"}, "flowchart": {"useMaxWidth": false, "nodeSpacing": 30, "rankSpacing": 40}}}%%
flowchart LR
    subgraph d4 [Grupo 4]
        API[FastAPI]
        W[Worker]
        PG[(Postgres)]
        API --> PG
        W --> PG
    end
    subgraph farma [Farma Central]
        Cat[catalogo y precios]
        Esp[espacios y movimientos]
        Fab[challenge y POST products]
    end
    subgraph pay [Integrapay]
        Auth[POST /payments/auth]
        Init[POST /payments/init]
        Host[checkout hosted]
    end
    API --> Cat
    API --> Auth
    Auth --> Init
    Init --> Host
    Host -->|"backUrls HTTPS"| API
    W --> Esp
    API -.-> Fab
```

El visor **no** llama a Farma: `GET /api/trazabilidad/{codigo}` lee solo Postgres. La UI pública es `/trazabilidad?lote=`.

---

## D. Modelo de datos (custodia)

Campos en `app/models.py`. Aquí solo las relaciones. Historial = `movimientos` + `consumos` + `lot_relations` (no hay tabla `custody_events`).

```mermaid
%%{init: {"theme": "neutral", "themeVariables": {"fontSize": "18px"}, "er": {"useMaxWidth": false}}}%%
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

N:M: un blíster tiene tres padres de insumo; un kit tiene tres padres acondicionados. Se materializa en `lot_relations` al nacer el hijo.