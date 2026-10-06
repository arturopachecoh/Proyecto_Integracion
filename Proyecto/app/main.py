from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app import catalogo, trazabilidad, ventas
from app.config import FARMA_ENV, PUBLIC_BASE_URL
from app.db import db_ok
from app.integrations.checkout import resultado_mock

app = FastAPI(title="Distribuidora 4")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

WEB_DIST = Path(__file__).resolve().parent.parent / "web" / "dist"


class ItemCarrito(BaseModel):
    sku: str
    cantidad: int = Field(gt=0)


class CarritoIn(BaseModel):
    items: list[ItemCarrito]


class CheckoutIn(BaseModel):
    comprador_nombre: str = Field(min_length=1)
    comprador_email: str = Field(min_length=3)
    items: list[ItemCarrito]


class ConfirmarIn(BaseModel):
    venta_id: int
    resultado: str


def _spa_index() -> str | None:
    index = WEB_DIST / "index.html"
    if index.exists():
        return index.read_text(encoding="utf-8")
    return None


@app.get("/health")
def health():
    return {"status": "ok", "env": FARMA_ENV, "db": db_ok()}


@app.get("/api/catalogo")
def api_catalogo():
    return {"kits": catalogo.listar_kits()}


@app.post("/api/carrito/validar")
def api_validar_carrito(body: CarritoIn):
    return catalogo.validar_carrito([item.model_dump() for item in body.items])


@app.post("/api/checkout")
def api_checkout(body: CheckoutIn):
    try:
        return ventas.iniciar_checkout(
            body.comprador_nombre.strip(),
            body.comprador_email.strip(),
            [item.model_dump() for item in body.items],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e


@app.get("/api/checkout/mock/{venta_id}")
def api_checkout_mock(venta_id: int):
    resultado = resultado_mock()
    try:
        ventas.finalizar(venta_id, resultado)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return RedirectResponse(f"{PUBLIC_BASE_URL}/pago/{resultado}?venta={venta_id}", status_code=302)


@app.post("/api/checkout/confirmar")
def api_checkout_confirmar(body: ConfirmarIn):
    if body.resultado not in {"exito", "cancelado", "error"}:
        raise HTTPException(status_code=400, detail="resultado inválido")
    try:
        return ventas.finalizar(body.venta_id, body.resultado)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


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


if (WEB_DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")


@app.get("/{full_path:path}", response_class=HTMLResponse)
def spa(full_path: str):
    html = _spa_index()
    if html:
        return html
    if full_path.startswith("trazabilidad"):
        return (
            "<h1>Trazabilidad de lote</h1>"
            '<form><input name="lote" placeholder="ID de lote"><button>Buscar</button></form>'
        )
    return "<h1>Distribuidora 4</h1><p>Portal de venta en construccion.</p>"
