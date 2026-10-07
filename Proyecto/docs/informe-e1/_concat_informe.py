#!/usr/bin/env python3
"""Arma INFORME.md concatenando las secciones en orden de lectura."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PARTS = [
    "00-indice.md",
    "01-diagramas.md",
    "02-decisiones-y-proyeccion.md",
    "03-estrategia-abastecimiento.md",
    "04-modelo-custodia.md",
    "05-logistica-operacion.md",
    "06-declaracion-ia.md",
]

header = """# Informe de diseño — Entrega 1

Distribuidora 4 · IIC3103 Taller de Integración 2026-2

Documento para Canvas. Las secciones A–D y la declaración de IA corresponden al PDF *Proyecto - Entrega 1*. Los diagramas de arquitectura, integración y ER son anexos.

Fuente en el repositorio: `docs/informe-e1/`.

---

"""

chunks = [header]
for name in PARTS:
    text = (ROOT / name).read_text(encoding="utf-8")
    chunks.append(text.rstrip() + "\n\n---\n\n")

out = ROOT / "INFORME.md"
out.write_text("".join(chunks).rstrip() + "\n", encoding="utf-8")
print(f"wrote {out} ({out.stat().st_size} bytes)")
