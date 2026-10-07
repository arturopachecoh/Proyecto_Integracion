# Informe de diseño — Entrega 1, Distribuidora 4

IIC3103 Taller de Integración, 2026-2. Grupo 4.

Este directorio es el **informe de diseño** que pide el PDF de Entrega 1 (§12.1 / forma de entrega §17). Se sube a Canvas como PDF (`INFORME.md` es el cuerpo concatenado). El código vive en el repositorio GitHub asignado.

El enunciado (`docs/01_enunciado_proyecto_llm.md`, fuente: *Proyecto - Entrega 1.pdf*) manda el diseño. `docs/02_arquitectura_decisiones_entrega1.md` es una **propuesta inicial** (Next.js, esquema en inglés) que **no describe lo que corre**. Aquí se documenta el sistema desplegado: FastAPI + worker + Postgres + SPA Vite.

## Mapa al PDF

| Ítem del PDF | Archivo |
|---|---|
| A. Diagramas de secuencia (prosa + figuras PNG) | [01-diagramas.md](01-diagramas.md) |
| Diagramas Mermaid a tamaño real (mejor lectura) | [diagramas.md](diagramas.md) |
| Anexos: arquitectura, integración, ER | [01-diagramas.md](01-diagramas.md) §§4–6 y [diagramas.md](diagramas.md) |
| B. Tres decisiones + trade-offs y arrastre a E2/E3 | [02-decisiones-y-proyeccion.md](02-decisiones-y-proyeccion.md) |
| C. Estrategia de abastecimiento y producción | [03-estrategia-abastecimiento.md](03-estrategia-abastecimiento.md) |
| D. Modelo de custodia y trazabilidad | [04-modelo-custodia.md](04-modelo-custodia.md) |
| Servidor, HTTPS, 30 kits, huecos logísticos | [05-logistica-operacion.md](05-logistica-operacion.md) |
| Declaración de uso de IA (§18) | [06-declaracion-ia.md](06-declaracion-ia.md) y `README.md` en la raíz del proyecto |
| Cuerpo único (Markdown) | [INFORME.md](INFORME.md) |
| HTML (diagramas renderizados) | [INFORME.html](INFORME.html) |
| PDF para Canvas | [Informe_Entrega1_Distribuidora4.pdf](Informe_Entrega1_Distribuidora4.pdf) |

Los diagramas de secuencia no son genéricos: usan SKU, cantidades y solicitudes que quedaron en `logs.txt` de la corrida PROD del 6–7 de octubre de 2026 (30 unidades de cada kit) y una venta real de `KIT-RESP-ADULTO`.

Para regenerar figuras y PDF: `python3 _render_diagrams.py`, capturar `img/*.html` a PNG, `python3 _concat_informe.py && python3 _build_html.py`. El archivo `Informe_Entrega1_Distribuidora4.pdf` es el que se sube a Canvas. Los Mermaid en vivo están en `diagramas.md`.
