#!/usr/bin/env python3
"""Genera INFORME.html (Mermaid en el navegador; imprimir a PDF para Canvas)."""
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent
md = (ROOT / "INFORME.md").read_text(encoding="utf-8")
body = escape(md)

html = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <title>Informe de diseño — Entrega 1 · Distribuidora 4</title>
  <script src="https://cdn.jsdelivr.net/npm/marked@15.0.7/marked.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/mermaid@11.6.0/dist/mermaid.min.js"></script>
  <style>
    :root {{ font-family: "Segoe UI", system-ui, sans-serif; color: #1c2b24; }}
    body {{ max-width: 980px; margin: 1.5rem auto; padding: 0 1.2rem 3rem; line-height: 1.45; }}
    img {{ max-width: 100%; height: auto; display: block; margin: 0.8rem 0 1.2rem; border: 1px solid #d5e0d9; border-radius: 8px; background: #fff; }}
    h1 {{ font-size: 1.7rem; border-bottom: 2px solid #0f6b4c; padding-bottom: .3rem; }}
    h2 {{ font-size: 1.25rem; margin-top: 2rem; color: #0b3d2e; }}
    h3 {{ font-size: 1.05rem; }}
    table {{ border-collapse: collapse; width: 100%; font-size: .92rem; margin: .8rem 0; }}
    th, td {{ border: 1px solid #d5e0d9; padding: .4rem .5rem; text-align: left; vertical-align: top; }}
    th {{ background: #eef5f1; }}
    code {{ background: #eef3f0; padding: .1rem .3rem; border-radius: 4px; font-size: .88em; }}
    pre {{ background: #f4f7f5; padding: .8rem; overflow: auto; border-radius: 8px; }}
    .mermaid {{ background: #fafcfb; border: 1px solid #d5e0d9; border-radius: 8px; padding: .6rem; margin: 1rem 0; }}
    hr {{ border: 0; border-top: 1px solid #d5e0d9; margin: 2rem 0; }}
    a {{ color: #0f6b4c; }}
    @media print {{
      body {{ max-width: none; margin: 0; }}
      .mermaid, img {{ break-inside: avoid; }}
      h2 {{ break-after: avoid; }}
    }}
  </style>
</head>
<body>
  <div id="out">Cargando informe…</div>
  <textarea id="src" hidden>{body}</textarea>
  <script>
    mermaid.initialize({{ startOnLoad: false, theme: "neutral", securityLevel: "loose" }});
    const raw = document.getElementById("src").value;
    document.getElementById("out").innerHTML = marked.parse(raw);
    document.querySelectorAll("pre > code.language-mermaid").forEach((el) => {{
      const div = document.createElement("div");
      div.className = "mermaid";
      div.textContent = el.textContent;
      el.parentElement.replaceWith(div);
    }});
    mermaid.run().then(() => document.documentElement.setAttribute("data-ready", "1"));
  </script>
</body>
</html>
"""
out = ROOT / "INFORME.html"
out.write_text(html, encoding="utf-8")
print(f"wrote {out} ({out.stat().st_size} bytes)")
