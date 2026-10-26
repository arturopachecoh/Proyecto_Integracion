# 04 — Diseño Entrega 2: órdenes de compra por sFTP y Pub/Sub

Alcance: recibir, decidir y cumplir las órdenes de compra (OC) que llegan por
sFTP y Pub/Sub, y mantener stock de kits para cumplirlas a tiempo. El canal de
mensajería y el retiro de lote se diseñan aparte, pero este diseño deja listo
lo que ellos necesitan (registro de OC, despacho real y custodia por cliente).

Puntaje en juego: 35 de 100 (17,5 sFTP + 17,5 Pub/Sub), medido como
`OC cumplidas / OC recibidas` por canal durante el período de evaluación.

## 1. Contexto y restricciones

- ~8 OC por hora entre sFTP y Pub/Sub, de 1 o 2 kits cada una, con plazo de
  ~2 horas desde su creación.
- Hay 10 kits en el catálogo, todos con lote de fabricación 1. Dos requieren
  frío: `KIT-DIABETES` y `KIT-VACUNA-INFLU`.
- Una OC sólo pasa a `cumplida` si se despacha la cantidad completa con
  `POST /farma-central/dispatch` (`productId`, `orderId`) antes de su
  vencimiento. Hoy el código **no** llama a ese servicio: la venta del portal
  sólo mueve a `checkOut` y marca la unidad como despachada en custodia.
- Una OC que no se responde nunca queda cumplida. Rechazar una OC y aceptarla
  sin alcanzar a cumplirla valen lo mismo en la rúbrica: cero.
- Sistema de órdenes: token propio (`POST /ordenes-compra/autenticar`, máximo
  20 por IP cada 5 min), consulta de a una OC (`GET /ordenes-compra/ordenes/{id}`)
  y cambio de estado (`POST /ordenes-compra/ordenes/{id}/estado`, sólo desde
  `creada`). Rate limit de 250 req/min por grupo.
- El rate limit de Farma Central (250 req/min) es por grupo y lo comparten el
  worker de frío, el despachador y el reponedor.
- Servidor de 2 GB de RAM.

## 2. Decisiones tomadas

| Tema | Decisión | Motivo |
|---|---|---|
| Origen de los kits | Stock por adelantado: mínimo configurable por kit, repuesto automáticamente | Con plazo de 2 h no hay margen para fabricar desde cero en cada OC |
| Regla de aceptación | Regla B: aceptar si el stock actual, o lo que llega antes del vencimiento con margen, cubre la OC descontando lo ya comprometido | Rechaza sólo lo claramente imposible, sin comprometer stock que no existe |
| Portal vs OC | Prioridad a las OC: el portal sólo vende lo que está sobre el mínimo | Las OC valen 35 puntos; el portal en E2 sólo se evalúa por disponibilidad |
| Pub/Sub | Suscripción pull, por REST con `google-auth` + `httpx` | Si el servidor cae, los mensajes esperan en Google; ack explícito por mensaje; sin gRPC en un contenedor chico; `google-auth` se reutiliza para verificar OIDC en mensajería y retiros |
| sFTP | `paramiko`, revisión cada 60 s, sesión abierta y cerrada en cada revisión | El servidor no avisa; las sesiones abiertas bloquean la casilla |
| Procesos | Dos contenedores nuevos: `pedidos` (rápido) y `reponedor` (CPU) | El PoW de fabricación puede tomar minutos y no debe bloquear la atención de OC |

## 3. Arquitectura

```
sFTP (XML)  ──┐
              ├─► bandeja ordenes_compra ─► procesador ─► despachador
Pub/Sub ──────┘   (PK = id de la OC)        acepta/       mueve a checkOut
                                            rechaza       + dispatch
                         ▲                                     │
                         └──────── conciliador ◄───────────────┘
                                   (sincroniza con la fuente oficial)

reponedor: mantiene el mínimo de cada kit con produccion.una_vuelta()
```

Cada pieza tiene una sola responsabilidad:

| Pieza | Qué hace | Qué no hace |
|---|---|---|
| Lector sFTP | Lista la casilla, descarga archivos nuevos, guarda el id de la OC en la bandeja | No decide nada |
| Lector Pub/Sub | Hace pull, decodifica el mensaje, guarda el id en la bandeja y recién entonces hace ack | No decide nada |
| Procesador | Consulta la OC oficial, aplica la regla B, reserva y acepta, o rechaza | No despacha |
| Despachador | Asigna unidades a OC aceptadas, mueve a `checkOut`, llama a dispatch, confirma en custodia | No acepta ni rechaza |
| Conciliador | Cada ~5 min consulta las OC no cerradas y sincroniza estado y `despachado` | No crea OC |
| Reponedor | Calcula faltantes contra el mínimo y ejecuta una vuelta de producción | No toca OC |

### Módulos nuevos

- `app/ordenes_client.py`: cliente del sistema de órdenes, con el mismo patrón
  que `app/farma_client.py` (token cacheado hasta su expiración, reintento con
  token nuevo ante 401, espera según `Ratelimit-Reset` ante 429).
