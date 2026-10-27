# Prompt 2 — Arquitectura, decisiones técnicas y plan recomendado para la Entrega 1

> Este archivo **NO es el enunciado oficial** ni el informe de Canvas.  
> Es el **segundo prompt / paquete de instrucciones** para el agente: propuesta técnica inicial (Next.js, tablas en inglés). El sistema que corre es FastAPI + worker + Postgres + SPA Vite.
>
> Fuente de requisitos: `docs/01_enunciado_proyecto_llm.md`.
>
> Regla: si esta propuesta contradice un requisito oficial, **el archivo 01 gana**.

---

# 1. Objetivo de arquitectura

Construir una base que permita:

- aprovechar el código que ya existe;
- completar Entrega 1;
- evitar rehacer todo en Entrega 2;
- mantener trazabilidad correcta;
- aislar integraciones externas;
- soportar procesos asíncronos;
- operar en un servidor muy limitado;
- mejorar la experiencia de usuario;
- mantener una separación clara entre frontend y backend.

No se busca una arquitectura "perfecta".

Se busca una arquitectura:

- simple;
- defendible;
- mantenible;
- extensible;
- segura frente a fallas;
- razonable para 2 cores y 2 GB RAM.

---

# 2. Decisión principal: preservar antes de reescribir

El repositorio ya contiene trabajo de otro integrante.

Por tanto:

**NO asumir que hay que migrar o reescribir todo.**

Antes de cambiar arquitectura:

1. analizar código existente;
2. identificar qué funciona;
3. mapear dependencias;
4. entender la BD actual;
5. entender contratos del backend;
6. revisar frontend existente;
7. comparar contra requisitos;
8. decidir qué conservar.

Una migración tecnológica solamente se justifica si:

- resuelve un problema concreto;
- no destruye trabajo útil;
- entra en el plazo;
- reduce riesgo;
- mejora mantenibilidad.

---

# 3. Preferencia tecnológica

## Frontend

Preferencia:

- Next.js;
- React;
- TypeScript.

Motivos:

- stack conocido;
- buena organización por rutas;
- composición de componentes;
- excelente DX;
- tipado;
- facilidad para construir portal + trazabilidad;
- buen ecosistema para UX.

### Iconos

Usar primero la librería ya presente en el proyecto.

Si el proyecto ya utiliza `react-icons`, conservarla.

No añadir una segunda librería de iconos sin necesidad.

Mantener estilo visual consistente.

---

# 4. Backend: no migrar Python automáticamente

Situación conocida:

- actualmente existe backend en Python.

Preferencia del proyecto:

- trabajar con TypeScript donde tenga sentido;
- Node.js es una opción futura;
- pero la prioridad es aprovechar el trabajo existente.

### Regla

Si el backend Python:

- ya integra Farma Central;
- contiene modelos útiles;
- implementa lógica funcional;
- está organizado razonablemente;

entonces:

**mantenerlo para Entrega 1** y mejorar estructura.

No migrarlo únicamente por preferencia tecnológica.

### Migrar a TypeScript sólo si

el análisis demuestra que:

- el backend actual es mínimo o desechable;
- la migración es de bajo riesgo;
- no hay integraciones complejas ya realizadas;
- existe beneficio concreto;
- el tiempo lo permite.

---

# 5. Evitar dos extremos

No recomiendo:

## Un único monolito mezclado

Ejemplo no deseado:

```text
frontend
backend
jobs
integraciones
PoW
DB
```

todo dentro de un único proceso difícil de separar.

Tampoco recomiendo:

## Microservicios completos

Ejemplo no deseado:

```text
inventory-service
payment-service
traceability-service
production-service
order-service
...
```

cada uno con su propio runtime.

Con 2 cores y 2 GB RAM sería complejidad innecesaria.

---

# 6. Arquitectura preferida: frontend + backend modular + worker

Separar responsabilidades, pero mantener pocas unidades de ejecución.

```text
                  Internet
                     |
                     v
                  Nginx
                     |
        +------------+-------------+
        |                          |
        v                          v
   Next.js web                Backend API
                              Python actual
                              o Node si se
                              justifica
                                   |
                       +-----------+-----------+
                       |           |           |
                       v           v           v
                    Postgres   Integrations   Worker
                               Farma/Pay      PoW/jobs
```

Esto conserva separación frontend/backend sin crear muchos microservicios.

---

# 7. Nginx

