# B. Tres decisiones de arquitectura y proyección E2/E3

El PDF pide tres decisiones con qué / por qué / qué se gana / qué se pierde. Las que siguen son las que **quedaron en el código**, no las de la propuesta `02` (Next.js, backend TypeScript, tablas `lots` / `custody_events`).

El enunciado avisa que las decisiones de E1 se arrastran el semestre. Cada decisión cierra con lo que deja listo o explícitamente aplazado para E2/E3.

---

## Decisión 1 — Un runtime Python y un portal estático (no Next.js)

**Qué se decidió.** Conservar FastAPI + SQLAlchemy + Alembic. El portal es una SPA Vite/React/TypeScript que el Dockerfile construye a `web/dist` y FastAPI sirve con `StaticFiles`. Un solo proceso HTTP (`web`) más un `worker`. No hay servidor Node en producción.

**Por qué.** El compañero ya tenía Farma, PoW, espacios y el esqueleto de custodia en Python. El servidor son 2 núcleos y 2 GB. Levantar Next.js junto a Uvicorn duplica runtime, RAM y puertos. Migrar el backend a TypeScript en la semana de E1 rompía integraciones que ya hablaban con Farma.

**Qué se gana.** Un deploy (`docker compose build web`), un puerto detrás de Nginx (`127.0.0.1:3000`), el PoW no pelea con el event loop del portal si se corre en el worker o en `compose run`. El catch-all `GET /{full_path:path}` entrega la SPA en `/`, `/trazabilidad`, `/pedidos`, `/pago/...`.

**Qué se pierde.** No hay SSR ni React Server Components. El carrito vive en `localStorage` (`web/src/cart.ts`), no en sesión de servidor. El build de frontend queda acoplado a la imagen Python. Quien esperaba el árbol de rutas de Next tiene que leer `web/src/App.tsx`.

**Trade-off.** Preferimos no reescribir lo que ya compraba insumos, a cambio de un frontend más “clásico”. Si en E3 hiciera falta un canal con UI pesada, se puede volver a separar el frontend; el API ya está detrás de `/api/...`.

**Arrastre.** E2 pide órdenes de compra y lenguaje natural: esos canales entran como nuevas rutas o un adapter que llama `custodia.crear_venta(..., canal="oc"|"nl")`, no como un rewrite de framework.

---

## Decisión 2 — Postgres del grupo como fuente de verdad de custodia

**Qué se decidió.** Farma ejecuta el mundo físico (unidades, espacios, fabricación). El historial interno, la genealogía y el stock que muestra el portal salen de Postgres (`unidades.estado`, `lotes`, `movimientos`, `lot_relations`, `ventas`). El visor **no consulta Farma**.

**Por qué.** El enunciado §8.6 es explícito: Farma no guarda el historial del grupo. Un visor que recorriera `GET /spaces/.../products` en cada búsqueda no escala (el PDF lo dice: no cargar todo el historial) y no respondería aguas arriba/abajo ni clientes.

**Qué se gana.** Consultas del visor en el orden de decenas de milisegundos (CTE sobre `lot_relations`, profundad máxima 20). Stock del catálogo = `custodia.stock_disponible` (en_stock, no vencido, no reservado). Independencia si Farma está lenta al mirar un lote.

**Qué se pierde.** Hay que **sincronizar**. El worker llama `registrar_llegadas` cada 20 s; si Farma entrega una unidad y el tick falla, hay una ventana en que el físico existe y custodia no. No usamos two-phase commit. El despacho a Farma (`DISPATCH_FARMA`) está apagado en E1 para no divergir: la unidad se marca `despachada` en Postgres y sigue en el espacio Farma.

**Trade-off.** Consistencia eventual de llegadas a cambio de un modelo consultable y de no mentir en el portal con el inventario crudo de Farma (que incluye vencidos y cosas en tránsito).

**Arrastre.** Recall E2: `origen`, `origen_grupo`, `cuarentena` ya están en el enum de espacios y en `estado` de unidad. Falta el job que, dado un código de lote Farma, recorra `aguas_abajo`, bloquee venta y mueva a `quarantine`. El grafo ya está.

---

## Decisión 3 — Portal síncrono, planta asíncrona (worker + candados)

