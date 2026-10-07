# Declaración de uso de inteligencia artificial

Obligatoria en el informe (PDF Entrega 1, p. 18; enunciado §18). El mismo contenido, resumido, está en el `README.md` del proyecto.

El uso de IA está permitido. El cuerpo docente puede pedir a cualquier integrante explicar oralmente custodia, PoW o checkout. No entender lo entregado es problema de integridad académica, no de la herramienta.

---

## Herramientas y modelos

| Herramienta | Para qué |
|---|---|
| Cursor (agente) con modelo Grok | Implementación del portal/visor/pagos, este informe, revisión contra el PDF |
| Graphify (`user-graphify`, grafo en `graphify-out/`) | Mapa de componentes y caminos abastecimiento → Farma → custodia, venta → Integrapay |
| Codebase Memory MCP (proyecto `integracion`) | Símbolos, `trace_path`, rutas HTTP, outline de `custodia.py` / `ventas.py` |
| Playwright (Chromium) | Click-through de catálogo, pago, visor con `?lote=`, pedidos |
| Documentación OpenAPI del curso (Farma e Integrapay) | Contratos `auth` / `init` / `challenge` / `products`; no se copió prosa del enunciado como si fuera código |

No se usó un modelo para “inventar” recetas de kits: las cantidades salen de Farma (`components`, `production.batch`) y del ejemplo §4 del enunciado. Los números de solicitudes (#1, #32, #56, venta #6) salen de `logs.txt` y de la API de ventas en PROD.

---

## Tareas asignadas a la IA

1. Leer el enunciado y la propuesta `02`, contrastarlos con el repo (Python ya integraba Farma) y **no** migrar a Next.js.
2. Completar custodia N:M (`lot_relations`), portal Vite, adapter Integrapay, visor con CTE, worker de frío.
3. Despliegue cuidado en la VM (backup, Alembic, sin `down -v`).
4. Corregir UX post-pago (`/trazabilidad?lote=`), bitácora `/pedidos`, botones con caja.
5. Redactar este informe: diagramas instanciados, decisiones con pérdida explícita, estrategia con tanda/batch, modelo D, logística incluyendo el DNS que no resuelve.

La IA **no** eligió secretos, no corrió `DISPATCH_FARMA=1`, no sembró demo en PROD y no reescribió el enunciado.

---

## Cómo se verificó

| Qué | Cómo |
|---|---|
| PoW | `tests/test_checkout_pow.py` contra la regla `sha256(prefix:nonce)` y leading-zero bits del anexo |
| Payload Integrapay | El mismo test arma `backUrls`; en PROD se vio `redirect_url` real y el ~20 % de error |
| Custodia / visor | Consultar un lote `L-KIT-*` producido en la campaña; tiempo de respuesta del orden de 20 ms; aguas arriba llegan a Farma |
| Portal | Playwright: catálogo con precio/stock, checkout, vuelta `exito`, botón de trazabilidad **con** código de lote |
| Diagramas de este informe | Actores y mensajes cruzados con Graphify/`trace_path` (`comprar`, `fabricar`, `iniciar_checkout`, `consultar`) y con líneas de `logs.txt` |
| Requisitos vs. propuesta 02 | Si 02 y el código discrepan, gana el enunciado y el código que corre |

Criterio de parada: un integrante del grupo tiene que poder dibujar en pizarra (1) la reserva FEFO antes de Integrapay, (2) por qué el visor no pega a Farma, (3) por qué el PoW no va en el worker HTTP de Uvicorn.
