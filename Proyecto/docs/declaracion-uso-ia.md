# Declaración de uso de inteligencia artificial

Obligatoria en el informe (enunciado Entrega 1, §18). Resumen también en el `README.md` del proyecto.

El uso de IA está permitido. El cuerpo docente puede pedir a cualquier integrante explicar oralmente custodia, PoW o checkout. No entender lo entregado es problema de integridad académica, no de la herramienta.

## Herramientas y modelos

| Herramienta | Para qué |
|---|---|
| Cursor (agente) | Código, diagramas, apoyo al informe, deploy en la VM cuando el grupo lo pidió |
| Prompts guardados en `docs/prompts/` | Instrucciones explícitas de análisis y de arquitectura |
| Graphify y Codebase Memory | Mapa de módulos y símbolos (`comprar`, `fabricar`, `iniciar_checkout`) |
| OpenAPI de Farma e Integrapay | Contratos HTTP; no se copió el enunciado como si fuera código |
| Tests (`tests/test_checkout_pow.py`) | PoW y forma de las `backUrls` |

Las recetas de kits no las inventó un modelo: salen de Farma (`components`, `production.batch`) y del ejemplo del enunciado.

## Tareas asignadas a la IA

1. Leer el enunciado (`01`) y el prompt de arquitectura (`prompts/prompt-arquitectura-decisiones.md`), contrastarlos con el repo (Python ya integraba Farma) y no migrar a Next.js.
2. Completar custodia (`lot_relations`), portal Vite, adapter Integrapay, visor y worker de frío.
3. Despliegue en la VM sin borrar Postgres (`docker compose down -v` prohibido).
4. Diagramas de secuencia instanciados (`docs/diagramas.md` / PNG en `docs/img/`).
5. Redacción de apoyo para el informe en Word (estrategia y custodia alineadas al código).

Los prompts completos están en [`prompts/`](prompts/).

## Cómo se verificó

- PoW: `tests/test_checkout_pow.py` contra `sha256(prefix:nonce)`.
- Portal y visor: catálogo, checkout, `/trazabilidad?lote=` sobre lotes `L-KIT-*` de PROD.
- Diagramas: contrastados con `comprar`, `fabricar`, `iniciar_checkout` y el worker (no con una propuesta Next.js).

Si el enunciado y el prompt 2 discrepan, gana el enunciado y el código que corre.