**Qué se decidió.** El click de “Pagar” es un request HTTP que reserva FEFO, llama Integrapay y redirige. Comprar insumos, fabricar, PoW, cadena de frío y reintento de despachos corren en el **worker** (o en un proceso `producir` aparte), con `os.nice(10)` y `cpus: "1.0"`. Fabricación y venta usan advisory locks de Postgres (`LOCK_FABRICACION`, `LOCK_VENTA`) para no elegir las mismas unidades en paralelo.

**Por qué.** El Anexo de PoW y el propio PDF advierten que un solver greedy puede comerse la CPU del portal. La cámara de frío degrada producto si no se mueve en minutos (`TICK_SECONDS = 20`). Farma limita 250 req/min: el worker topea `MAX_MOVES_PER_TICK = 100`.

**Qué se gana.** El catálogo y el visor siguen respondiendo mientras se resuelve un challenge de 12–13 bits. La recepción no bloquea a `comprar`: se registra `solicitud` pendiente y el tick crea el lote cuando aparece el `batch`.

**Qué se pierde.** Hay latencia de un tick (~20 s) entre que Farma deja el producto y que custodia lo ve. El orquestador `producir(..., tanda=10)` es un bucle con `sleep(20)`, no una cola con DLQ. No hay outbox ni message broker (la propuesta 02 los mencionaba; en 2 GB no se justificó).

**Trade-off.** Operación continua barata versus menos “mensajería empresarial”. E2 puede enchufar una cola **como canal de pedidos** (`Venta.canal`) sin cambiar el worker de frío.

**Arrastre.** Operación 24–48 h (E2) y 48–72 h (E3): el worker ya reintenta `recuperar_pendientes` y no se mata por una excepción en el tick. Falta marcar vencidas en el mismo loop (`registrar_vencidas` existe, el worker aún no lo llama: hueco P2).

---

## Otras decisiones menores que el informe debe poder defender

**Genealogía duplicada a propósito.** `consumos` guarda la unidad exacta. `lot_relations` agrega lote↔lote N:M para el visor. Coste: dos escrituras al nacer un lote. Beneficio: el CTE no recorre `consumos` × `unidades` en cada búsqueda.

**SPA híbrida, no plantillas Jinja.** El HTML de fallback del catch-all existe por si `web/dist` no está; en PROD el visor es React.

**Confirmar pago sin sesión de usuario.** `POST /api/checkout/confirmar` acepta `venta_id` + resultado porque Integrapay redirige al browser. Es el camino de las `backUrls`. Quien conozca un `venta_id` pendiente podría confirmar; en E1 el riesgo se acepta (grupo cerrado, HTTPS). E2 debería firmar las backUrls o validar el `payment_id` contra Integrapay.

**Adapter de Integrapay, no de `/transactions`.** El host real es `.../payments/auth` e `init`. Un base URL con sufijo `/checkout` devolvió 500 y dejó una reserva (venta 1, luego cancelada). El adapter ahora revierte la reserva si `init` falla.

---

## Proyección a Entrega 2 y 3

El PDF recomienda diseñar E1 para no rehacer. Lo que ya está en el esquema y lo que falta:

| Tema E2/E3 | Qué hay hoy | Qué falta |
|---|---|---|
| Órdenes de compra / plazos | `Venta.canal`, `orden_externa_id` | Parser del canal, estados de plazo |
| Pedidos en lenguaje natural | Idem canal | Servicio no determinista; misma reserva FEFO |
| Colas / archivos | Campo `canal` | Adapter de ingestión; no hace falta un broker en el mismo host |
| Recall / retiro | `aguas_abajo`, `clientes_del_lote`, espacio `quarantine`, estado `cuarentena` | Job de bloqueo + notificación en ventana de tiempo |
| Facturación | `venta_items` con precio vigente al comprar | Adapter del sistema de facturas |
| Escasez / trueque entre grupos | `lotes.origen` ∈ {farma_central, distribuidora, produccion}, `origen_grupo` | Registrar lotes que llegan de otra dist. |
| Cuarentena | Enum listo, worker **no** mira ese espacio en llegadas (a propósito) | Usar el espacio cuando Farma emita el retiro |
| Visor a escala | CTE acotado a un código, no dump de `movimientos` | Índices extra si el grafo crece en E3 |
| Autonomía 24–72 h | Worker no muere por un tick fallido; candados | Job de vencimiento; alerta si `en_camino` se pudre |

La decisión de **no** despachar en Farma en E1 (`DISPATCH_FARMA=0`) se revierte cuando el grupo acepte el riesgo de un `PATCH` a `checkOut` a medias: `despachos_pendientes` + `recuperar_pendientes` existen para ese día.