Nginx debe ser el punto público.

Ejemplo conceptual:

```text
https://distribuidorX.ing.uc.cl/
                |
                v
              Nginx
                |
     +----------+----------+
     |                     |
     v                     v
  Next.js                /api
                     Backend local
```

Todos los procesos internos deberían escuchar solamente en localhost.

Ejemplo:

```text
Next.js      127.0.0.1:3000
Backend      127.0.0.1:8000
PostgreSQL   127.0.0.1:5432
```

Nginx expone solamente:

- 80;
- 443.

---

# 8. El servidor oficial

La entrega debe terminar publicada en:

`https://distribuidorX.ing.uc.cl`

No asumir Vercel como destino de evaluación.

Vercel podría servir para desarrollo si el equipo quisiera, pero **no reemplaza la URL oficial**.

Para esta fase actual:

**NO desplegar todavía.**

Primero:

- entender repo;
- organizar código;
- preparar configuración;
- preparar scripts;
- dejar deployment documentado.

---

# 9. Configuración por entorno

Separar:

```text
local
dev universidad
prod universidad
```

Usar variables de entorno.

Ejemplo:

```env
APP_ENV=local

FARMA_BASE_URL=
FARMA_TOKEN=

CHECKOUT_BASE_URL=
CHECKOUT_TOKEN=

DATABASE_URL=

INTEGRATION_MODE=mock
```

### Regla de seguridad

El modo por defecto durante esta fase debe ser:

```text
INTEGRATION_MODE=mock
```

o equivalente.

La aplicación no debe contactar accidentalmente sistemas reales.

---

# 10. Capa de integraciones

No repartir `fetch()` o `requests.get()` por todo el código.

Crear adaptadores.

Ejemplo conceptual:

```text
integrations/
  farma-central/
    client
    types
    mappers

  checkout/
    client
    types
    mappers
```

Beneficios:

- contratos centralizados;
- mocking;
- cambio DEV/PROD;
- reintentos;
- logging;
- testing futuro;
- menos acoplamiento.

---

# 11. Fuente de verdad

Separar dos conceptos.

## Farma Central

Fuente de verdad operacional externa sobre:

- productos;
- movimientos;
- espacios;
- disponibilidades que exponga;
- producción;
- precios según contrato.

## PostgreSQL del grupo

Fuente de verdad propia sobre:

- custodia;
- genealogía;
- pedidos;
- pagos;
- relaciones internas;
- auditoría;
- correlaciones;
- decisiones pendientes.

No intentar duplicar ciegamente todo Farma Central.

Guardar lo necesario para operar y reconstruir la custodia.

---

# 12. Modelo de datos recomendado

El modelo exacto se debe adaptar al código actual.

No borrar tablas útiles sin necesidad.

## 12.1 `lots`

Representa lotes conocidos.

Campos sugeridos:

```text
id
sku
origin_type
origin_reference
effective_expires_at
conservation_type
created_at
updated_at
```

`origin_type` podría distinguir:

```text
FARMA_CENTRAL
OTHER_DISTRIBUTOR
OWN_PRODUCTION
```

---

## 12.2 `units`

Representa unidades concretas.

```text
id
lot_id
sku
location
status
effective_expires_at
created_at
updated_at
```

Estados posibles:

```text
AVAILABLE
RESERVED
IN_PRODUCTION
CONSUMED
SOLD
DISPATCHED
EXPIRED
QUARANTINED
```

Adaptar a la semántica real de Farma Central.

---

## 12.3 `lot_relations`

Tabla central para genealogía.

```text
id
parent_lot_id
child_lot_id
quantity_consumed
production_reference
created_at
```

La relación debe soportar N:M.

No usar un único `parent_id` en `lots`.

---

## 12.4 `custody_events`

Historial auditable.

```text
id
event_type
unit_id nullable
lot_id
from_location nullable
to_location nullable
order_id nullable
external_reference nullable
metadata
occurred_at
recorded_at
```

Ejemplos:

```text
RECEIVED
MOVED
CONSUMED
PRODUCED
RESERVED
SOLD
DISPATCHED
EXPIRED
QUARANTINED
```

---

## 12.5 `orders`

```text
id
status
customer_name
customer_identifier
total_amount
currency
payment_id
created_at
updated_at
```

Estados sugeridos:

```text
DRAFT
PENDING_PAYMENT
PAID
PAYMENT_FAILED
CANCELLED
FULFILLING
DISPATCHED
```