- `app/canales/sftp.py` y `app/canales/pubsub.py`: lectores.
- `app/pedidos.py`: procesador, despachador y conciliador (regla B incluida).
- `worker/pedidos.py` y `worker/reponedor.py`: ciclos de cada contenedor.
- `app/scripts/crear_suscripcion.py`: crea una sola vez la suscripción pull
  por ambiente con la llave de `GET /ordenes-compra/pubsub/key`.

### Cambios a módulos existentes

- `app/produccion.py`: el cuerpo del ciclo de `producir()` pasa a una función
  `una_vuelta(objetivos)`. `producir()` la llama en ciclo, así el script de
  terminal sigue igual; el reponedor la llama una vez por tick. Se conserva el
  candado `LOCK_PRODUCCION`, así nunca corren dos producciones a la vez.
- `app/farma_client.py`: nueva función `dispatch(product_id, order_id)`.
- `app/catalogo.py`: `listar_kits()` y `validar_carrito()` usan el stock
  vendible por el portal (sección 6).
- `docker-compose.yml`: servicios `pedidos` y `reponedor`.

## 4. Modelo de datos

Una migración de Alembic agrega dos tablas. El modelo de custodia de la
Entrega 1 no cambia de estructura: cada OC aceptada es una `Venta` con
`canal` (`sftp` / `pubsub`) y `orden_externa_id`, y sus unidades van a
`VentaUnidad`, como ya estaba previsto en `app/models.py`.

### `ordenes_compra`

| Columna | Tipo | Nota |
|---|---|---|
| `id` | texto, PK | id de la OC en el sistema de órdenes |
| `canal` | enum `sftp`, `pubsub` (luego `mensajeria`) | |
| `origen_ref` | texto | nombre del archivo o id del mensaje Pub/Sub |
| `sku`, `cantidad`, `vencimiento` | | copiados de la OC oficial |
| `cliente` | texto | `nombreCliente` o `cliente` de la OC |
| `estado` | enum (sección 5) | estado local |
| `estado_remoto` | texto | último estado visto en el sistema de órdenes |
| `despachado_remoto` | entero | último `despachado` visto |
| `venta_id` | FK `ventas.id`, nullable | se crea al aceptar |
| `decision` | JSON | stock, en camino y comprometido vistos, y el motivo |
| `recibida_en`, `decidida_en`, `actualizada_en` | fecha | |
| `intentos`, `ultimo_error` | | para reintentos y diagnóstico |

### `archivos_sftp`

| Columna | Tipo | Nota |
|---|---|---|
| `nombre` | texto, PK | nombre del archivo en la casilla |
| `oc_id` | texto | id leído del XML |
| `leido_en` | fecha | |

Los archivos no se borran de la casilla: el enunciado no indica que esté
permitido, y esta tabla basta para no descargarlos de nuevo.

## 5. Ciclo de vida local de una OC

```
nueva ──► aceptando ──► aceptada ──► despachando ──► cumplida
  │           │
  │           └──► (la API no respondió: se concilia con la fuente oficial)
  └──► rechazando ──► rechazada

aceptada / despachando ──► vencida   (se libera lo reservado sin despachar)
```

Regla general: **cada paso se anota en la base antes de llamar a la API
externa**, igual que la venta del portal (`asignar_unidades_a_venta` antes de
mover y despachar). Si el proceso cae entre la anotación y la respuesta, al
reiniciar se consulta la OC oficial y se continúa desde lo que diga ella:

| Estado local al reiniciar | Estado remoto | Acción |
|---|---|---|
| `aceptando` | `creada` | Reintentar la aceptación |
| `aceptando` | `aceptada` | Pasar a `aceptada` |
| `aceptando` | `vencida` | Pasar a `vencida` y liberar la reserva |
| `rechazando` | `creada` | Reintentar el rechazo |
| `rechazando` | `rechazada` | Pasar a `rechazada` |
| `despachando` | cualquiera | Revisar cada `VentaUnidad` pendiente y reintentar el dispatch |

## 6. Regla de aceptación (regla B)

Para una OC de `cantidad` unidades de `sku` con vencimiento `V`:

```
disponible = stock_vendible(sku)
           + en_camino(sku, llega_antes_de = V − MARGEN_DESPACHO)
           − comprometido(sku)

acepta si disponible ≥ cantidad
```

- `stock_vendible`: `custodia.stock_disponible(sku)`. No cuenta unidades
  reservadas.
- `en_camino`: solicitudes de compra o fabricación pendientes del kit cuyo
  `llega_en` es anterior a `V − MARGEN_DESPACHO`.
- `comprometido`: unidades de OC ya aceptadas que todavía no tienen unidad
  asignada. Sin este término, una misma unidad en camino se contaría para
  varias OC.
- `MARGEN_DESPACHO`: 20 minutos por defecto, configurable.

La decisión se toma bajo un candado de Postgres compartido con la venta del
portal (`LOCK_VENTA`), así dos decisiones no cuentan el mismo stock.

