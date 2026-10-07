# D. Modelo de custodia y trazabilidad

Entregable central del diseño (§12.1 D y §8.6). Farma no conserva el historial interno del grupo: si no se escribe aquí, no se reconstruye.

El módulo **único** que escribe las tablas de custodia es `app/custodia.py`. `operaciones.py` es la fachada hacia Farma: nadie debería llamar `farma_client` desde un script de planta sin pasar por ahí.

---

## Qué se registra y cuándo

| Evento del enunciado | Cuándo | Tablas | `movimientos.tipo` |
|---|---|---|---|
| Recepción de un insumo comprado | Worker ve unidades nuevas en un espacio (salvo cuarentena) cuyo `batch` aún no está en `unidades` | `solicitudes` pasa a `recibida`; `lotes` origen=`farma_central`; `unidades` `en_stock` | `recepcion` |
| Generación de un producto fabricado | Igual, pero la solicitud es `tipo=fabricacion` | `lotes` origen=`produccion`; `_materializar_relaciones` | `generacion` |
| Traslado entre espacios | Después de un `PATCH /products/{id}` exitoso (`operaciones.mover` o worker de frío) | `unidades.espacio_actual` | `traslado` |
| Consumo en acondicionamiento | Justo después de que Farma acepta `POST /products` de una fabricación | `consumos` (unidad, lote padre, solicitud); unidad `consumida`, sin espacio | `consumo` |
| Venta (intención) | **Antes** de llamar a Integrapay, al reservar FEFO | `ventas`, `venta_items`, `venta_unidades` estado `pendiente`; unidad `reservada` | `venta` |
| Despacho | Tras pago `pagada`, `confirmar_despacho` | `venta_unidades.despachada`; unidad `despachada` | `despacho` |
| Vencimiento | Helper `registrar_vencidas` (aún no en el loop del worker) | unidad `vencida` | `vencimiento` |
| Cuarentena | Enum listo; E2 | — | `cuarentena` |

Reglas de consistencia local (una transacción SQLAlchemy `SessionLocal.begin`):

- `registrar_fabricacion` revierte todo si falta un `_id` en custodia. No hay consumo huérfano.
- `asignar_unidades_a_venta` exige `estado == en_stock`. Si falla a mitad, la transacción no confirma.
- Llegadas son **idempotentes**: `_id` ya conocido se ignora.
- Un lote se ata a **a lo más una** solicitud (`lotes.solicitud_id` unique).

---

## Modelo de datos

Esquema en `app/models.py`. Índices y CHECK con `naming_convention` de Alembic (migración `e1a7c0d1e2f3`: `lot_relations`, `reservada`, `venta_items`).

| Tabla | Rol |
|---|---|
| `solicitudes` | Compra o fabricación pedida a Farma. `challenge_id`, `llega_en`, `pendiente\|recibida\|fallida` |
| `lotes` | Nacimiento conjunto. `codigo` único (el `batch` de Farma). `origen` = farma_central \| produccion \| distribuidora. `origen_grupo` para trueque E3 |
| `unidades` | PK = `_id` de Farma. Estado actual y espacio |
| `consumos` | Unidad exacta gastada en una solicitud de fabricación. Una unidad se consume una vez |
| `lot_relations` | Arista N:M padre→hijo, `cantidad`, `solicitud_id`. Unique `(parent, child)` |
| `movimientos` | Bitácora por unidad (no se borra) |
| `ventas` | Pedido. `canal` default `portal`. `transaccion_id` Integrapay unique |
| `venta_items` | Líneas con `precio_unitario` vigente al confirmar el carro |
| `venta_unidades` | Qué `_id` se llevó cada venta; `pendiente` hasta el despacho |

**N:M consumido↔generado.** Un lote de `BLI-AMOXI-500` tiene tres padres de insumo. Un lote de `KIT-RESP-ADULTO` tiene tres padres acondicionados. El mismo lote de `API-AMOXI-500` puede ser padre de varios blísteres. El visor recorre `lot_relations`, no asume 1:1.

Espacios (`ESPACIOS`): `checkIn`, `bodega`, `cold`, `buffer`, `packaging`, `checkOut`, `quarantine`. El worker **no** sincroniza cuarentena: un retiro no debe reaparecer como llegada.