---

## 12.6 `order_items`

```text
id
order_id
sku
quantity
unit_price
```

El `unit_price` debe guardar el precio utilizado en esa compra.

No significa que el catálogo deje de consultar el precio actual.

---

## 12.7 `order_units`

Relaciona pedido con unidades físicas.

```text
order_id
unit_id
```

Es importante porque la trazabilidad exige saber **qué unidades concretas** se entregaron.

---

## 12.8 `payments`

```text
id
order_id
external_transaction_id
status
amount
redirect_url
raw_metadata
created_at
updated_at
```

Estados:

```text
CREATED
PENDING
SUCCEEDED
FAILED
CANCELLED
```

---

## 12.9 `outbox_events`

Recomendado si el diseño actual lo permite.

```text
id
event_type
payload
status
created_at
processed_at
```

Permite registrar trabajo pendiente dentro de la misma transacción que modifica la BD.

---

# 13. Consistencia y transacciones

Ejemplo de problema:

```text
pago exitoso
-> marcar pedido como PAID
-> reservar unidades
-> registrar custodia
-> preparar despacho
```

Si el servidor cae entre pasos, no se puede dejar el pedido inconsistente.

Usar transacciones de BD para cambios que deban ser atómicos.

Ejemplo conceptual:

```text
BEGIN

update order
reserve units
create custody event
create outbox event

COMMIT
```

Después un worker procesa el efecto externo.

---

# 14. Idempotencia

Las confirmaciones externas pueden repetirse.

Por ejemplo:

- callback duplicado;
- reintento de pago;
- proceso reiniciado.

Diseñar operaciones importantes para ser idempotentes.

Ejemplo:

```text
payment external_transaction_id UNIQUE
```

y:

```text
si ya se procesó:
  no duplicar venta
```

Esto evita:

- doble despacho;
- doble registro;
- doble consumo.

---

# 15. Reservas de stock

El portal no debería vender la misma unidad a dos personas.

Flujo recomendado:

```text
pedido
-> validar stock
-> reservar unidades
-> crear pago
-> confirmar
-> convertir reserva en venta
```

Si el pago falla o se cancela:

```text
liberar reserva
```

La implementación exacta depende de los contratos de Farma Central.

---

# 16. Estrategia FEFO

Para productos con vencimiento:

**FEFO — First Expire, First Out**

Priorizar unidades que vencen antes.

No usar únicamente FIFO.

Esto reduce merma.

---

# 17. Reposición

Propuesta inicial que debe ajustarse a catálogo real.

Para cada insumo:

```text
usable_stock =
  available
  - reserved
  - expired
  - unusable
```

Definir:

```text
reorder_point
target_stock
```

Ejemplo inicial:

```text
reorder_point = consumo de 2 lotes
target_stock  = consumo de 4 lotes
```

Si:

```text
usable_stock <= reorder_point
```

pedir:

```text
target_stock - usable_stock
```

redondeado hacia arriba al tamaño de lote válido.

Los números deben recalibrarse según:

- productos reales;
- tamaños de lote;
- tiempos;
- costos;
- demanda.

---

# 18. Sensibilidad al precio

La estrategia debe reaccionar.

Propuesta inicial:

## Si precio cae aproximadamente 50%

- evitar fabricar grandes inventarios si existe riesgo de vencimiento;
- reducir producción especulativa;
- priorizar producción contra demanda;
- revisar si conviene reducir target de stock de producto terminado.

## Si precio sube aproximadamente 50%

- evaluar producir un lote adicional;
- solamente si:
  - existe capacidad;
  - hay insumos;
  - la vida útil lo permite;
  - la bodega externa no elimina el margen.

Esto debe convertirse en reglas concretas en el informe.

---

# 19. Bodega externa

La bodega externa:

- es ilimitada;
- mantiene frío;
- cuesta por hora.

Estrategia:

1. priorizar almacenamiento propio;
2. utilizar externa como overflow;
3. retirar de externa cuando haya capacidad;
4. considerar costo antes de abastecer grandes cantidades.

Para productos fríos:

- bodega externa puede ser preferible a perder vida útil;
- pero su costo debe controlarse.

---

# 20. Cadena de frío

Diseñar reacción rápida.

Ejemplo:

```text
producto cold_required
AND location not refrigerated
```

debe convertirse en condición de atención prioritaria.