Si hay stock, se reservan las unidades en el momento (FEFO, igual que el
portal). Si se aceptó contando con producción en camino, la OC queda aceptada
sin unidades y el despachador le asigna las que nazcan, empezando por la OC
que vence primero.

Toda decisión guarda en `decision` los números vistos y el motivo, para
revisarla después.

### Stock vendible por el portal

```
vendible_portal(sku) = max(0, stock_vendible(sku) − minimo(sku) − comprometido(sku))
```

`validar_carrito()` vuelve a revisarlo al reservar, así una página abierta
desde antes no puede vender stock reservado para las OC.

## 7. Reposición automática

Cada tick del `reponedor`:

```
para cada kit:
    faltan = minimo(kit) + comprometido(kit) − (stock_vendible(kit) + en_camino(kit))
si algún kit tiene faltan > 0:
    produccion.una_vuelta({kit: faltan, ...})
```

- El mínimo por kit es configurable sin tocar código. Se parte con 3 por kit
  y se ajusta midiendo la demanda real en dev, donde ya llegan OC con el
  volumen y los plazos de producción desde el 15 de octubre.
- Los kits de frío ocupan cupo en la cámara; si falta espacio se les da un
  mínimo menor.

## 8. Lectores

### sFTP

- Cada 60 s: conectar, listar, descargar sólo los archivos que no están en
  `archivos_sftp`, leer `<id>` del XML, insertar en `ordenes_compra` y
  `archivos_sftp` en la misma transacción, desconectar.
- La conexión se cierra siempre, también ante error (`try/finally`). Nunca se
  deja una sesión abierta entre revisiones.
- Un XML mal formado se registra con su error y no detiene la revisión.

### Pub/Sub

- Suscripción pull creada una vez por ambiente sobre
  `projects/taller-integracion-310700/topics/[AMBIENTE].proyecto.2026-2.grupo4`.
- Cada ~10 s: `pull`, decodificar `message.data` (base64), insertar el id de
  la OC en la bandeja, hacer commit y **recién entonces** `acknowledge`.
- Si algo falla antes del ack, Google reenvía el mensaje y la bandeja lo
  descarta por clave primaria.

## 9. Duplicados e idempotencia

Tres capas, cada una suficiente por sí sola para su caso:

1. **Recepción:** `ordenes_compra.id` es clave primaria. Una OC repetida por
   cualquier canal no entra dos veces.
2. **Aceptación:** el paso de `nueva` a `aceptando` es un
   `UPDATE ... WHERE estado = 'nueva'`. Si dos procesos lo intentan, sólo uno
   gana.
3. **Despacho:** `VentaUnidad.unidad_id` es único. Una unidad no puede quedar
   asignada a dos OC ni despacharse dos veces.

## 10. Despacho y vencidas

- Por cada `VentaUnidad` pendiente de una OC aceptada: mover a `checkOut`,
  `POST /farma-central/dispatch`, `custodia.confirmar_despacho()`.
- Si falla a mitad de camino, la unidad queda pendiente y se reintenta en el
  siguiente tick.
- Si una OC vence sin cumplirse, se liberan sus unidades reservadas y no
  despachadas; vuelven al stock vendible.

## 11. Rate limits

- Cada proceso tiene un tope de requests por tick hacia Farma Central, para
  que la suma de worker de frío, despachador y reponedor quede bajo 250/min.
- Ante 429 se espera lo que indique `Ratelimit-Reset`, como ya hace
  `farma_client.request`.
- El token del sistema de órdenes se cachea hasta su expiración, para no
  acercarse al límite de 20 autenticaciones cada 5 min.

## 12. Observabilidad

- `GET /api/salud/pedidos`: última lectura exitosa de sFTP y Pub/Sub, OC por
  estado, OC próximas a vencer y últimos errores.
- Logs con el id de la OC en cada línea, para seguir una OC de punta a punta
  durante las 36 horas.

## 13. Recursos

| Servicio | Memoria |
|---|---|
| db | 512 MB |
| web | 512 MB |
| worker (frío) | 256 MB |
| pedidos | ~200 MB |
| reponedor | ~200 MB, 1 núcleo como máximo |

Queda justo para 2 GB; se mide en dev antes del 26 de octubre.

## 14. Pruebas

- **Unitarias (pytest)**, con sFTP, Pub/Sub y las APIs reemplazadas por
  versiones falsas:
  - regla B: stock justo, producción en camino que llega antes y después del
    margen, compromisos de varias OC sobre las mismas unidades;
  - deduplicación por cada canal;
  - recuperación desde cada estado intermedio de la tabla de la sección 5;
  - lectura de XML válido y mal formado;
  - stock vendible del portal con mínimo y compromisos.
- **En dev**: dejarlo corriendo varias horas contra las OC reales, medir el
  porcentaje de cumplidas por canal y ajustar los mínimos antes del 26 de
  octubre.

## 15. Pendientes externos

- Contraseña sFTP de dev y prod (portal de grupo).
- Llave Pub/Sub de prod (disponible desde el 26 de octubre).
