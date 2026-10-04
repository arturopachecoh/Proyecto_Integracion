from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse

from app.config import FARMA_ENV
from app.db import db_ok

app = FastAPI(title="Distribuidora 4")


@app.get("/health")
def health():
    return {"status": "ok", "env": FARMA_ENV, "db": db_ok()}


@app.get("/", response_class=HTMLResponse)
def home():
    return "<h1>Distribuidora 4</h1><p>Portal de venta en construccion.</p>"


@app.get("/trazabilidad", response_class=HTMLResponse)
def trazabilidad(lote: str | None = Query(default=None)):
    # TODO: consultar el modelo de custodia
    return (
        "<h1>Trazabilidad de lote</h1>"
        '<form><input name="lote" placeholder="ID de lote"><button>Buscar</button></form>'
        f"<p>Lote consultado: {lote or '-'}</p>"
    )
