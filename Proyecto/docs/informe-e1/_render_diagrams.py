#!/usr/bin/env python3
"""Extrae bloques Mermaid de diagramas.md y deja un HTML por diagrama para screenshot."""
import re
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent
IMG = ROOT / "img"
IMG.mkdir(exist_ok=True)

NAMES = [
    "a1-abastecimiento-pedir",
    "a2-abastecimiento-llegada",
    "a3-acondicionamiento-bli",
    "a4-acondicionamiento-kit",
    "a5-venta-reserva",
    "a6-venta-resultado",
    "b-arquitectura",
    "c-integracion",
    "d-modelo-datos",
]

src = (ROOT / "diagramas.md").read_text(encoding="utf-8")
blocks = re.findall(r"```mermaid\n(.*?)```", src, re.S)
if len(blocks) != len(NAMES):
    raise SystemExit(f"esperaba {len(NAMES)} diagramas, hay {len(blocks)}")

index = []
for name, code in zip(NAMES, blocks):
    html = f"""<!DOCTYPE html>
<html lang="es"><head>
<meta charset="utf-8">
<script src="https://cdn.jsdelivr.net/npm/mermaid@11.6.0/dist/mermaid.min.js"></script>
<style>
  html, body {{ margin: 0; background: #fff; }}
  .wrap {{ display: inline-block; padding: 28px 36px; }}
  .mermaid {{ background: #fff; }}
</style>
</head><body>
<div class="wrap"><div class="mermaid">{escape(code)}</div></div>
<script>
  mermaid.initialize({{ startOnLoad: false, theme: "neutral", securityLevel: "loose" }});
  mermaid.run().then(() => document.documentElement.setAttribute("data-ready", "1"));
</script>
</body></html>"""
    page = IMG / f"{name}.html"
    page.write_text(html, encoding="utf-8")
    index.append(name)
    print("page", page.name)

(IMG / "index.txt").write_text("\n".join(index) + "\n", encoding="utf-8")
print("ok", len(index))