No asumir que Farma Central avisará la degradación.

La lógica debería poder identificar exposición.

---

# 21. Proof of Work

El PoW nunca debería bloquear el proceso web principal.

Separarlo mediante:

- worker;
- proceso independiente;
- cola simple en BD;
- `child_process`;
- `worker_threads`;
- equivalente Python.

No crear muchos workers.

Con 2 cores:

- mantener baja concurrencia;
- reservar recursos para portal/backend/DB.

---

# 22. Procesos asíncronos

Buenos candidatos:

- resolver PoW;
- esperar producción;
- reconciliar estados;
- liberar reservas expiradas;
- procesar outbox;
- mover automáticamente productos críticos;
- futura reposición automática.

No ejecutar loops pesados dentro de una request HTTP.

---

# 23. Visor de trazabilidad

Debe responder dos direcciones.

## Ancestros / upstream

```text
lote consultado
<- lotes usados para producirlo
<- lotes usados para producir esos lotes
...
```

## Descendientes / downstream

```text
lote consultado
-> lotes derivados
-> kits
-> unidades
-> pedidos
-> clientes
```

---

# 24. Consultas recursivas

PostgreSQL permite usar:

```sql
WITH RECURSIVE
```

para genealogía.

El agente debe evaluar si:

- es suficiente;
- conviene una vista;
- conviene materializar ciertas relaciones;
- el volumen esperado requiere optimización adicional.

No cargar todo el historial en memoria.

---

# 25. Índices recomendados

Revisar y adaptar.

```text
lots.id
lots.sku
units.lot_id
units.location
units.status

lot_relations.parent_lot_id
lot_relations.child_lot_id

custody_events.lot_id
custody_events.unit_id
custody_events.order_id
custody_events.occurred_at

orders.status
payments.external_transaction_id
```

---

# 26. UX — Portal de venta

Objetivo:

una experiencia clara y rápida, no una demo técnica fea ni un e-commerce sobrecargado.

## Home/catalog

Mostrar:

- nombre del distribuidor;
- catálogo de kits;
- precio actual;
- stock visible;
- estado de disponibilidad;
- CTA claro.

### Tarjeta de producto

Debe priorizar:

1. nombre;
2. qué incluye;
3. precio;
4. stock;
5. acción.

No saturar con datos técnicos internos.

---

# 27. UX — Carro

El carrito debe permitir:

- editar cantidad;
- eliminar;
- ver subtotal;
- ver total;
- detectar cambios de stock;
- detectar cambios de precio antes del pago.

Antes de crear transacción:

```text
revalidar precio
revalidar stock
```

Si cambió:

- informar;
- actualizar total;
- pedir confirmación.

---

# 28. UX — Estados de pago

Tener pantallas claras.

## Éxito

Mostrar:

- pedido;
- estado;
- resumen;
- total.

## Cancelado

Mostrar:

- mensaje claro;
- volver al carrito;
- permitir reintentar.

## Error

Recordar que hay error aleatorio simulado.

No mostrar stack traces.

Mostrar:

- fallo;
- pedido no confirmado;
- CTA de reintento.

---

# 29. UX — Trazabilidad

Este visor es una herramienta técnica.

Debe ser fácil de comprender.

## Layout recomendado

### Encabezado

- buscador;
- ID del lote;
- SKU;
- estado.

### Resumen

- origen;
- unidades;
- vencimiento;
- conservación;
- ubicación.

### Grafo o árbol

Centro:

```text
LOTE CONSULTADO
```

Izquierda:

```text
UPSTREAM
lotes que lo generaron
```

Derecha:

```text
DOWNSTREAM
lotes derivados
entregas
clientes
```

### Interacción

Idealmente:

- expandir nodos;
- colapsar ramas;
- abrir otro lote;
- copiar ID;
- mantener breadcrumbs.

No priorizar animaciones.

Priorizar legibilidad.

---

# 30. Accesibilidad y estados UI

Todo portal debe contemplar:

- loading;
- empty state;
- error state;
- disabled state;
- éxito.

Evitar:

- botones ambiguos;
- acciones sin feedback;
- colores como único indicador;
- texto demasiado pequeño;
- skeletons infinitos.

---

# 31. Diseño visual

Preferencia:

- limpio;
- profesional;
- clínico/logístico;
- no "dashboard genérico de IA";
- jerarquía visual fuerte;
- pocas decoraciones.