---

## Las cuatro preguntas (§8.6)

Implementación: `app/trazabilidad.py`. API: `GET /api/trazabilidad/{codigo}`. UI: `/trazabilidad?lote=`.

### 1. Unidades del lote X en inventario y dónde

- **Procedimiento:** `unidades_en_inventario(codigo)`.
- **Consulta:** `unidades` del lote con `estado IN (en_stock, reservada)`, ordenadas por espacio.
- **Mecanismo:** lookup por `lotes.codigo` (único). No recorre Farma. El visor también agrega conteos por espacio y por estado (`consultar`).

### 2. En qué productos se consumió X y qué lotes se generaron

- **Procedimiento:** `aguas_abajo(codigo)`.
- **Consulta:** CTE recursivo en `lot_relations` donde el lote es **padre**, profundidad &lt; 20.
- **Mecanismo:** cada fila trae `codigo`, `sku`, `origen`, `cantidad_relacion` (unidades de ese padre que alimentaron al hijo). La UI muestra profundidad 1 aparte de la recursiva.

### 3. A qué clientes se entregó X, cuándo, en qué pedido

- **Procedimiento:** `clientes_del_lote(codigo)` → `_clientes`.
- **Consulta:** `ventas ⋈ venta_unidades ⋈ lotes` filtrado a `ventas.estado = 'pagada'`.
- **Mecanismo:** “se entregaron” no incluye reservas ni errores. Devuelve nombre, email, `pagada_en`, `transaccion_id`, lista de `_id`. `consultar` también arma `entregas` para el nodo verde del grafo.

### 4. De qué lotes de insumo se produjo X y de dónde venían

- **Procedimiento:** `aguas_arriba(codigo)`.
- **Consulta:** CTE al revés: el lote es **hijo**, se sube a padres hasta que el origen es `farma_central` o `distribuidora` (hojas del grafo).
- **Mecanismo:** cada nodo lleva `origen` y `origen_grupo`. El visor etiqueta FARMA CENTRAL / DISTRIBUIDORA n / PROPIO.

`consultar` junta las cuatro, más KPIs (sku, cantidad inicial, vencimiento efectivo = min `vence_en` de unidades vivas, conservación por catálogo Farma, `consulta_ms`). Medido en PROD en ~16–26 ms sobre un lote de kit.

No se barre `movimientos` entero. Eso es el requisito de rendimiento del visor.

---

## Qué pasa si se cae a medias

Escenario del PDF: producto físicamente entregado y venta/custodia a medias.

| Falla | Mitigación |
|---|---|
| Integrapay `init` falla (HTTP 5xx, URL mal armada) | `iniciar_checkout` hace `marcar_pago(error)` + `liberar_reserva`. La venta 1 de PROD quedó colgada **antes** de este rollback; se canceló a mano con confirmar. El rollback está en el código que corre ahora. |
| El cliente no vuelve de la pasarela | Unidades siguen `reservada`. No se despachan. Hay que expirar reservas (no hay TTL aún; hueco). Cancelar en Integrapay pega la `backUrl` y libera. |
| Pago ok, proceso muere antes de `confirmar_despacho` | `finalizar` es **idempotente**: si ya está `pagada`, no vuelve a despachar. El worker llama `recuperar_pendientes` cada tick. |
| `DISPATCH_FARMA=1` y el `PATCH` a checkOut falla | La fila `venta_unidades` sigue `pendiente`; el worker reintenta. No se marca `despachada` en custodia hasta que Farma acepta **y** `confirmar_despacho` corre. En E1 el flag está en **0**: Farma no se entera del despacho, pero el rastro comprador↔unidad sí existe. |
| Farma acepta fabricación y Postgres no guarda consumos | Log `CRITICAL` con sku, challenge, `_id`. No hay XA. Planta corrige a mano; no se sigue fabricando a ciegas (candado). |
| Dos fabricaciones eligen las mismas unidades | `pg_try_advisory_lock(4000001)`. La segunda espera o falla explícito. |
| Lote llega sin solicitud pendiente | `registrar_llegadas` no crea lote huérfano; log de error. |

El visor, si el lote no está, responde 404. No inventa genealogía.
