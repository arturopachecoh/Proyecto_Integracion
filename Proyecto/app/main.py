from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.config import FARMA_ENV
from app.db import db_ok
from app import trazabilidad

app = FastAPI(title="Distribuidora 4")

WEB_DIST = Path(__file__).resolve().parent.parent / "web" / "dist"


@app.get("/health")
def health():
    return {"status": "ok", "env": FARMA_ENV, "db": db_ok()}


@app.get("/api/trazabilidad/{codigo}")
def api_trazabilidad_codigo(codigo: str):
    data = trazabilidad.consultar(codigo.strip())
    if data is None:
        raise HTTPException(status_code=404, detail="Lote no encontrado")
    return data


@app.get("/api/trazabilidad")
def api_trazabilidad_query(lote: str | None = Query(default=None)):
    if not lote or not lote.strip():
        raise HTTPException(status_code=400, detail="Falta parametro lote")
    data = trazabilidad.consultar(lote.strip())
    if data is None:
        raise HTTPException(status_code=404, detail="Lote no encontrado")
    return data


@app.get("/", response_class=HTMLResponse)
def home():
    index = WEB_DIST / "index.html"
    if index.exists():
        return index.read_text(encoding="utf-8")
    return "<h1>Distribuidora 4</h1><p>Portal de venta en construccion.</p>"


@app.get("/trazabilidad", response_class=HTMLResponse)
def trazabilidad_html(lote: str | None = Query(default=None)):
    index = WEB_DIST / "index.html"
    if index.exists():
        return index.read_text(encoding="utf-8")
    return (
        "<h1>Trazabilidad de lote</h1>"
        '<form><input name="lote" placeholder="ID de lote"><button>Buscar</button></form>'
        f"<p>Lote consultado: {lote or '-'}</p>"
    )


if WEB_DIST.exists():
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")