Usar sistema consistente de:

- spacing;
- tipografía;
- bordes;
- cards;
- estados;
- iconos.

No invertir más tiempo en estética que en correctitud.

---

# 32. Estructura sugerida de frontend

Adaptar al repo real.

```text
web/
  app/
    page.tsx
    cart/
    checkout/
    payment/
      success/
      cancelled/
      error/
    trazabilidad/
  components/
    catalog/
    cart/
    traceability/
    ui/
  lib/
    api/
    types/
    formatting/
```

No crear esta estructura ciegamente si el proyecto ya tiene otra razonable.

---

# 33. Estructura sugerida de backend

Si se mantiene Python:

```text
backend/
  app/
    modules/
      inventory/
      production/
      custody/
      orders/
      payments/
      traceability/
    integrations/
      farma_central/
      checkout/
    workers/
    db/
    config/
```

Si eventualmente se migra a TS:

```text
backend/
  src/
    modules/
    integrations/
    workers/
    db/
    config/
```

El concepto importa más que los nombres exactos.

---

# 34. No conectar todavía a sistemas reales

Durante la fase de refactor/estructura:

PROHIBIDO sin autorización explícita:

- llamar Farma Central DEV;
- llamar Farma Central PROD;
- llamar Checkout real;
- crear pagos reales/simulados en infraestructura del curso;
- pedir challenges;
- ejecutar PoW contra challenge real;
- solicitar producción;
- mover productos;
- comprar insumos;
- desplegar en servidor UC;
- reiniciar procesos del servidor UC;
- modificar Nginx remoto;
- modificar PostgreSQL remoto;
- tocar credenciales remotas.

---

# 35. Validación permitida en esta fase

Por defecto:

- no ejecutar suites de integración;
- no ejecutar e2e;
- no hacer smoke tests remotos.

Se puede usar, si es completamente local:

- lint;
- format;
- typecheck;
- build;
- análisis estático.

Tests unitarios solamente si:

- usan mocks;
- no tienen efectos externos;
- el usuario los autoriza o el agente confirma que son 100% aislados.

---

# 36. Mocking

Crear interfaces que permitan:

```text
RealFarmaCentralClient
MockFarmaCentralClient
```

y:

```text
RealCheckoutClient
MockCheckoutClient
```

Durante esta fase:

```text
Mock*
```

debe ser el comportamiento seguro por defecto.

---

# 37. Observabilidad

Sin sobrearquitectura.

Como mínimo:

- logs estructurados;
- correlation/request id;
- external reference ids;
- errores con contexto;
- no loggear secretos.

Esto será especialmente útil cuando la operación de E2/E3 dure horas.

---

# 38. Preparación para E2

La arquitectura debe poder añadir:

```text
purchase-orders
natural-language-orders
recalls
quarantine
notifications
```

sin reescribir:

- pedidos;
- inventario;
- custodia.

Idealmente todos los canales terminan produciendo una representación común:

```text
Order
```

---

# 39. Preparación para E3

Debe ser posible añadir:

- facturación;
- otras distribuidoras;
- estrategia frente a escasez;
- más automatización;
- operación continua.

No diseñarlo todo ahora.

Solamente evitar decisiones que lo hagan imposible.

---

# 40. Orden de implementación recomendado

## Fase A — Auditoría

- mapa actual;
- dependencias;
- frontend;
- backend;
- DB;
- integraciones;
- gaps.

## Fase B — Modelo de dominio

Asegurar:

- lots;
- units;
- relations;
- custody;
- orders;
- payments.

## Fase C — Adaptadores

Centralizar:

- Farma Central;
- Checkout.

## Fase D — Trazabilidad

Backend primero.

Después UI.

## Fase E — Portal

- catálogo;
- carrito;
- checkout;
- estados.

## Fase F — Worker/PoW

Aislar computación.

## Fase G — Preparar despliegue

- Nginx;
- procesos;
- env;
- scripts;
- documentación.

## Fase H — Integración real

**NO realizar todavía.**

Se hace solamente después de revisión manual y autorización del usuario.

---

# 41. Principio clave para el agente

No optimizar por "hacer más código".

Optimizar por:

```text
requisito oficial
+
reutilización del código existente
+
bajo riesgo
+
claridad
+
trazabilidad correcta
+
operación futura
```

Si el código actual ya resuelve un problema:

**mejorarlo, no reemplazarlo automáticamente.**
