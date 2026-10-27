# 05 — Plan de implementación Entrega 2: órdenes de compra por sFTP y Pub/Sub

Implementa el diseño de `04_diseno_entrega2_ordenes_compra.md`. Cada tarea
termina en algo que se puede probar por sí solo. Los commits se hacen sólo con
el OK de Mario, con mensajes en español al estilo del repo (una frase que
termina en punto) y sin líneas de atribución de ningún tipo.

**Rama:** `feat/e2-ordenes-compra`, creada desde `origin/develop`. El PR va
contra `develop`.

**Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0, Alembic, PostgreSQL 16,
httpx, paramiko (sFTP), google-auth (Pub/Sub REST), defusedxml (XML).
Pruebas con `unittest`, igual que las existentes: las que necesitan Postgres
se saltan si no está definido `TEST_DATABASE_URL`.

## Restricciones globales

- Nunca tocar PROD, Farma Central de prod ni Integrapay sin OK de Mario.
- Los IDs de OC y de producto son de 24 caracteres hexadecimales
  (`^[0-9a-fA-F]{24}$`, patrón de `POST /farma-central/dispatch`).
- Rate limit de Farma Central y del sistema de órdenes: 250 req/min por grupo.
  `/ordenes-compra/autenticar`: 20 por IP cada 5 min.
- Cada paso de una OC se anota en la base **antes** de llamar a la API externa.
- `app/custodia.py` sigue siendo el único módulo que escribe tablas de custodia.
  `app/pedidos/bandeja.py` es el único que escribe `ordenes_compra` y
  `archivos_sftp`.
- Las llaves (`keys/`) nunca van al repo ni a la imagen de Docker.
- Margen de despacho por defecto: 20 min. Mínimo de stock por defecto: 3 por kit.

## Diferencias con el diseño (decididas al planificar)

- El código de pedidos va en un paquete `app/pedidos/` con un archivo por
  pieza (bandeja, regla, procesador, despachador, conciliador, cierre) en vez
  de un solo `app/pedidos.py`, para que cada archivo tenga una responsabilidad.
- El estado local `despachando` no se guarda como estado: una OC `aceptada`
  con `VentaUnidad` en estado `pendiente` es exactamente eso. Así no hay dos
  fuentes de verdad.
- Las ventas de OC usan un estado nuevo de `Venta`, `orden_compra`. Con eso no
  las tocan ni `recuperar_pendientes()` (sólo mira `pagada`) ni la expiración
  de reservas del PR #4 (sólo mira `pendiente_pago`).
- El candado de stock pasa de `app/ventas.py` a `app/stock.py`, porque ahora
  lo comparten el portal y las OC. Se mantiene el mismo id de candado.
- Una tabla `salud_componentes` guarda la última ejecución correcta y el
  último error de cada pieza, para el endpoint de salud.

## Mapa de archivos

| Archivo | Acción | Responsabilidad |
|---|---|---|
| `requirements.txt` | Modificar | Dependencias nuevas |
| `app/config.py` | Modificar | Variables de sFTP, Pub/Sub, órdenes y stock |
| `.env.example`, `.gitignore`, `.dockerignore` | Modificar | Nombres de variables; excluir `keys/` |
| `app/models.py` | Modificar | `OrdenCompra`, `ArchivoSftp`, `SaludComponente`, estado `orden_compra` |
| `alembic/versions/20261021_e2_ordenes_compra.py` | Crear | Migración |
| `app/ordenes_client.py` | Crear | Cliente HTTP del sistema de órdenes |
| `app/farma_client.py` | Modificar | `dispatch()` |
| `app/stock.py` | Crear | Candado de stock, mínimos, comprometido, vendible por el portal |
| `app/custodia.py` | Modificar | `crear_venta(estado=)` y consultas por venta |
| `app/ventas.py`, `app/catalogo.py` | Modificar | El portal usa el stock vendible |
| `app/pedidos/__init__.py` | Crear | Paquete |
| `app/pedidos/bandeja.py` | Crear | Lectura y escritura de `ordenes_compra` y `archivos_sftp` |
| `app/pedidos/regla.py` | Crear | Validación de la OC y regla B |
| `app/pedidos/cierre.py` | Crear | Cerrar una OC liberando su reserva |
| `app/pedidos/procesador.py` | Crear | Decidir y avisar la decisión |
| `app/pedidos/despachador.py` | Crear | Asignar unidades y despachar |
| `app/pedidos/conciliador.py` | Crear | Sincronizar con el sistema de órdenes |
| `app/canales/__init__.py` | Crear | Paquete |
| `app/canales/formatos.py` | Crear | Leer el id de OC de un XML o de un mensaje |
| `app/canales/sftp.py` | Crear | Lector sFTP |
| `app/canales/pubsub.py` | Crear | Lector Pub/Sub (pull REST) |
| `app/scripts/crear_suscripcion.py` | Crear | Crear la suscripción una vez por ambiente |
| `app/produccion.py` | Modificar | `una_vuelta()`, `intentar_vuelta()`, `ProduccionOcupada` |
| `app/reposicion.py` | Crear | Faltantes contra el mínimo |
| `app/salud.py` | Crear | Registro y resumen de salud |
| `app/main.py` | Modificar | `GET /api/salud/pedidos` |
| `worker/pedidos.py`, `worker/reponedor.py` | Crear | Ciclos de los contenedores nuevos |
| `docker-compose.yml`, `README.md` | Modificar | Servicios nuevos y cómo operarlos |
| `tests/test_config_stock.py` | Crear | Mínimos por kit (sin red ni Postgres) |
| `tests/test_ordenes_client.py` | Crear | Cliente HTTP (sin red) |
| `tests/test_regla.py` | Crear | Regla B y validación (sin red ni Postgres) |
| `tests/test_canales.py` | Crear | Formatos y lectores con dobles (sin red ni Postgres) |
| `tests/test_reposicion.py` | Crear | Faltantes (sin red ni Postgres) |
| `tests/test_pedidos_db.py` | Crear | Bandeja, stock, procesador, despachador, conciliador (Postgres) |

## Cómo correr las pruebas

Sin Postgres:

```bash
cd Proyecto
python -m unittest tests/test_config_stock.py tests/test_ordenes_client.py tests/test_regla.py tests/test_canales.py tests/test_reposicion.py -v
```

Con Postgres desechable (nunca el de PROD):

```bash
docker run -d --rm --name pg-test -e POSTGRES_USER=farma -e POSTGRES_PASSWORD=x -e POSTGRES_DB=farma -p 127.0.0.1:55432:5432 postgres:16
export TEST_DATABASE_URL=postgresql+psycopg://farma:x@127.0.0.1:55432/farma
DATABASE_URL=$TEST_DATABASE_URL alembic upgrade head
python -m unittest tests/test_pedidos_db.py -v
```

---

### Tarea 1: Dependencias y configuración

**Archivos:**
- Modificar: `requirements.txt`, `app/config.py`, `.env.example`, `.gitignore`, `.dockerignore`
- Crear: `app/stock.py` (sólo los mínimos en esta tarea)
- Prueba: `tests/test_config_stock.py`

**Interfaces:**
- Produce: constantes de `app/config.py` listadas abajo; `stock.parsear_minimos(texto) -> dict[str, int]`; `stock.minimo(sku) -> int`.

- [ ] **Paso 1: Escribir la prueba que falla**

`tests/test_config_stock.py`:

```python
"""Tests de los minimos de stock por kit (sin red ni Postgres)."""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://farma:x@localhost/farma")

from app import stock  # noqa: E402


class MinimosTest(unittest.TestCase):
    def test_vacio_no_tiene_excepciones(self):
        self.assertEqual(stock.parsear_minimos(""), {})

    def test_lee_pares_sku_cantidad(self):
        self.assertEqual(
            stock.parsear_minimos("KIT-DIABETES=2, KIT-GASTRO=4"),
            {"KIT-DIABETES": 2, "KIT-GASTRO": 4},
        )

    def test_rechaza_formato_malo(self):
        for malo in ("KIT-DIABETES", "KIT-DIABETES=dos", "=3", "KIT-A=-1"):
            with self.subTest(malo=malo), self.assertRaises(ValueError):
                stock.parsear_minimos(malo)

    def test_minimo_usa_el_default_si_no_hay_excepcion(self):
        self.assertEqual(stock.minimo("KIT-QUE-NO-ESTA"), stock.STOCK_MINIMO_DEFAULT)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Paso 2: Correrla y ver que falla**

Run: `python -m unittest tests/test_config_stock.py -v`
Esperado: FALLA con `ModuleNotFoundError: No module named 'app.stock'`.

- [ ] **Paso 3: Implementar**

`requirements.txt`, agregar al final:

```
paramiko==3.5.*
google-auth==2.*
requests==2.32.*
defusedxml==0.7.*
```

`app/config.py`, agregar al final:

```python
# Sistema de ordenes de compra (mismo host que Farma Central)
ORDENES_BASE_URL = (os.getenv("ORDENES_BASE_URL") or FARMA_BASE_URL).rstrip("/")
ORDENES_SECRET = os.getenv("ORDENES_SECRET") or FARMA_API_KEY

# Casilla sFTP del grupo (Anexo 1 del enunciado E2)
SFTP_HOST = os.getenv("SFTP_HOST", "")
SFTP_PORT = int(os.getenv("SFTP_PORT", "22"))
SFTP_USER = os.getenv("SFTP_USER", "")
SFTP_PASSWORD = os.getenv("SFTP_PASSWORD", "")
SFTP_DIR = os.getenv("SFTP_DIR", ".")
SFTP_KNOWN_HOSTS = os.getenv("SFTP_KNOWN_HOSTS", "keys/known_hosts")

# Pub/Sub (Anexo 2): suscripcion pull propia del grupo
PUBSUB_PROJECT = "taller-integracion-310700"
PUBSUB_TOPIC = os.getenv(
    "PUBSUB_TOPIC",
    f"projects/{PUBSUB_PROJECT}/topics/{FARMA_ENV}.proyecto.2026-2.grupo{FARMA_GROUP}",
)
PUBSUB_SUBSCRIPTION = os.getenv(
    "PUBSUB_SUBSCRIPTION",
    f"projects/{PUBSUB_PROJECT}/subscriptions/grupo{FARMA_GROUP}-{FARMA_ENV}",
)
PUBSUB_KEY_FILE = os.getenv("PUBSUB_KEY_FILE", f"keys/pubsub-{FARMA_ENV}.json")

# Pedidos
MARGEN_DESPACHO_MIN = int(os.getenv("MARGEN_DESPACHO_MIN", "20"))
STOCK_MINIMO_DEFAULT = int(os.getenv("STOCK_MINIMO_DEFAULT", "3"))
STOCK_MINIMO = os.getenv("STOCK_MINIMO", "")  # excepciones: "KIT-DIABETES=2,KIT-GASTRO=4"
```

`.env.example`, agregar al final:

```
ORDENES_BASE_URL=
ORDENES_SECRET=
SFTP_HOST=
SFTP_PORT=
SFTP_USER=
SFTP_PASSWORD=
SFTP_DIR=
SFTP_KNOWN_HOSTS=
PUBSUB_TOPIC=
PUBSUB_SUBSCRIPTION=
PUBSUB_KEY_FILE=
MARGEN_DESPACHO_MIN=
STOCK_MINIMO_DEFAULT=
STOCK_MINIMO=
```

`.gitignore`, agregar debajo de `.env`:

```
# Llaves de Pub/Sub y known_hosts del sFTP: nunca al repo
keys/
```

`.dockerignore`, agregar una línea:

```
keys
```

`app/stock.py` (primera versión; la Tarea 4 la completa):

```python
"""Stock comprometido con OC y stock que puede vender el portal.

Las OC tienen prioridad sobre el portal: el portal solo vende lo que esta
sobre el minimo de cada kit y no esta comprometido con una OC aceptada.
"""
from app.config import STOCK_MINIMO, STOCK_MINIMO_DEFAULT


def parsear_minimos(texto: str) -> dict[str, int]:
    """Lee "KIT-A=2,KIT-B=4". Un error de formato detiene el arranque:
    es mejor no partir que partir con minimos equivocados."""
    minimos: dict[str, int] = {}
    for parte in (p.strip() for p in texto.split(",")):
        if not parte:
            continue
        sku, sep, n = parte.partition("=")
        sku, n = sku.strip(), n.strip()
        if not sep or not sku or not n.isdigit():
            raise ValueError(f"STOCK_MINIMO mal escrito: {parte!r} (se espera SKU=N)")
        minimos[sku] = int(n)
    return minimos


_MINIMOS = parsear_minimos(STOCK_MINIMO)


def minimo(sku: str) -> int:
    return _MINIMOS.get(sku, STOCK_MINIMO_DEFAULT)
```

- [ ] **Paso 4: Correr la prueba y ver que pasa**

Run: `pip install -r requirements.txt && python -m unittest tests/test_config_stock.py -v`
Esperado: 4 tests OK.

- [ ] **Paso 5: Commit (con OK de Mario)**

```bash
git add requirements.txt app/config.py app/stock.py .env.example .gitignore .dockerignore tests/test_config_stock.py
git commit -m "Configurar dependencias y variables de la Entrega 2."
```

---

### Tarea 2: Modelo de datos y migración

**Archivos:**
- Modificar: `app/models.py`
- Crear: `alembic/versions/20261021_e2_ordenes_compra.py`
- Prueba: `tests/test_pedidos_db.py` (se crea aquí y crece en las tareas siguientes)

**Interfaces:**
- Produce: modelos `OrdenCompra`, `ArchivoSftp`, `SaludComponente`; constante `ESTADOS_OC`; estado de venta `orden_compra`.

- [ ] **Paso 1: Escribir la prueba que falla**

`tests/test_pedidos_db.py`:

```python
"""Tests de pedidos (OC) contra un Postgres desechable (NUNCA el de PROD).

Se saltan si TEST_DATABASE_URL no esta definido. Ver docs/05 para correrlos.
"""
from __future__ import annotations

import os
import unittest
import uuid
from datetime import datetime, timedelta, timezone

TEST_DB = os.environ.get("TEST_DATABASE_URL")
if TEST_DB:
    os.environ["DATABASE_URL"] = TEST_DB
    os.environ.setdefault("FARMA_GROUP", "4")  # las OC de prueba son para el grupo 4

    from sqlalchemy import select
    from sqlalchemy.exc import IntegrityError

    from app import custodia
    from app.db import SessionLocal
    from app.models import OrdenCompra, Venta


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _oc_id() -> str:
    return uuid.uuid4().hex[:24]


class BaseDB(unittest.TestCase):
    """SKU unico por test: la base de prueba puede tener datos de antes."""

    def setUp(self):
        self.sufijo = uuid.uuid4().hex[:8]
        self.sku = f"KIT-TEST-{self.sufijo}"

    def sembrar(self, n: int, espacio: str = "bodega") -> list[str]:
        """Registra n unidades vendibles del kit de prueba y devuelve sus ids."""
        vence = (_ahora() + timedelta(days=10)).isoformat()
        productos = [{"_id": uuid.uuid4().hex[:24], "sku": self.sku,
                      "batch": f"L-TEST-{self.sufijo}", "expiresAt": vence} for _ in range(n)]
        custodia.registrar_llegadas(productos, espacio)
        return [p["_id"] for p in productos]

    def oc_remota(self, oc_id: str, cantidad: int = 1, estado: str = "creada",
                  vence_en: timedelta = timedelta(hours=2), despachado: int = 0) -> dict:
        """Una OC como la devuelve GET /ordenes-compra/ordenes/{id}."""
        return {"id": oc_id, "cliente": "9", "proveedor": "4", "sku": self.sku,
                "cantidad": cantidad, "despachado": despachado, "precioUnitario": 1500,
                "nombreCliente": "", "estado": estado,
                "vencimiento": (_ahora() + vence_en).isoformat()}


@unittest.skipUnless(TEST_DB, "TEST_DATABASE_URL no definido")
class ModeloTest(BaseDB):
    def test_oc_repetida_viola_la_clave_primaria(self):
        oc_id = _oc_id()
        with SessionLocal.begin() as s:
            s.add(OrdenCompra(id=oc_id, canal="sftp", estado="nueva"))
        with self.assertRaises(IntegrityError):
            with SessionLocal.begin() as s:
                s.add(OrdenCompra(id=oc_id, canal="pubsub", estado="nueva"))

    def test_venta_acepta_estado_orden_compra(self):
        venta_id = custodia.crear_venta("Cliente", None, 0, canal="sftp",
                                        orden_externa_id=_oc_id(), estado="orden_compra")
        with SessionLocal() as s:
            self.assertEqual(s.get(Venta, venta_id).estado, "orden_compra")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Paso 2: Correrla y ver que falla**

Run: `python -m unittest tests/test_pedidos_db.py -v` (con `TEST_DATABASE_URL`)
Esperado: FALLA con `ImportError: cannot import name 'OrdenCompra'`.

- [ ] **Paso 3: Implementar**

`app/models.py`:

1. Cambiar el import de SQLAlchemy por:

```python
from sqlalchemy import (JSON, DateTime, Enum, ForeignKey, Index, Integer, MetaData, String,
                        Text, UniqueConstraint, func)
```

2. Agregar al docstring del módulo, después de `venta_unidades`:

```
ordenes_compra  OC recibidas por sFTP y Pub/Sub, y lo que se decidio con cada una
archivos_sftp   archivos de la casilla sFTP ya leidos
salud_componentes  ultima ejecucion correcta y ultimo error de cada pieza de pedidos
```

3. En `Venta.estado`, cambiar el enum por:

```python
        _enum("pendiente_pago", "pagada", "cancelada", "error", "orden_compra",
              name="estado_venta"),
```

4. Agregar antes de `__all__`:

```python
ESTADOS_OC = ("nueva", "aceptando", "aceptada", "rechazando", "rechazada",
              "cumplida", "vencida", "descartada")


class OrdenCompra(Base):
    """OC recibida. La clave primaria es el id de la OC: una OC repetida por
    cualquier canal no entra dos veces."""

    __tablename__ = "ordenes_compra"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    canal: Mapped[str] = mapped_column(_enum("sftp", "pubsub", "mensajeria", name="canal_oc"))
    origen_ref: Mapped[str | None] = mapped_column(String(255))  # archivo o id del mensaje
    sku: Mapped[str | None] = mapped_column(String(50), index=True)
    cantidad: Mapped[int | None] = mapped_column(Integer)
    vencimiento: Mapped[datetime | None] = mapped_column(Fecha)
    cliente: Mapped[str | None] = mapped_column(String(120))
    estado: Mapped[str] = mapped_column(_enum(*ESTADOS_OC, name="estado_oc"), default="nueva")
    estado_remoto: Mapped[str | None] = mapped_column(String(20))
    despachado_remoto: Mapped[int] = mapped_column(Integer, default=0)
    venta_id: Mapped[int | None] = mapped_column(ForeignKey("ventas.id"), unique=True)
    decision: Mapped[dict | None] = mapped_column(JSON)  # numeros vistos y motivo
    intentos: Mapped[int] = mapped_column(Integer, default=0)
    ultimo_error: Mapped[str | None] = mapped_column(Text)
    recibida_en: Mapped[datetime] = mapped_column(Fecha, server_default=func.now())
    decidida_en: Mapped[datetime | None] = mapped_column(Fecha)
    actualizada_en: Mapped[datetime] = mapped_column(
        Fecha, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (Index("ix_ordenes_compra_estado_vencimiento", "estado", "vencimiento"),)


class ArchivoSftp(Base):
    """Archivo de la casilla ya leido. La casilla puede seguir mostrandolo."""

    __tablename__ = "archivos_sftp"

    nombre: Mapped[str] = mapped_column(String(255), primary_key=True)
    oc_id: Mapped[str | None] = mapped_column(String(40))  # None si el archivo era invalido
    error: Mapped[str | None] = mapped_column(Text)
    leido_en: Mapped[datetime] = mapped_column(Fecha, server_default=func.now())


class SaludComponente(Base):
    __tablename__ = "salud_componentes"

    nombre: Mapped[str] = mapped_column(String(40), primary_key=True)
    ultimo_ok: Mapped[datetime | None] = mapped_column(Fecha)
    ultimo_error_en: Mapped[datetime | None] = mapped_column(Fecha)
    ultimo_error: Mapped[str | None] = mapped_column(Text)
```

5. Agregar `"OrdenCompra", "ArchivoSftp", "SaludComponente", "ESTADOS_OC"` a `__all__`.

`app/custodia.py`, en `crear_venta`, agregar el parámetro `estado` y usarlo:

```python
def crear_venta(comprador_nombre: str, comprador_email: str | None, total: int,
                canal: str = "portal", orden_externa_id: str | None = None,
                items: list[dict] | None = None,
                transaccion_id: str | None = None,
                estado: str = "pendiente_pago") -> int:
    """items: [{sku, cantidad, precio_unitario}, ...]
    estado: pendiente_pago para el portal; orden_compra para una OC (no pasa por pago)."""
    with SessionLocal.begin() as s:
        v = Venta(comprador_nombre=comprador_nombre, comprador_email=comprador_email,
                  total=total, canal=canal, orden_externa_id=orden_externa_id,
                  transaccion_id=transaccion_id, estado=estado)
```

(el resto de la función no cambia).

`alembic/versions/20261021_e2_ordenes_compra.py`:

```python
"""E2: ordenes de compra, archivos sFTP, salud y ventas de OC

Revision ID: e2b5d1c0a9f4
Revises: e1a7c0d1e2f3
Create Date: 2026-10-21 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e2b5d1c0a9f4"
down_revision: Union[str, None] = "e1a7c0d1e2f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ESTADOS_VENTA_E1 = ("pendiente_pago", "pagada", "cancelada", "error")
ESTADOS_VENTA_E2 = ESTADOS_VENTA_E1 + ("orden_compra",)
ESTADOS_OC = ("nueva", "aceptando", "aceptada", "rechazando", "rechazada",
              "cumplida", "vencida", "descartada")


def _check_ventas(valores: tuple[str, ...]) -> None:
    # Mismo patron que la migracion e1: se borra por los dos nombres posibles
    op.execute("ALTER TABLE ventas DROP CONSTRAINT IF EXISTS ck_ventas_estado_venta")
    op.execute("ALTER TABLE ventas DROP CONSTRAINT IF EXISTS estado_venta")
    lista = ", ".join(f"'{v}'" for v in valores)
    op.execute(f"ALTER TABLE ventas ADD CONSTRAINT ck_ventas_estado_venta CHECK (estado IN ({lista}))")


def _enum(*valores: str, name: str) -> sa.Enum:
    return sa.Enum(*valores, name=name, native_enum=False, create_constraint=True, length=20)


def upgrade() -> None:
    _check_ventas(ESTADOS_VENTA_E2)

    op.create_table(
        "ordenes_compra",
        sa.Column("id", sa.String(40), nullable=False),
        sa.Column("canal", _enum("sftp", "pubsub", "mensajeria", name="canal_oc"), nullable=False),
        sa.Column("origen_ref", sa.String(255)),
        sa.Column("sku", sa.String(50)),
        sa.Column("cantidad", sa.Integer()),
        sa.Column("vencimiento", sa.DateTime(timezone=True)),
        sa.Column("cliente", sa.String(120)),
        sa.Column("estado", _enum(*ESTADOS_OC, name="estado_oc"), nullable=False),
        sa.Column("estado_remoto", sa.String(20)),
        sa.Column("despachado_remoto", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("venta_id", sa.Integer()),
        sa.Column("decision", sa.JSON()),
        sa.Column("intentos", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ultimo_error", sa.Text()),
        sa.Column("recibida_en", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("decidida_en", sa.DateTime(timezone=True)),
        sa.Column("actualizada_en", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["venta_id"], ["ventas.id"],
                                name=op.f("fk_ordenes_compra_venta_id_ventas")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ordenes_compra")),
        sa.UniqueConstraint("venta_id", name=op.f("uq_ordenes_compra_venta_id")),
    )
    op.create_index("ix_ordenes_compra_estado_vencimiento", "ordenes_compra",
                    ["estado", "vencimiento"])
    op.create_index(op.f("ix_ordenes_compra_sku"), "ordenes_compra", ["sku"])

    op.create_table(
        "archivos_sftp",
        sa.Column("nombre", sa.String(255), nullable=False),
        sa.Column("oc_id", sa.String(40)),
        sa.Column("error", sa.Text()),
        sa.Column("leido_en", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("nombre", name=op.f("pk_archivos_sftp")),
    )

    op.create_table(
        "salud_componentes",
        sa.Column("nombre", sa.String(40), nullable=False),
        sa.Column("ultimo_ok", sa.DateTime(timezone=True)),
        sa.Column("ultimo_error_en", sa.DateTime(timezone=True)),
        sa.Column("ultimo_error", sa.Text()),
        sa.PrimaryKeyConstraint("nombre", name=op.f("pk_salud_componentes")),
    )


def downgrade() -> None:
    op.drop_table("salud_componentes")
    op.drop_table("archivos_sftp")
    op.drop_index(op.f("ix_ordenes_compra_sku"), table_name="ordenes_compra")
    op.drop_index("ix_ordenes_compra_estado_vencimiento", table_name="ordenes_compra")
    op.drop_table("ordenes_compra")
    # Sin la tabla de OC, sus ventas quedan como canceladas para respetar el CHECK de E1
    op.execute("UPDATE ventas SET estado = 'cancelada' WHERE estado = 'orden_compra'")
    _check_ventas(ESTADOS_VENTA_E1)
```

- [ ] **Paso 4: Migrar y correr la prueba**

Run:
```bash
DATABASE_URL=$TEST_DATABASE_URL alembic upgrade head
DATABASE_URL=$TEST_DATABASE_URL alembic downgrade -1 && DATABASE_URL=$TEST_DATABASE_URL alembic upgrade head
python -m unittest tests/test_pedidos_db.py -v
```
Esperado: la migración sube, baja y vuelve a subir sin error; 2 tests OK.

- [ ] **Paso 5: Commit (con OK de Mario)**

```bash
git add app/models.py app/custodia.py alembic/versions/20261021_e2_ordenes_compra.py tests/test_pedidos_db.py
git commit -m "Agregar tablas de ordenes de compra, archivos sFTP y salud."
```

---

### Tarea 3: Cliente del sistema de órdenes y despacho en Farma Central

**Archivos:**
- Crear: `app/ordenes_client.py`
- Modificar: `app/farma_client.py`
- Prueba: `tests/test_ordenes_client.py`

**Interfaces:**
- Produce:
  - `ordenes_client.obtener(oc_id: str) -> dict`
  - `ordenes_client.actualizar_estado(oc_id: str, estado: str) -> None`
  - `ordenes_client.pubsub_key() -> dict`
  - `farma_client.dispatch(product_id: str, order_id: str) -> None`
  - Errores HTTP como `httpx.HTTPStatusError` (igual que `farma_client`).

- [ ] **Paso 1: Escribir la prueba que falla**

`tests/test_ordenes_client.py`:

```python
"""Tests del cliente del sistema de ordenes (sin red)."""
from __future__ import annotations

import base64
import json
import os
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://farma:x@localhost/farma")
os.environ.setdefault("FARMA_BASE_URL", "https://dev.example")
os.environ.setdefault("FARMA_GROUP", "4")
os.environ.setdefault("FARMA_API_KEY", "test-secret")

import httpx  # noqa: E402

from app import farma_client, ordenes_client  # noqa: E402

BASE = ordenes_client.ORDENES_BASE_URL


def _jwt(exp: float) -> str:
    payload = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).decode().rstrip("=")
    return f"x.{payload}.y"


def _resp(status: int, method: str, url: str, body=None, headers=None) -> httpx.Response:
    return httpx.Response(status, json=body, headers=headers,
                          request=httpx.Request(method, url))


class OrdenesClientTest(unittest.TestCase):
    def setUp(self):
        ordenes_client._token = None
        ordenes_client._token_exp = 0

    def _auth(self, *a, **k):
        return _resp(200, "POST", f"{BASE}/ordenes-compra/autenticar",
                     {"token": _jwt(time.time() + 3600)})

    def test_obtener_usa_bearer_y_cachea_el_token(self):
        url = f"{BASE}/ordenes-compra/ordenes/abc"
        with patch("httpx.post", side_effect=self._auth) as post, \
             patch("httpx.request", return_value=_resp(200, "GET", url, {"id": "abc"})) as req:
            self.assertEqual(ordenes_client.obtener("abc"), {"id": "abc"})
            ordenes_client.obtener("abc")
        self.assertEqual(post.call_count, 1)  # el token se reutiliza
        self.assertTrue(req.call_args.kwargs["headers"]["Authorization"].startswith("Bearer "))

    def test_401_renueva_el_token_una_vez(self):
        url = f"{BASE}/ordenes-compra/ordenes/abc"
        respuestas = [_resp(401, "GET", url), _resp(200, "GET", url, {"id": "abc"})]
        with patch("httpx.post", side_effect=self._auth) as post, \
             patch("httpx.request", side_effect=respuestas):
            self.assertEqual(ordenes_client.obtener("abc"), {"id": "abc"})
        self.assertEqual(post.call_count, 2)

    def test_429_espera_ratelimit_reset_y_reintenta(self):
        url = f"{BASE}/ordenes-compra/ordenes/abc"
        respuestas = [_resp(429, "GET", url, headers={"Ratelimit-Reset": "2"}),
                      _resp(200, "GET", url, {"id": "abc"})]
        with patch("httpx.post", side_effect=self._auth), \
             patch("httpx.request", side_effect=respuestas), \
             patch("time.sleep") as dormir:
            ordenes_client.obtener("abc")
        dormir.assert_called_once_with(3.0)

    def test_actualizar_estado_404_levanta_error(self):
        url = f"{BASE}/ordenes-compra/ordenes/abc/estado"
        with patch("httpx.post", side_effect=self._auth), \
             patch("httpx.request", return_value=_resp(404, "POST", url)):
            with self.assertRaises(httpx.HTTPStatusError):
                ordenes_client.actualizar_estado("abc", "aceptada")

    def test_actualizar_estado_envia_el_estado(self):
        url = f"{BASE}/ordenes-compra/ordenes/abc/estado"
        with patch("httpx.post", side_effect=self._auth), \
             patch("httpx.request", return_value=httpx.Response(
                 204, request=httpx.Request("POST", url))) as req:
            ordenes_client.actualizar_estado("abc", "aceptada")
        self.assertEqual(req.call_args.kwargs["json"], {"estado": "aceptada"})


class DispatchTest(unittest.TestCase):
    def test_dispatch_envia_producto_y_orden(self):
        with patch.object(farma_client, "request", return_value=None) as req:
            farma_client.dispatch("p" * 24, "o" * 24)
        req.assert_called_once_with("POST", "/farma-central/dispatch",
                                    json={"productId": "p" * 24, "orderId": "o" * 24})


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Paso 2: Correrla y ver que falla**

Run: `python -m unittest tests/test_ordenes_client.py -v`
Esperado: FALLA con `ImportError: cannot import name 'ordenes_client'`.

- [ ] **Paso 3: Implementar**

`app/ordenes_client.py`:

```python
"""Cliente del sistema de ordenes de compra.

Mismo patron que farma_client:
- Pide el token una vez y lo reutiliza hasta que esta por vencer
  (/ordenes-compra/autenticar permite solo 20 llamadas por IP cada 5 minutos).
- Si una llamada responde 401, renueva el token y reintenta una vez.
- Si responde 429 (limite de 250/min por grupo), espera lo que indica
  Ratelimit-Reset (maximo 60 s) y reintenta, hasta 6 intentos en total.
"""
import threading
import time

import httpx

from app.config import FARMA_GROUP, ORDENES_BASE_URL, ORDENES_SECRET
from app.farma_client import _jwt_exp

_token: str | None = None
_token_exp: float = 0
_lock = threading.Lock()


def get_token(force: bool = False) -> str:
    global _token, _token_exp
    with _lock:
        if force or _token is None or time.time() > _token_exp - 60:
            r = httpx.post(
                f"{ORDENES_BASE_URL}/ordenes-compra/autenticar",
                json={"group": FARMA_GROUP, "secret": ORDENES_SECRET},
                timeout=15,
            )
            r.raise_for_status()
            _token = r.json()["token"]
            _token_exp = _jwt_exp(_token)
        return _token


def request(method: str, path: str, **kwargs):
    url = f"{ORDENES_BASE_URL}{path}"
    renovado = forzar = False
    for _ in range(6):
        headers = {"Authorization": "Bearer " + get_token(force=forzar)}
        forzar = False
        r = httpx.request(method, url, headers=headers, timeout=15, **kwargs)
        if r.status_code == 401 and not renovado:
            renovado = forzar = True
            continue
        if r.status_code == 429:
            try:
                espera = float(r.headers.get("Ratelimit-Reset", "10"))
            except ValueError:
                espera = 10
            time.sleep(min(espera, 60) + 1)
            continue
        break
    r.raise_for_status()
    return r.json() if r.content else None


def obtener(oc_id: str) -> dict:
    """Detalle oficial de la OC. Al consultarla, el sistema aplica el vencimiento."""
    return request("GET", f"/ordenes-compra/ordenes/{oc_id}")


def actualizar_estado(oc_id: str, estado: str) -> None:
    """estado: aceptada o rechazada. 400 si la OC ya no esta en creada."""
    request("POST", f"/ordenes-compra/ordenes/{oc_id}/estado", json={"estado": estado})


def pubsub_key() -> dict:
    """Llave de la cuenta de servicio para crear la suscripcion de Pub/Sub."""
    return request("GET", "/ordenes-compra/pubsub/key")
```

`app/farma_client.py`, agregar después de `move_product`:

```python
def dispatch(product_id: str, order_id: str):
    """Entrega una unidad que esta en checkOut a la OC indicada."""
    return request("POST", "/farma-central/dispatch",
                   json={"productId": product_id, "orderId": order_id})
```

- [ ] **Paso 4: Correr la prueba y ver que pasa**

Run: `python -m unittest tests/test_ordenes_client.py -v`
Esperado: 6 tests OK.

- [ ] **Paso 5: Commit (con OK de Mario)**

```bash
git add app/ordenes_client.py app/farma_client.py tests/test_ordenes_client.py
git commit -m "Agregar cliente del sistema de ordenes y despacho a Farma Central."
```

---

### Tarea 4: Stock comprometido y prioridad de las OC en el portal

**Archivos:**
- Modificar: `app/stock.py`, `app/custodia.py`, `app/ventas.py`, `app/catalogo.py`
- Prueba: `tests/test_pedidos_db.py`

**Interfaces:**
- Consume: `OrdenCompra` (Tarea 2), `stock.minimo` (Tarea 1).
- Produce:
  - `stock.candado_stock(esperar_s: float = 0)` (context manager; `RuntimeError` si no se obtiene)
  - `stock.comprometido(sku: str) -> int`
  - `stock.en_camino_antes(sku: str, limite: datetime) -> int`
  - `stock.vendible_portal(sku: str) -> int`
  - `custodia.unidades_de_venta(venta_id) -> int`, `custodia.despachadas_de_venta(venta_id) -> int`,
    `custodia.pendientes_de_venta(venta_id) -> list[str]`, `custodia.espacio_de(unidad_id) -> str | None`

- [ ] **Paso 1: Escribir la prueba que falla**

Agregar a `tests/test_pedidos_db.py`, dentro del bloque `if TEST_DB:` del inicio:

```python
    from unittest.mock import patch

    from app import stock
    from app.models import Solicitud
```

y antes de `if __name__ == "__main__":`:

```python
@unittest.skipUnless(TEST_DB, "TEST_DATABASE_URL no definido")
class StockTest(BaseDB):
    def _oc_aceptada(self, cantidad: int, asignar: list[str]) -> str:
        oc_id = _oc_id()
        venta_id = custodia.crear_venta("C", None, 0, canal="sftp",
                                        orden_externa_id=oc_id, estado="orden_compra")
        if asignar:
            custodia.asignar_unidades_a_venta(venta_id, asignar)
        with SessionLocal.begin() as s:
            s.add(OrdenCompra(id=oc_id, canal="sftp", estado="aceptada", sku=self.sku,
                              cantidad=cantidad, venta_id=venta_id,
                              vencimiento=_ahora() + timedelta(hours=2)))
        return oc_id

    def test_comprometido_cuenta_solo_lo_que_falta_asignar(self):
        ids = self.sembrar(1)
        self._oc_aceptada(cantidad=3, asignar=ids)
        self.assertEqual(stock.comprometido(self.sku), 2)

    def test_en_camino_antes_respeta_el_limite(self):
        with SessionLocal.begin() as s:
            s.add(Solicitud(tipo="fabricacion", sku=self.sku, cantidad=2,
                            llega_en=_ahora() + timedelta(minutes=30)))
            s.add(Solicitud(tipo="fabricacion", sku=self.sku, cantidad=5,
                            llega_en=_ahora() + timedelta(hours=3)))
        self.assertEqual(stock.en_camino_antes(self.sku, _ahora() + timedelta(hours=1)), 2)

    def test_portal_solo_vende_sobre_el_minimo_y_lo_comprometido(self):
        self.sembrar(6)
        self._oc_aceptada(cantidad=1, asignar=[])
        with patch.object(stock, "minimo", return_value=3):
            self.assertEqual(stock.vendible_portal(self.sku), 2)  # 6 - 3 - 1

    def test_portal_nunca_negativo(self):
        self.sembrar(1)
        with patch.object(stock, "minimo", return_value=3):
            self.assertEqual(stock.vendible_portal(self.sku), 0)
```

- [ ] **Paso 2: Correrla y ver que falla**

Run: `python -m unittest tests/test_pedidos_db.py -v`
Esperado: FALLA con `AttributeError: module 'app.stock' has no attribute 'comprometido'`.

- [ ] **Paso 3: Implementar**

`app/stock.py` completo:

```python
"""Stock comprometido con OC y stock que puede vender el portal.

Las OC tienen prioridad sobre el portal: el portal solo vende lo que esta
sobre el minimo de cada kit y no esta comprometido con una OC aceptada.
"""
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, text

from app import custodia
from app.config import STOCK_MINIMO, STOCK_MINIMO_DEFAULT
from app.db import SessionLocal, engine
from app.models import OrdenCompra, Solicitud, VentaUnidad

# Mismo id que usaba el candado de ventas del portal: portal y OC deciden
# sobre el mismo stock, asi que comparten candado
LOCK_STOCK = 4_000_003
ESTADOS_COMPROMETIDOS = ("aceptando", "aceptada")


@contextmanager
def candado_stock(esperar_s: float = 0):
    """Un solo proceso a la vez reserva stock (portal u OC). Es un candado de
    Postgres: se libera solo si el proceso muere. Si no se obtiene en
    esperar_s segundos, levanta RuntimeError."""
    limite = time.monotonic() + esperar_s
    with engine.connect() as conn:
        while not conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": LOCK_STOCK}).scalar():
            if time.monotonic() >= limite:
                raise RuntimeError("Hay otra operacion de stock en curso; reintenta")
            time.sleep(0.2)
        try:
            yield
        finally:
            conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": LOCK_STOCK})


def parsear_minimos(texto: str) -> dict[str, int]:
    """Lee "KIT-A=2,KIT-B=4". Un error de formato detiene el arranque:
    es mejor no partir que partir con minimos equivocados."""
    minimos: dict[str, int] = {}
    for parte in (p.strip() for p in texto.split(",")):
        if not parte:
            continue
        sku, sep, n = parte.partition("=")
        sku, n = sku.strip(), n.strip()
        if not sep or not sku or not n.isdigit():
            raise ValueError(f"STOCK_MINIMO mal escrito: {parte!r} (se espera SKU=N)")
        minimos[sku] = int(n)
    return minimos


_MINIMOS = parsear_minimos(STOCK_MINIMO)


def minimo(sku: str) -> int:
    return _MINIMOS.get(sku, STOCK_MINIMO_DEFAULT)


def comprometido(sku: str) -> int:
    """Unidades prometidas a OC aceptadas que todavia no tienen unidad asignada.
    Sin esto, una misma unidad en camino se contaria para varias OC."""
    with SessionLocal() as s:
        filas = s.execute(
            select(OrdenCompra.cantidad, OrdenCompra.venta_id)
            .where(OrdenCompra.sku == sku, OrdenCompra.estado.in_(ESTADOS_COMPROMETIDOS))
        ).all()
        total = 0
        for cantidad, venta_id in filas:
            asignadas = 0
            if venta_id is not None:
                asignadas = s.scalar(select(func.count()).select_from(VentaUnidad)
                                     .where(VentaUnidad.venta_id == venta_id)) or 0
            total += max(0, (cantidad or 0) - asignadas)
        return total


def en_camino_antes(sku: str, limite: datetime,
                    max_atraso: timedelta = timedelta(minutes=30)) -> int:
    """Unidades pedidas (compra o fabricacion) que llegan antes de `limite`.
    Igual que custodia.en_camino, las atrasadas mas de max_atraso se dan por perdidas."""
    ahora = datetime.now(timezone.utc)
    with SessionLocal() as s:
        return s.scalar(
            select(func.coalesce(func.sum(Solicitud.cantidad), 0))
            .where(Solicitud.sku == sku, Solicitud.estado == "pendiente",
                   Solicitud.llega_en <= limite, Solicitud.llega_en > ahora - max_atraso)
        ) or 0


def vendible_portal(sku: str) -> int:
    return max(0, custodia.stock_disponible(sku) - minimo(sku) - comprometido(sku))
```

`app/custodia.py`, agregar después de `despachos_pendientes`:

```python
def unidades_de_venta(venta_id: int) -> int:
    """Unidades asignadas a una venta (pendientes y despachadas)."""
    with SessionLocal() as s:
        return s.scalar(select(sqlfunc.count()).select_from(VentaUnidad)
                        .where(VentaUnidad.venta_id == venta_id)) or 0


def despachadas_de_venta(venta_id: int) -> int:
    with SessionLocal() as s:
        return s.scalar(select(sqlfunc.count()).select_from(VentaUnidad)
                        .where(VentaUnidad.venta_id == venta_id,
                               VentaUnidad.estado == "despachada")) or 0


def pendientes_de_venta(venta_id: int) -> list[str]:
    """Unidades asignadas a la venta que aun no salen."""
    with SessionLocal() as s:
        return list(s.scalars(select(VentaUnidad.unidad_id)
                              .where(VentaUnidad.venta_id == venta_id,
                                     VentaUnidad.estado == "pendiente")
                              .order_by(VentaUnidad.id)))


def espacio_de(unidad_id: str) -> str | None:
    with SessionLocal() as s:
        u = s.get(Unidad, unidad_id)
        return u.espacio_actual if u else None
```

`app/ventas.py`:

1. Borrar `LOCK_VENTA`, `_candado_venta` y los imports que solo usaba
   (`contextmanager`, `text`, `engine`).
2. Cambiar `from app import catalogo, custodia` por `from app import catalogo, custodia, stock`.
3. En `iniciar_checkout`, reemplazar `with _candado_venta():` y la revisión de stock por:

```python
    with stock.candado_stock(esperar_s=5):
        unidad_ids: list[str] = []
        for linea in validado["items"]:
            # Las OC tienen prioridad: solo se vende lo que esta sobre el minimo
            vendibles = stock.vendible_portal(linea["sku"])
            if vendibles < linea["cantidad"]:
                raise ValueError(
                    f"{linea['sku']}: stock insuficiente al reservar "
                    f"(hay {vendibles}, se piden {linea['cantidad']})"
                )
            disponibles = custodia.unidades_disponibles(linea["sku"])
            unidad_ids.extend(u.id for u in disponibles[: linea["cantidad"]])
```

(el resto de la función queda igual, indentado dentro del `with`).

`app/catalogo.py`:

1. Cambiar `from app import custodia, farma_client` por `from app import farma_client, stock`.
2. En los dos lugares de `listar_kits()` donde dice
   `"stock": custodia.stock_disponible(sku),` poner `"stock": stock.vendible_portal(sku),`.

- [ ] **Paso 4: Correr las pruebas y ver que pasan**

Run: `python -m unittest tests/test_pedidos_db.py tests/test_checkout_pow.py tests/test_config_stock.py -v`
Esperado: todo OK (las de E1 siguen pasando).

- [ ] **Paso 5: Commit (con OK de Mario)**

```bash
git add app/stock.py app/custodia.py app/ventas.py app/catalogo.py tests/test_pedidos_db.py
git commit -m "Dar prioridad a las ordenes de compra sobre el portal en el stock."
```

---

### Tarea 5: Bandeja y regla de aceptación

**Archivos:**
- Crear: `app/pedidos/__init__.py` (vacío), `app/pedidos/bandeja.py`, `app/pedidos/regla.py`
- Prueba: `tests/test_regla.py`, `tests/test_pedidos_db.py`

**Interfaces:**
- Consume: `stock.en_camino_antes`, `stock.comprometido`, `custodia.stock_disponible`.
- Produce:
  - `bandeja.ID_OC` (regex compilada)
  - `bandeja.recibir(oc_id, canal, origen_ref) -> bool`
  - `bandeja.recibir_archivo(nombre, oc_id: str | None, error: str | None = None) -> bool`
  - `bandeja.archivos_no_leidos(nombres: list[str]) -> list[str]`
  - `bandeja.nuevas(limite=20) -> list[str]`
  - `bandeja.get(oc_id) -> OrdenCompra | None`
  - `bandeja.en_estado(*estados) -> list[OrdenCompra]`
  - `bandeja.aceptadas_por_vencimiento() -> list[OrdenCompra]`
  - `bandeja.cumplidas_sin_confirmar() -> list[OrdenCompra]`
  - `bandeja.guardar_detalle(oc_id, oc: dict) -> None`
  - `bandeja.reclamar(oc_id, desde, hacia, decision: dict | None = None) -> bool`
  - `bandeja.marcar(oc_id, estado, error: str | None = None) -> None`
  - `bandeja.registrar_error(oc_id, error: str) -> None`
  - `bandeja.enlazar_venta(oc_id, venta_id) -> None`
  - `bandeja.contar_por_estado() -> dict[str, int]`
  - `regla.Evaluacion` (dataclass con `disponible`, `acepta`, `reservar_ahora`, `como_dict()`)
  - `regla.validar_oc(oc: dict, ahora: datetime, es_kit) -> tuple[str | None, str | None]`
  - `regla.evaluar(sku, cantidad, vencimiento: datetime) -> Evaluacion`

- [ ] **Paso 1: Escribir las pruebas que fallan**

`tests/test_regla.py`:

```python
"""Tests de la regla B de aceptacion de OC (sin red ni Postgres)."""
from __future__ import annotations

import os
import unittest
from datetime import datetime, timedelta, timezone

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://farma:x@localhost/farma")
os.environ.setdefault("FARMA_GROUP", "4")

from app.pedidos import regla  # noqa: E402

AHORA = datetime(2026, 10, 27, 15, 0, tzinfo=timezone.utc)


def _ev(cantidad, stock, en_camino=0, comprometido=0):
    return regla.Evaluacion(sku="KIT-X", cantidad=cantidad, stock=stock,
                            en_camino=en_camino, comprometido=comprometido)


class EvaluacionTest(unittest.TestCase):
    def test_stock_justo_acepta_y_reserva_todo(self):
        ev = _ev(cantidad=2, stock=2)
        self.assertTrue(ev.acepta)
        self.assertEqual(ev.reservar_ahora, 2)

    def test_produccion_en_camino_completa_lo_que_falta(self):
        ev = _ev(cantidad=2, stock=1, en_camino=1)
        self.assertTrue(ev.acepta)
        self.assertEqual(ev.reservar_ahora, 1)

    def test_lo_comprometido_no_se_cuenta_dos_veces(self):
        # Un kit en camino ya prometido a otra OC no sirve para esta
        self.assertFalse(_ev(cantidad=1, stock=0, en_camino=1, comprometido=1).acepta)

    def test_no_reserva_stock_prometido_a_oc_anteriores(self):
        ev = _ev(cantidad=2, stock=2, en_camino=2, comprometido=2)
        self.assertTrue(ev.acepta)
        self.assertEqual(ev.reservar_ahora, 0)

    def test_como_dict_guarda_los_numeros_y_la_decision(self):
        d = _ev(cantidad=2, stock=1).como_dict()
        self.assertEqual((d["stock"], d["disponible"], d["acepta"]), (1, 1, False))


class ValidarOcTest(unittest.TestCase):
    def _oc(self, **cambios):
        oc = {"proveedor": "4", "estado": "creada", "sku": "KIT-X", "cantidad": 1,
              "vencimiento": (AHORA + timedelta(hours=2)).isoformat()}
        oc.update(cambios)
        return oc

    def _validar(self, oc):
        return regla.validar_oc(oc, AHORA, es_kit=lambda sku: sku == "KIT-X")

    def test_oc_valida(self):
        self.assertEqual(self._validar(self._oc()), (None, None))

    def test_de_otro_proveedor_se_descarta(self):
        self.assertEqual(self._validar(self._oc(proveedor="7"))[0], "descartar")

    def test_ya_no_creada_se_descarta(self):
        self.assertEqual(self._validar(self._oc(estado="vencida"))[0], "descartar")

    def test_sku_que_no_es_kit_se_rechaza(self):
        self.assertEqual(self._validar(self._oc(sku="API-AMOXI-500"))[0], "rechazar")

    def test_cantidad_invalida_se_rechaza(self):
        self.assertEqual(self._validar(self._oc(cantidad=0))[0], "rechazar")

    def test_plazo_menor_al_margen_se_rechaza(self):
        vence = (AHORA + timedelta(minutes=10)).isoformat()
        self.assertEqual(self._validar(self._oc(vencimiento=vence))[0], "rechazar")


if __name__ == "__main__":
    unittest.main()
```

Agregar a `tests/test_pedidos_db.py`, dentro del bloque `if TEST_DB:`:

```python
    from app.pedidos import bandeja
```

y la clase:

```python
@unittest.skipUnless(TEST_DB, "TEST_DATABASE_URL no definido")
class BandejaTest(BaseDB):
    def test_recibir_es_idempotente_entre_canales(self):
        oc_id = _oc_id()
        self.assertTrue(bandeja.recibir(oc_id, "pubsub", "msg-1"))
        self.assertFalse(bandeja.recibir(oc_id, "pubsub", "msg-1"))
        self.assertFalse(bandeja.recibir(oc_id, "sftp", "archivo.xml"))
        self.assertEqual(bandeja.get(oc_id).canal, "pubsub")

    def test_archivo_leido_no_vuelve_a_aparecer(self):
        nombre = f"oc-{self.sufijo}.xml"
        self.assertEqual(bandeja.archivos_no_leidos([nombre]), [nombre])
        self.assertTrue(bandeja.recibir_archivo(nombre, _oc_id()))
        self.assertEqual(bandeja.archivos_no_leidos([nombre]), [])

    def test_archivo_invalido_se_anota_sin_oc(self):
        nombre = f"malo-{self.sufijo}.xml"
        self.assertFalse(bandeja.recibir_archivo(nombre, None, "XML invalido"))
        self.assertEqual(bandeja.archivos_no_leidos([nombre]), [])

    def test_reclamar_solo_gana_una_vez(self):
        oc_id = _oc_id()
        bandeja.recibir(oc_id, "sftp", "a.xml")
        self.assertTrue(bandeja.reclamar(oc_id, "nueva", "aceptando", {"acepta": True}))
        self.assertFalse(bandeja.reclamar(oc_id, "nueva", "rechazando"))
        o = bandeja.get(oc_id)
        self.assertEqual((o.estado, o.decision), ("aceptando", {"acepta": True}))

    def test_guardar_detalle_copia_la_oc_oficial(self):
        oc_id = _oc_id()
        bandeja.recibir(oc_id, "sftp", "a.xml")
        bandeja.guardar_detalle(oc_id, self.oc_remota(oc_id, cantidad=2, despachado=1))
        o = bandeja.get(oc_id)
        self.assertEqual((o.sku, o.cantidad, o.estado_remoto, o.despachado_remoto),
                         (self.sku, 2, "creada", 1))
```

- [ ] **Paso 2: Correrlas y ver que fallan**

Run: `python -m unittest tests/test_regla.py -v` y `python -m unittest tests/test_pedidos_db.py -v`
Esperado: FALLAN con `ModuleNotFoundError: No module named 'app.pedidos'`.

- [ ] **Paso 3: Implementar**

`app/pedidos/__init__.py`: archivo vacío.

`app/pedidos/bandeja.py`:

```python
"""Bandeja de OC recibidas.

Unico modulo que escribe ordenes_compra y archivos_sftp. La clave primaria
de ordenes_compra es el id de la OC: recibir dos veces la misma OC, por el
mismo canal o por otro, no hace nada la segunda vez.
"""
import re
from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert

from app.db import SessionLocal
from app.models import ArchivoSftp, OrdenCompra

# Patron de los ids de OC y de producto (el de POST /farma-central/dispatch)
ID_OC = re.compile(r"^[0-9a-fA-F]{24}$")


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _fecha(iso: str | None) -> datetime | None:
    return datetime.fromisoformat(iso.replace("Z", "+00:00")) if iso else None


def _insertar(s, oc_id: str, canal: str, origen_ref: str | None) -> bool:
    r = s.execute(
        insert(OrdenCompra)
        .values(id=oc_id, canal=canal, origen_ref=origen_ref, estado="nueva",
                despachado_remoto=0, intentos=0)
        .on_conflict_do_nothing(index_elements=["id"])
    )
    return r.rowcount == 1


def recibir(oc_id: str, canal: str, origen_ref: str | None) -> bool:
    """Anota una OC recibida. Devuelve False si ya estaba."""
    with SessionLocal.begin() as s:
        return _insertar(s, oc_id, canal, origen_ref)


def recibir_archivo(nombre: str, oc_id: str | None, error: str | None = None) -> bool:
    """Anota un archivo de la casilla y su OC en una sola transaccion.
    Un archivo invalido (oc_id None) queda anotado con su error para no
    leerlo de nuevo en cada revision. Devuelve True si la OC es nueva."""
    with SessionLocal.begin() as s:
        s.execute(insert(ArchivoSftp).values(nombre=nombre, oc_id=oc_id, error=error)
                  .on_conflict_do_nothing(index_elements=["nombre"]))
        return _insertar(s, oc_id, "sftp", nombre) if oc_id else False


def archivos_no_leidos(nombres: list[str]) -> list[str]:
    if not nombres:
        return []
    with SessionLocal() as s:
        leidos = set(s.scalars(select(ArchivoSftp.nombre).where(ArchivoSftp.nombre.in_(nombres))))
    return [n for n in nombres if n not in leidos]


def nuevas(limite: int = 20) -> list[str]:
    with SessionLocal() as s:
        return list(s.scalars(select(OrdenCompra.id).where(OrdenCompra.estado == "nueva")
                              .order_by(OrdenCompra.recibida_en).limit(limite)))


def get(oc_id: str) -> OrdenCompra | None:
    with SessionLocal() as s:
        return s.get(OrdenCompra, oc_id)


def en_estado(*estados: str) -> list[OrdenCompra]:
    with SessionLocal() as s:
        return list(s.scalars(select(OrdenCompra).where(OrdenCompra.estado.in_(estados))
                              .order_by(OrdenCompra.vencimiento.asc().nulls_last())))


def aceptadas_por_vencimiento() -> list[OrdenCompra]:
    """OC aceptadas que aun no vencen, la que vence primero adelante."""
    with SessionLocal() as s:
        return list(s.scalars(select(OrdenCompra)
                              .where(OrdenCompra.estado == "aceptada",
                                     OrdenCompra.vencimiento > _ahora())
                              .order_by(OrdenCompra.vencimiento)))


def cumplidas_sin_confirmar() -> list[OrdenCompra]:
    """Cumplidas segun custodia que el sistema de ordenes aun no muestra cumplidas."""
    with SessionLocal() as s:
        return list(s.scalars(select(OrdenCompra).where(
            OrdenCompra.estado == "cumplida",
            OrdenCompra.estado_remoto.is_distinct_from("cumplida"))))


def guardar_detalle(oc_id: str, oc: dict) -> None:
    """Copia lo que dice la OC oficial (la fuente de verdad del pedido)."""
    with SessionLocal.begin() as s:
        o = s.get(OrdenCompra, oc_id)
        if o is None:
            return
        o.sku = oc.get("sku")
        o.cantidad = oc.get("cantidad")
        o.vencimiento = _fecha(oc.get("vencimiento"))
        o.cliente = (oc.get("nombreCliente") or str(oc.get("cliente") or "")) or None
        o.estado_remoto = oc.get("estado")
        o.despachado_remoto = int(oc.get("despachado") or 0)


def reclamar(oc_id: str, desde: str, hacia: str, decision: dict | None = None) -> bool:
    """Cambia el estado solo si sigue en `desde`. Si dos procesos lo intentan
    a la vez, uno solo gana. Devuelve True si gano este."""
    valores = {"estado": hacia, "decidida_en": _ahora()}
    if decision is not None:
        valores["decision"] = decision
    with SessionLocal.begin() as s:
        r = s.execute(update(OrdenCompra)
                      .where(OrdenCompra.id == oc_id, OrdenCompra.estado == desde)
                      .values(**valores))
        return r.rowcount == 1


def marcar(oc_id: str, estado: str, error: str | None = None) -> None:
    with SessionLocal.begin() as s:
        o = s.get(OrdenCompra, oc_id)
        if o is None:
            return
        o.estado = estado
        if error:
            o.ultimo_error = error[:2000]


def registrar_error(oc_id: str, error: str) -> None:
    with SessionLocal.begin() as s:
        o = s.get(OrdenCompra, oc_id)
        if o is not None:
            o.intentos += 1
            o.ultimo_error = error[:2000]


def enlazar_venta(oc_id: str, venta_id: int) -> None:
    with SessionLocal.begin() as s:
        s.get(OrdenCompra, oc_id).venta_id = venta_id


def contar_por_estado() -> dict[str, int]:
    with SessionLocal() as s:
        return dict(s.execute(select(OrdenCompra.estado, func.count())
                              .group_by(OrdenCompra.estado)).all())
```

`app/pedidos/regla.py`:

```python
"""Regla B de aceptacion de OC (seccion 6 del diseno, docs/04).

Se acepta si lo que hay en stock, mas lo que llega antes del vencimiento con
margen, menos lo ya prometido a otras OC, cubre la cantidad pedida.
"""
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta

from app import custodia, stock
from app.config import FARMA_GROUP, MARGEN_DESPACHO_MIN

MARGEN_DESPACHO = timedelta(minutes=MARGEN_DESPACHO_MIN)


def _fecha(iso: str | None) -> datetime | None:
    return datetime.fromisoformat(iso.replace("Z", "+00:00")) if iso else None


@dataclass(frozen=True)
class Evaluacion:
    sku: str
    cantidad: int
    stock: int
    en_camino: int
    comprometido: int

    @property
    def disponible(self) -> int:
        return self.stock + self.en_camino - self.comprometido

    @property
    def acepta(self) -> bool:
        return self.disponible >= self.cantidad

    @property
    def reservar_ahora(self) -> int:
        """Unidades que se reservan al aceptar: las que hay en stock y no estan
        prometidas a OC anteriores. El resto lo asigna el despachador al nacer."""
        return max(0, min(self.cantidad, self.stock - self.comprometido))

    def como_dict(self) -> dict:
        return {**asdict(self), "disponible": self.disponible, "acepta": self.acepta,
                "reservar_ahora": self.reservar_ahora}


def validar_oc(oc: dict, ahora: datetime, es_kit) -> tuple[str | None, str | None]:
    """Revisa la OC oficial antes de mirar el stock. Devuelve (accion, motivo):
    - ("descartar", ...): no se le puede responder (no es nuestra o ya no esta creada);
    - ("rechazar", ...): es nuestra y esta creada, pero no se puede cumplir;
    - (None, None): pasa a la regla de stock."""
    if str(oc.get("proveedor")) != str(FARMA_GROUP):
        return "descartar", f"la OC es para el grupo {oc.get('proveedor')}"
    if oc.get("estado") != "creada":
        return "descartar", f"la OC ya esta {oc.get('estado')}"
    if not es_kit(oc.get("sku")):
        return "rechazar", f"{oc.get('sku')} no es un kit del catalogo"
    if not isinstance(oc.get("cantidad"), int) or oc["cantidad"] < 1:
        return "rechazar", f"cantidad invalida: {oc.get('cantidad')!r}"
    vencimiento = _fecha(oc.get("vencimiento"))
    if vencimiento is None or vencimiento <= ahora + MARGEN_DESPACHO:
        return "rechazar", "el plazo no alcanza para despachar"
    return None, None


def evaluar(sku: str, cantidad: int, vencimiento: datetime) -> Evaluacion:
    """Hay que llamarla con stock.candado_stock tomado."""
    return Evaluacion(
        sku=sku,
        cantidad=cantidad,
        stock=custodia.stock_disponible(sku),
        en_camino=stock.en_camino_antes(sku, vencimiento - MARGEN_DESPACHO),
        comprometido=stock.comprometido(sku),
    )
```

- [ ] **Paso 4: Correr las pruebas y ver que pasan**

Run: `python -m unittest tests/test_regla.py -v` y `python -m unittest tests/test_pedidos_db.py -v`
Esperado: todo OK.

- [ ] **Paso 5: Commit (con OK de Mario)**

```bash
git add app/pedidos/__init__.py app/pedidos/bandeja.py app/pedidos/regla.py tests/test_regla.py tests/test_pedidos_db.py
git commit -m "Agregar bandeja de ordenes de compra y regla de aceptacion."
```

---

### Tarea 6: Procesador (decidir y avisar)

**Archivos:**
- Crear: `app/pedidos/cierre.py`, `app/pedidos/procesador.py`
- Prueba: `tests/test_pedidos_db.py`

**Interfaces:**
- Consume: `bandeja.*`, `regla.*`, `stock.candado_stock`, `ordenes_client.obtener/actualizar_estado`,
  `custodia.crear_venta/asignar_unidades_a_venta/unidades_disponibles/liberar_reserva`.
- Produce:
  - `cierre.cerrar(oc_id, estado_final, motivo=None) -> None`
  - `procesador.procesar_nuevas(limite=20) -> int`
  - `procesador.procesar(oc_id) -> None`
  - `procesador.enviar_decision(oc_id) -> None`
  - `procesador.conciliar_decision(oc_id) -> None`
  - `procesador.reintentar_decisiones() -> None`
  - `procesador.asegurar_venta(oc_id) -> int`

- [ ] **Paso 1: Escribir la prueba que falla**

Agregar a `tests/test_pedidos_db.py`, dentro del bloque `if TEST_DB:`:

```python
    import httpx

    from app.pedidos import procesador
```

y la clase:

```python
def _http_error(status: int) -> "httpx.HTTPStatusError":
    req = httpx.Request("POST", "https://x")
    return httpx.HTTPStatusError("error", request=req, response=httpx.Response(status, request=req))


@unittest.skipUnless(TEST_DB, "TEST_DATABASE_URL no definido")
class ProcesadorTest(BaseDB):
    def setUp(self):
        super().setUp()
        self.es_kit = patch.object(procesador, "_es_kit", side_effect=lambda sku: sku == self.sku)
        self.es_kit.start()
        self.addCleanup(self.es_kit.stop)

    def _recibir(self) -> str:
        oc_id = _oc_id()
        bandeja.recibir(oc_id, "sftp", f"{oc_id}.xml")
        return oc_id

    def test_con_stock_reserva_y_acepta(self):
        self.sembrar(2)
        oc_id = self._recibir()
        with patch.object(procesador, "ordenes_client") as api:
            api.obtener.return_value = self.oc_remota(oc_id, cantidad=2)
            procesador.procesar(oc_id)
        api.actualizar_estado.assert_called_once_with(oc_id, "aceptada")
        o = bandeja.get(oc_id)
        self.assertEqual(o.estado, "aceptada")
        self.assertEqual(custodia.unidades_de_venta(o.venta_id), 2)
        self.assertEqual(custodia.stock_disponible(self.sku), 0)

    def test_sin_stock_rechaza_y_guarda_el_motivo(self):
        oc_id = self._recibir()
        with patch.object(procesador, "ordenes_client") as api:
            api.obtener.return_value = self.oc_remota(oc_id, cantidad=1)
            procesador.procesar(oc_id)
        api.actualizar_estado.assert_called_once_with(oc_id, "rechazada")
        o = bandeja.get(oc_id)
        self.assertEqual(o.estado, "rechazada")
        self.assertFalse(o.decision["acepta"])

    def test_oc_inexistente_se_descarta(self):
        oc_id = self._recibir()
        with patch.object(procesador, "ordenes_client") as api:
            api.obtener.side_effect = _http_error(404)
            procesador.procesar(oc_id)
        self.assertEqual(bandeja.get(oc_id).estado, "descartada")
        api.actualizar_estado.assert_not_called()

    def test_caida_tras_anotar_aceptando_se_recupera(self):
        # Se anoto "aceptando" pero la API no respondio: la OC sigue creada
        self.sembrar(1)
        oc_id = self._recibir()
        with patch.object(procesador, "ordenes_client") as api:
            api.obtener.return_value = self.oc_remota(oc_id)
            api.actualizar_estado.side_effect = httpx.ConnectError("caida")
            with self.assertRaises(httpx.ConnectError):
                procesador.procesar(oc_id)
        self.assertEqual(bandeja.get(oc_id).estado, "aceptando")

        with patch.object(procesador, "ordenes_client") as api:
            api.obtener.return_value = self.oc_remota(oc_id)
            procesador.reintentar_decisiones()
        api.actualizar_estado.assert_called_once_with(oc_id, "aceptada")
        self.assertEqual(bandeja.get(oc_id).estado, "aceptada")

    def test_aceptacion_que_si_llego_no_se_reenvia(self):
        self.sembrar(1)
        oc_id = self._recibir()
        bandeja.reclamar(oc_id, "nueva", "aceptando")
        with patch.object(procesador, "ordenes_client") as api:
            api.obtener.return_value = self.oc_remota(oc_id, estado="aceptada")
            procesador.reintentar_decisiones()
        api.actualizar_estado.assert_not_called()
        self.assertEqual(bandeja.get(oc_id).estado, "aceptada")

    def test_aceptando_que_vencio_libera_la_reserva(self):
        self.sembrar(1)
        oc_id = self._recibir()
        with patch.object(procesador, "ordenes_client") as api:
            api.obtener.return_value = self.oc_remota(oc_id)
            api.actualizar_estado.side_effect = httpx.ConnectError("caida")
            with self.assertRaises(httpx.ConnectError):
                procesador.procesar(oc_id)
        self.assertEqual(custodia.stock_disponible(self.sku), 0)

        with patch.object(procesador, "ordenes_client") as api:
            api.obtener.return_value = self.oc_remota(oc_id, estado="vencida")
            procesador.reintentar_decisiones()
        self.assertEqual(bandeja.get(oc_id).estado, "vencida")
        self.assertEqual(custodia.stock_disponible(self.sku), 1)

    def test_la_misma_oc_dos_veces_acepta_una_sola_vez(self):
        self.sembrar(2)
        oc_id = self._recibir()
        bandeja.recibir(oc_id, "pubsub", "msg-repetido")
        with patch.object(procesador, "ordenes_client") as api:
            api.obtener.return_value = self.oc_remota(oc_id, cantidad=1)
            procesador.procesar_nuevas()
            procesador.procesar_nuevas()
        api.actualizar_estado.assert_called_once_with(oc_id, "aceptada")
        self.assertEqual(custodia.stock_disponible(self.sku), 1)
```

- [ ] **Paso 2: Correrla y ver que falla**

Run: `python -m unittest tests/test_pedidos_db.py -v`
Esperado: FALLA con `ImportError: cannot import name 'procesador'`.

- [ ] **Paso 3: Implementar**

`app/pedidos/cierre.py`:

```python
"""Cerrar una OC que no se va a cumplir: libera lo reservado y no despachado."""
import logging

from app import custodia
from app.pedidos import bandeja

log = logging.getLogger("pedidos")


def cerrar(oc_id: str, estado_final: str, motivo: str | None = None) -> None:
    """estado_final: vencida, rechazada o descartada. Las unidades reservadas
    y sin despachar vuelven al stock vendible."""
    o = bandeja.get(oc_id)
    if o is None:
        return
    if o.venta_id is not None:
        custodia.liberar_reserva(o.venta_id)
    bandeja.marcar(oc_id, estado_final, error=motivo)
    log.info("OC %s cerrada como %s%s", oc_id, estado_final, f": {motivo}" if motivo else "")
```

`app/pedidos/procesador.py`:

```python
"""Procesador de OC: decide cada OC nueva y avisa la decision.

Cada paso se anota en la base ANTES de llamar a la API externa. Si el proceso
cae entre la anotacion y la respuesta, reintentar_decisiones() consulta la OC
oficial y sigue desde lo que diga ella (seccion 5 del diseno, docs/04).
"""
import logging
from datetime import datetime, timezone

import httpx

from app import custodia, ordenes_client, stock
from app.operaciones import catalogo
from app.pedidos import bandeja, cierre, regla

log = logging.getLogger("pedidos")

ESPERA_CANDADO_S = 30
ESTADO_OBJETIVO = {"aceptando": "aceptada", "rechazando": "rechazada"}


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _es_kit(sku: str | None) -> bool:
    return bool(sku) and bool(catalogo().get(sku, {}).get("sellable"))


def procesar_nuevas(limite: int = 20) -> int:
    hechas = 0
    for oc_id in bandeja.nuevas(limite):
        try:
            procesar(oc_id)
            hechas += 1
        except Exception as e:
            # Queda "nueva" (o en aceptando/rechazando): se reintenta en el proximo tick
            log.exception("OC %s: error procesando", oc_id)
            bandeja.registrar_error(oc_id, repr(e))
    return hechas


def procesar(oc_id: str) -> None:
    try:
        oc = ordenes_client.obtener(oc_id)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            bandeja.reclamar(oc_id, "nueva", "descartada",
                             {"motivo": "la OC no existe en el sistema de ordenes"})
            log.warning("OC %s no existe: descartada", oc_id)
            return
        raise
    bandeja.guardar_detalle(oc_id, oc)

    accion, motivo = regla.validar_oc(oc, _ahora(), es_kit=_es_kit)
    if accion == "descartar":
        bandeja.reclamar(oc_id, "nueva", "descartada", {"motivo": motivo})
        log.info("OC %s descartada: %s", oc_id, motivo)
        return
    if accion == "rechazar":
        bandeja.reclamar(oc_id, "nueva", "rechazando", {"motivo": motivo})
    else:
        _decidir_por_stock(oc_id, oc)
    enviar_decision(oc_id)


def _decidir_por_stock(oc_id: str, oc: dict) -> None:
    vencimiento = regla._fecha(oc["vencimiento"])
    with stock.candado_stock(esperar_s=ESPERA_CANDADO_S):
        ev = regla.evaluar(oc["sku"], oc["cantidad"], vencimiento)
        decision = ev.como_dict()
        decision["precio_unitario"] = oc.get("precioUnitario")  # para la Venta de la OC
        if not ev.acepta:
            decision["motivo"] = "no hay stock ni produccion que llegue a tiempo"
            bandeja.reclamar(oc_id, "nueva", "rechazando", decision)
            log.info("OC %s se rechazara: %s", oc_id, decision)
            return
        if not bandeja.reclamar(oc_id, "nueva", "aceptando", decision):
            return  # otro proceso ya la tomo
        venta_id = asegurar_venta(oc_id)
        if ev.reservar_ahora:
            ids = [u.id for u in custodia.unidades_disponibles(oc["sku"])][: ev.reservar_ahora]
            custodia.asignar_unidades_a_venta(venta_id, ids)
        log.info("OC %s se aceptara: %s", oc_id, decision)


def asegurar_venta(oc_id: str) -> int:
    """La Venta de una OC aceptada (la crea si una caida la dejo sin venta).
    Es lo que deja la OC en el modelo de custodia: unidades, lote y cliente."""
    o = bandeja.get(oc_id)
    if o.venta_id is not None:
        return o.venta_id
    precio = int(round((o.decision or {}).get("precio_unitario") or 0))
    venta_id = custodia.crear_venta(
        comprador_nombre=o.cliente or "", comprador_email=None,
        total=precio * (o.cantidad or 0), canal=o.canal, orden_externa_id=o.id,
        items=[{"sku": o.sku, "cantidad": o.cantidad, "precio_unitario": precio}],
        estado="orden_compra",
    )
    bandeja.enlazar_venta(oc_id, venta_id)
    return venta_id


def _enviar(oc_id: str, objetivo: str) -> None:
    ordenes_client.actualizar_estado(oc_id, objetivo)
    bandeja.marcar(oc_id, objetivo)
    log.info("OC %s %s en el sistema de ordenes", oc_id, objetivo)


def enviar_decision(oc_id: str) -> None:
    o = bandeja.get(oc_id)
    objetivo = ESTADO_OBJETIVO.get(o.estado) if o else None
    if objetivo is None:
        return
    try:
        _enviar(oc_id, objetivo)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 400:
            conciliar_decision(oc_id)  # ya no estaba en creada: ver que paso
            return
        raise


def conciliar_decision(oc_id: str) -> None:
    """Para una OC en aceptando/rechazando: consulta la fuente oficial y sigue."""
    o = bandeja.get(oc_id)
    objetivo = ESTADO_OBJETIVO.get(o.estado) if o else None
    if objetivo is None:
        return
    remoto = ordenes_client.obtener(oc_id)
    bandeja.guardar_detalle(oc_id, remoto)
    estado = remoto.get("estado")
    if estado == "creada":
        _enviar(oc_id, objetivo)
    elif estado == objetivo or (objetivo == "aceptada" and estado == "cumplida"):
        bandeja.marcar(oc_id, estado)
    elif estado == "vencida":
        cierre.cerrar(oc_id, "vencida", "vencio antes de responderla")
    else:
        cierre.cerrar(oc_id, "descartada", f"estado remoto inesperado: {estado}")


def reintentar_decisiones() -> None:
    for o in bandeja.en_estado("aceptando", "rechazando"):
        try:
            conciliar_decision(o.id)
        except Exception as e:
            log.exception("OC %s: no se pudo conciliar la decision", o.id)
            bandeja.registrar_error(o.id, repr(e))
```

- [ ] **Paso 4: Correr la prueba y ver que pasa**

Run: `python -m unittest tests/test_pedidos_db.py -v`
Esperado: todo OK.

- [ ] **Paso 5: Commit (con OK de Mario)**

```bash
git add app/pedidos/cierre.py app/pedidos/procesador.py tests/test_pedidos_db.py
git commit -m "Decidir cada orden de compra y avisar la decision de forma recuperable."
```

---

### Tarea 7: Despachador

**Archivos:**
- Crear: `app/pedidos/despachador.py`
- Prueba: `tests/test_pedidos_db.py`

**Interfaces:**
- Consume: `bandeja.aceptadas_por_vencimiento`, `procesador.asegurar_venta`,
  `custodia.*_de_venta`, `custodia.espacio_de`, `operaciones.mover`, `farma_client.dispatch`,
  `ordenes_client.obtener`.
- Produce: `despachador.asignar_pendientes() -> int`, `despachador.despachar_pendientes(maximo=5) -> int`.

- [ ] **Paso 1: Escribir la prueba que falla**

Agregar a `tests/test_pedidos_db.py`, dentro del bloque `if TEST_DB:`:

```python
    from app.pedidos import despachador
```

agregar este método a `BaseDB` (lo usan el despachador y el conciliador):

```python
    def aceptada(self, cantidad: int, vence_en: timedelta = timedelta(hours=2)) -> str:
        """Una OC ya aceptada en el sistema de ordenes, con su Venta y sin unidades."""
        oc_id = _oc_id()
        bandeja.recibir(oc_id, "pubsub", "msg")
        bandeja.guardar_detalle(oc_id, self.oc_remota(oc_id, cantidad=cantidad, vence_en=vence_en))
        bandeja.reclamar(oc_id, "nueva", "aceptada", {"precio_unitario": 1500})
        procesador.asegurar_venta(oc_id)
        return oc_id
```

y la clase:

```python
@unittest.skipUnless(TEST_DB, "TEST_DATABASE_URL no definido")
class DespachadorTest(BaseDB):
    def _sin_red(self):
        mover = patch.object(despachador, "mover", side_effect=lambda uid, hacia:
                             custodia.registrar_traslado(uid, hacia))
        dispatch = patch.object(despachador.farma_client, "dispatch", return_value=None)
        return mover, dispatch

    def test_asigna_unidades_nuevas_a_la_que_vence_primero(self):
        tarde = self.aceptada(1, vence_en=timedelta(hours=2))
        pronto = self.aceptada(1, vence_en=timedelta(hours=1))
        self.sembrar(1)
        self.assertEqual(despachador.asignar_pendientes(), 1)
        self.assertEqual(custodia.unidades_de_venta(bandeja.get(pronto).venta_id), 1)
        self.assertEqual(custodia.unidades_de_venta(bandeja.get(tarde).venta_id), 0)

    def test_despacha_y_marca_cumplida(self):
        oc_id = self.aceptada(2)
        self.sembrar(2)
        despachador.asignar_pendientes()
        mover, dispatch = self._sin_red()
        with mover as m, dispatch as d:
            self.assertEqual(despachador.despachar_pendientes(), 2)
        self.assertEqual(d.call_count, 2)
        self.assertTrue(all(c.args[1] == "checkOut" for c in m.call_args_list))
        self.assertEqual(bandeja.get(oc_id).estado, "cumplida")

    def test_unidad_ya_despachada_no_se_despacha_dos_veces(self):
        oc_id = self.aceptada(1)
        self.sembrar(1)
        despachador.asignar_pendientes()
        mover, dispatch = self._sin_red()
        with mover, dispatch as d:
            despachador.despachar_pendientes()
            despachador.despachar_pendientes()
        self.assertEqual(d.call_count, 1)

    def test_404_tras_caida_se_confirma_si_el_sistema_ya_lo_conto(self):
        oc_id = self.aceptada(1)
        self.sembrar(1)
        despachador.asignar_pendientes()
        mover, dispatch = self._sin_red()
        with mover, dispatch as d, patch.object(despachador, "ordenes_client") as api:
            d.side_effect = _http_error(404)
            api.obtener.return_value = self.oc_remota(oc_id, estado="cumplida", despachado=1)
            despachador.despachar_pendientes()
        self.assertEqual(bandeja.get(oc_id).estado, "cumplida")

    def test_error_de_dispatch_deja_la_unidad_pendiente(self):
        oc_id = self.aceptada(1)
        self.sembrar(1)
        despachador.asignar_pendientes()
        mover, dispatch = self._sin_red()
        with mover, dispatch as d:
            d.side_effect = _http_error(500)
            self.assertEqual(despachador.despachar_pendientes(), 0)
        venta_id = bandeja.get(oc_id).venta_id
        self.assertEqual(len(custodia.pendientes_de_venta(venta_id)), 1)
        self.assertEqual(bandeja.get(oc_id).estado, "aceptada")
```

- [ ] **Paso 2: Correrla y ver que falla**

Run: `python -m unittest tests/test_pedidos_db.py -v`
Esperado: FALLA con `ImportError: cannot import name 'despachador'`.

- [ ] **Paso 3: Implementar**

`app/pedidos/despachador.py`:

```python
"""Despachador de OC: asigna unidades a las OC aceptadas y las despacha.

Por cada unidad: moverla a checkOut, POST /farma-central/dispatch y confirmar
en custodia. Si falla a mitad de camino, la unidad queda pendiente y se
reintenta en el proximo tick. VentaUnidad.unidad_id es unico: una unidad no
puede quedar en dos OC ni despacharse dos veces.
"""
import logging

import httpx

from app import custodia, farma_client, ordenes_client, stock
from app.operaciones import mover
from app.pedidos import bandeja, procesador

log = logging.getLogger("pedidos")

# Cada despacho son 2 requests a Farma Central (mover + dispatch). El limite
# de 250/min es por grupo y lo comparten el worker de frio y el reponedor.
MAX_DESPACHOS_POR_TICK = 5


def asignar_pendientes() -> int:
    """Asigna unidades que ya existen a OC aceptadas que aun no las tienen,
    empezando por la que vence primero."""
    asignadas = 0
    with stock.candado_stock(esperar_s=procesador.ESPERA_CANDADO_S):
        for o in bandeja.aceptadas_por_vencimiento():
            venta_id = o.venta_id or procesador.asegurar_venta(o.id)
            faltan = (o.cantidad or 0) - custodia.unidades_de_venta(venta_id)
            if faltan <= 0:
                continue
            ids = [u.id for u in custodia.unidades_disponibles(o.sku)][:faltan]
            if ids:
                custodia.asignar_unidades_a_venta(venta_id, ids)
                asignadas += len(ids)
                log.info("OC %s: %d unidades asignadas", o.id, len(ids))
    return asignadas


def despachar_pendientes(maximo: int = MAX_DESPACHOS_POR_TICK) -> int:
    hechos = 0
    for o in bandeja.aceptadas_por_vencimiento():
        if o.venta_id is None:
            continue
        for unidad_id in custodia.pendientes_de_venta(o.venta_id):
            if hechos >= maximo:
                return hechos
            if _despachar_unidad(unidad_id, o):
                hechos += 1
        if custodia.despachadas_de_venta(o.venta_id) >= (o.cantidad or 0):
            bandeja.marcar(o.id, "cumplida")
            log.info("OC %s cumplida: %d unidades despachadas", o.id, o.cantidad)
    return hechos


def _despachar_unidad(unidad_id: str, o) -> bool:
    try:
        if custodia.espacio_de(unidad_id) != "checkOut":
            mover(unidad_id, "checkOut")
        farma_client.dispatch(unidad_id, o.id)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404 and _ya_salio(o):
            log.warning("OC %s: %s ya habia salido (caida antes de anotarlo)", o.id, unidad_id)
        else:
            log.error("OC %s: no se pudo despachar %s: %s", o.id, unidad_id, e.response.text)
            bandeja.registrar_error(o.id, f"dispatch {unidad_id}: {e.response.status_code}")
            return False
    custodia.confirmar_despacho(unidad_id)
    log.info("OC %s: despachada %s", o.id, unidad_id)
    return True


def _ya_salio(o) -> bool:
    """Un 404 dice que la unidad ya no esta. Si el sistema de ordenes cuenta mas
    despachos que custodia, el despacho anterior si llego y solo falto anotarlo."""
    remoto = ordenes_client.obtener(o.id)
    bandeja.guardar_detalle(o.id, remoto)
    return int(remoto.get("despachado") or 0) > custodia.despachadas_de_venta(o.venta_id)
```

- [ ] **Paso 4: Correr la prueba y ver que pasa**

Run: `python -m unittest tests/test_pedidos_db.py -v`
Esperado: todo OK.

- [ ] **Paso 5: Commit (con OK de Mario)**

```bash
git add app/pedidos/despachador.py tests/test_pedidos_db.py
git commit -m "Despachar las ordenes de compra aceptadas a Farma Central."
```

---

### Tarea 8: Conciliador

**Archivos:**
- Crear: `app/pedidos/conciliador.py`
- Prueba: `tests/test_pedidos_db.py`

**Interfaces:**
- Consume: `bandeja.en_estado`, `bandeja.cumplidas_sin_confirmar`, `bandeja.guardar_detalle`,
  `cierre.cerrar`, `ordenes_client.obtener`.
- Produce: `conciliador.conciliar() -> int`

- [ ] **Paso 1: Escribir la prueba que falla**

Agregar a `tests/test_pedidos_db.py`, dentro del bloque `if TEST_DB:`:

```python
    from app.pedidos import conciliador
```

y la clase:

```python
@unittest.skipUnless(TEST_DB, "TEST_DATABASE_URL no definido")
class ConciliadorTest(BaseDB):
    def test_vencida_en_el_sistema_libera_la_reserva(self):
        oc_id = self.aceptada(1)
        self.sembrar(1)
        despachador.asignar_pendientes()
        self.assertEqual(custodia.stock_disponible(self.sku), 0)
        with patch.object(conciliador, "ordenes_client") as api:
            api.obtener.return_value = self.oc_remota(oc_id, estado="vencida")
            conciliador.conciliar()
        self.assertEqual(bandeja.get(oc_id).estado, "vencida")
        self.assertEqual(custodia.stock_disponible(self.sku), 1)

    def test_cumplida_local_se_confirma_con_el_sistema(self):
        oc_id = self.aceptada(1)
        bandeja.marcar(oc_id, "cumplida")
        with patch.object(conciliador, "ordenes_client") as api:
            api.obtener.return_value = self.oc_remota(oc_id, estado="cumplida", despachado=1)
            conciliador.conciliar()
        self.assertEqual(bandeja.get(oc_id).estado_remoto, "cumplida")

    def test_sigue_aceptada_no_cambia_nada(self):
        oc_id = self.aceptada(1)
        with patch.object(conciliador, "ordenes_client") as api:
            api.obtener.return_value = self.oc_remota(oc_id, estado="aceptada")
            conciliador.conciliar()
        self.assertEqual(bandeja.get(oc_id).estado, "aceptada")
```

- [ ] **Paso 2: Correrla y ver que falla**

Run: `python -m unittest tests/test_pedidos_db.py -v`
Esperado: FALLA con `ImportError: cannot import name 'conciliador'`.

- [ ] **Paso 3: Implementar**

`app/pedidos/conciliador.py`:

```python
"""Conciliador: mantiene la base al dia con el sistema de ordenes (la fuente oficial).

Cada ~5 minutos consulta las OC que no estan cerradas: si el sistema dice que
vencio, se libera lo reservado; si dice cumplida, se anota.
"""
import logging

from app import custodia, ordenes_client
from app.pedidos import bandeja, cierre

log = logging.getLogger("pedidos")


def conciliar() -> int:
    revisadas = 0
    for o in bandeja.en_estado("aceptada") + bandeja.cumplidas_sin_confirmar():
        try:
            _conciliar_una(o)
            revisadas += 1
        except Exception as e:
            log.exception("OC %s: no se pudo conciliar", o.id)
            bandeja.registrar_error(o.id, repr(e))
    return revisadas


def _conciliar_una(o) -> None:
    remoto = ordenes_client.obtener(o.id)
    bandeja.guardar_detalle(o.id, remoto)
    estado = remoto.get("estado")
    if estado == "aceptada":
        return
    if estado == "cumplida":
        pendientes = custodia.pendientes_de_venta(o.venta_id) if o.venta_id else []
        if pendientes:
            # El sistema ya cuenta la OC completa pero custodia no anoto alguna salida
            log.warning("OC %s cumplida con %d unidades sin confirmar en custodia: %s",
                        o.id, len(pendientes), pendientes)
        bandeja.marcar(o.id, "cumplida")
    elif estado == "vencida":
        cierre.cerrar(o.id, "vencida", "vencio sin completarse")
    else:
        cierre.cerrar(o.id, "descartada", f"estado remoto inesperado: {estado}")
```

- [ ] **Paso 4: Correr la prueba y ver que pasa**

Run: `python -m unittest tests/test_pedidos_db.py -v`
Esperado: todo OK.

- [ ] **Paso 5: Commit (con OK de Mario)**

```bash
git add app/pedidos/conciliador.py tests/test_pedidos_db.py
git commit -m "Conciliar las ordenes de compra con el sistema de ordenes."
```

---

### Tarea 9: Formatos y lector sFTP

**Archivos:**
- Crear: `app/canales/__init__.py` (vacío), `app/canales/formatos.py`, `app/canales/sftp.py`
- Prueba: `tests/test_canales.py`

**Interfaces:**
- Consume: `bandeja.ID_OC`, `bandeja.archivos_no_leidos`, `bandeja.recibir_archivo`.
- Produce: `formatos.parsear_xml(contenido: bytes) -> str`, `formatos.parsear_mensaje(data: bytes, atributos: dict) -> str`,
  `sftp.revisar(sesion=_sesion) -> int`.

- [ ] **Paso 1: Escribir la prueba que falla**

`tests/test_canales.py`:

```python
"""Tests de los lectores de canales (sin red ni Postgres)."""
from __future__ import annotations

import base64
import io
import json
import os
import unittest
from contextlib import contextmanager
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://farma:x@localhost/farma")

from app.canales import formatos, sftp  # noqa: E402

OC = "64abc123def456789012abcd"
XML = f"""<?xml version="1.0" encoding="UTF-8"?>
<order><id>{OC}</id><sku>KIT-RESP-ADULTO</sku><qty>2</qty></order>""".encode()


class FormatosTest(unittest.TestCase):
    def test_xml_del_anexo(self):
        self.assertEqual(formatos.parsear_xml(XML), OC)

    def test_xml_mal_formado(self):
        with self.assertRaises(ValueError):
            formatos.parsear_xml(b"<order><id>")

    def test_xml_con_id_invalido(self):
        with self.assertRaises(ValueError):
            formatos.parsear_xml(b"<order><id>no-es-un-id</id></order>")

    def test_xml_con_entidades_se_rechaza(self):
        bomba = b'<?xml version="1.0"?><!DOCTYPE a [<!ENTITY b "x">]><order><id>&b;</id></order>'
        with self.assertRaises(ValueError):
            formatos.parsear_xml(bomba)

    def test_mensaje_json_xml_o_id_solo(self):
        for data in (json.dumps({"id": OC}).encode(), json.dumps({"orderId": OC}).encode(),
                     XML, OC.encode()):
            with self.subTest(data=data[:20]):
                self.assertEqual(formatos.parsear_mensaje(data, {}), OC)

    def test_mensaje_con_id_en_atributos(self):
        self.assertEqual(formatos.parsear_mensaje(b"", {"orderId": OC}), OC)

    def test_mensaje_sin_id(self):
        with self.assertRaises(ValueError):
            formatos.parsear_mensaje(b'{"hola": 1}', {})


class FakeAttr:
    def __init__(self, nombre):
        self.filename = nombre
        self.st_mode = 0o100644  # archivo regular


class FakeSftp:
    def __init__(self, archivos: dict[str, bytes]):
        self.archivos = archivos
        self.abiertos: list[str] = []

    def listdir_attr(self, ruta):
        return [FakeAttr(n) for n in self.archivos]

    def open(self, ruta, modo):
        nombre = ruta.rsplit("/", 1)[-1]
        self.abiertos.append(nombre)
        return io.BytesIO(self.archivos[nombre])


class SftpTest(unittest.TestCase):
    def _sesion(self, fake, cerrada: list):
        @contextmanager
        def sesion():
            try:
                yield fake
            finally:
                cerrada.append(True)
        return sesion

    def test_lee_solo_los_nuevos_y_cierra_la_sesion(self):
        fake = FakeSftp({"a.xml": XML, "b.xml": XML})
        cerrada: list = []
        with patch.object(sftp.bandeja, "archivos_no_leidos", return_value=["b.xml"]), \
             patch.object(sftp.bandeja, "recibir_archivo", return_value=True) as recibir:
            self.assertEqual(sftp.revisar(sesion=self._sesion(fake, cerrada)), 1)
        self.assertEqual(fake.abiertos, ["b.xml"])
        recibir.assert_called_once_with("b.xml", OC)
        self.assertEqual(cerrada, [True])

    def test_archivo_invalido_se_anota_con_su_error(self):
        fake = FakeSftp({"malo.xml": b"<nada"})
        with patch.object(sftp.bandeja, "archivos_no_leidos", return_value=["malo.xml"]), \
             patch.object(sftp.bandeja, "recibir_archivo", return_value=False) as recibir:
            sftp.revisar(sesion=self._sesion(fake, []))
        nombre, oc_id, error = recibir.call_args.args
        self.assertEqual((nombre, oc_id), ("malo.xml", None))
        self.assertIn("XML", error)

    def test_error_al_leer_igual_cierra_la_sesion(self):
        fake = FakeSftp({"a.xml": XML})
        fake.open = lambda *a: (_ for _ in ()).throw(OSError("se corto"))
        cerrada: list = []
        with patch.object(sftp.bandeja, "archivos_no_leidos", return_value=["a.xml"]):
            with self.assertRaises(OSError):
                sftp.revisar(sesion=self._sesion(fake, cerrada))
        self.assertEqual(cerrada, [True])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Paso 2: Correrla y ver que falla**

Run: `python -m unittest tests/test_canales.py -v`
Esperado: FALLA con `ModuleNotFoundError: No module named 'app.canales'`.

- [ ] **Paso 3: Implementar**

`app/canales/__init__.py`: archivo vacío.

`app/canales/formatos.py`:

```python
"""Leer el id de OC desde un archivo XML del sFTP o un mensaje de Pub/Sub.

El XML se lee con defusedxml: rechaza DTD y entidades, asi un archivo
malicioso no puede reventar la memoria del proceso.
"""
import json

from defusedxml import DefusedXmlException
from defusedxml.ElementTree import ParseError, fromstring

from app.pedidos.bandeja import ID_OC


def parsear_xml(contenido: bytes) -> str:
    """Formato del Anexo 1: <order><id>..</id><sku>..</sku><qty>..</qty></order>."""
    try:
        raiz = fromstring(contenido, forbid_dtd=True)
    except (ParseError, DefusedXmlException) as e:
        raise ValueError(f"XML invalido: {e}") from e
    if raiz.tag != "order":
        raise ValueError(f"XML sin <order> (raiz: {raiz.tag})")
    oc_id = (raiz.findtext("id") or "").strip()
    if not ID_OC.match(oc_id):
        raise ValueError(f"id de OC invalido en el XML: {oc_id!r}")
    return oc_id


def parsear_mensaje(data: bytes, atributos: dict) -> str:
    """El enunciado solo dice que el mensaje trae el id de la OC. Se aceptan
    JSON ({"id"} u {"orderId"}), el mismo XML del sFTP, el id solo, o el id en
    los atributos del mensaje. Cualquier otra cosa es un error con el contenido."""
    texto = data.decode("utf-8", errors="replace").strip()
    candidatos: list[str] = []
    if texto.startswith("{"):
        try:
            obj = json.loads(texto)
        except json.JSONDecodeError as e:
            raise ValueError(f"JSON invalido: {e}") from e
        candidatos += [str(obj[k]) for k in ("id", "orderId", "idOrden", "_id") if obj.get(k)]
    elif texto.startswith("<"):
        candidatos.append(parsear_xml(data))
    elif texto:
        candidatos.append(texto)
    candidatos += [str(atributos[k]) for k in ("id", "orderId") if atributos.get(k)]
    for c in candidatos:
        if ID_OC.match(c):
            return c
    raise ValueError(f"mensaje sin id de OC reconocible: {texto[:200]!r}")
```

`app/canales/sftp.py`:

```python
"""Lector de la casilla sFTP (Anexo 1 del enunciado E2).

El servidor no avisa: se revisa cada minuto. Cada revision abre una sesion y
la cierra siempre, tambien ante un error: las sesiones que quedan abiertas
ocupan cupos y al llegar al limite el servidor bloquea la casilla.

La llave del servidor se verifica contra keys/known_hosts (RejectPolicy):
si cambia, no se conecta.
"""
import logging
import posixpath
import stat
from contextlib import contextmanager

import paramiko

from app.canales import formatos
from app.config import (SFTP_DIR, SFTP_HOST, SFTP_KNOWN_HOSTS, SFTP_PASSWORD, SFTP_PORT,
                        SFTP_USER)
from app.pedidos import bandeja

log = logging.getLogger("sftp")

MAX_BYTES = 64 * 1024  # una OC son unas pocas lineas de XML


@contextmanager
def _sesion():
    cliente = paramiko.SSHClient()
    try:
        cliente.load_host_keys(SFTP_KNOWN_HOSTS)
        cliente.set_missing_host_key_policy(paramiko.RejectPolicy())
        cliente.connect(SFTP_HOST, port=SFTP_PORT, username=SFTP_USER, password=SFTP_PASSWORD,
                        timeout=15, banner_timeout=15, auth_timeout=15,
                        allow_agent=False, look_for_keys=False)
        canal = cliente.open_sftp()
        try:
            yield canal
        finally:
            canal.close()
    finally:
        cliente.close()


def revisar(sesion=_sesion) -> int:
    """Lee los archivos nuevos de la casilla. Devuelve cuantas OC nuevas anoto."""
    nuevas = 0
    with sesion() as canal:
        nombres = [a.filename for a in canal.listdir_attr(SFTP_DIR) if stat.S_ISREG(a.st_mode)]
        for nombre in bandeja.archivos_no_leidos(nombres):
            with canal.open(posixpath.join(SFTP_DIR, nombre), "rb") as f:
                contenido = f.read(MAX_BYTES + 1)
            if len(contenido) > MAX_BYTES:
                bandeja.recibir_archivo(nombre, None, "archivo demasiado grande")
                log.error("Archivo %s demasiado grande: no se procesa", nombre)
                continue
            try:
                oc_id = formatos.parsear_xml(contenido)
            except ValueError as e:
                bandeja.recibir_archivo(nombre, None, str(e))
                log.error("Archivo %s invalido: %s", nombre, e)
                continue
            if bandeja.recibir_archivo(nombre, oc_id):
                nuevas += 1
                log.info("OC %s recibida por sFTP (%s)", oc_id, nombre)
    return nuevas
```

- [ ] **Paso 4: Correr la prueba y ver que pasa**

Run: `python -m unittest tests/test_canales.py -v`
Esperado: todo OK.

- [ ] **Paso 5: Commit (con OK de Mario)**

```bash
git add app/canales/__init__.py app/canales/formatos.py app/canales/sftp.py tests/test_canales.py
git commit -m "Leer ordenes de compra desde la casilla sFTP."
```

---

### Tarea 10: Lector Pub/Sub y creación de la suscripción

**Archivos:**
- Crear: `app/canales/pubsub.py`, `app/scripts/crear_suscripcion.py`
- Prueba: `tests/test_canales.py`

**Interfaces:**
- Consume: `formatos.parsear_mensaje`, `bandeja.recibir`, `ordenes_client.pubsub_key`.
- Produce: `pubsub.revisar(max_mensajes=20) -> int`, `pubsub.habilitado() -> bool`.

- [ ] **Paso 1: Escribir la prueba que falla**

Agregar a `tests/test_canales.py`, debajo de los imports del inicio:

```python
from app.canales import pubsub  # noqa: E402
```

y la clase:

```python
def _msg(ack: str, data: bytes, mid: str = "m1") -> dict:
    return {"ackId": ack, "message": {"messageId": mid, "attributes": {},
                                      "data": base64.b64encode(data).decode()}}


class PubsubTest(unittest.TestCase):
    def setUp(self):
        p = patch.object(pubsub, "_token", return_value="t")
        p.start()
        self.addCleanup(p.stop)

    def test_ack_solo_despues_de_guardar(self):
        orden: list[str] = []
        recibidos = {"receivedMessages": [_msg("a1", OC.encode())]}

        def post(ruta, cuerpo, timeout=30):
            orden.append(ruta.rsplit(":", 1)[-1])
            return recibidos if ruta.endswith(":pull") else {}

        with patch.object(pubsub, "_post", side_effect=post), \
             patch.object(pubsub.bandeja, "recibir",
                          side_effect=lambda *a: orden.append("guardar") or True):
            self.assertEqual(pubsub.revisar(), 1)
        self.assertEqual(orden, ["pull", "guardar", "acknowledge"])

    def test_si_falla_al_guardar_no_hace_ack(self):
        recibidos = {"receivedMessages": [_msg("a1", OC.encode())]}
        with patch.object(pubsub, "_post", return_value=recibidos) as post, \
             patch.object(pubsub.bandeja, "recibir", side_effect=RuntimeError("db caida")):
            with self.assertRaises(RuntimeError):
                pubsub.revisar()
        self.assertEqual(post.call_count, 1)  # solo el pull

    def test_mensaje_ilegible_se_confirma_para_no_repetirlo(self):
        recibidos = {"receivedMessages": [_msg("a1", b'{"x": 1}')]}
        llamadas: list = []
        with patch.object(pubsub, "_post", side_effect=lambda r, c, timeout=30:
                          llamadas.append((r, c)) or (recibidos if r.endswith(":pull") else {})):
            self.assertEqual(pubsub.revisar(), 0)
        self.assertEqual(llamadas[-1][1], {"ackIds": ["a1"]})

    def test_sin_mensajes_no_hace_ack(self):
        with patch.object(pubsub, "_post", return_value={}) as post:
            self.assertEqual(pubsub.revisar(), 0)
        self.assertEqual(post.call_count, 1)
```

- [ ] **Paso 2: Correrla y ver que falla**

Run: `python -m unittest tests/test_canales.py -v`
Esperado: FALLA con `ImportError: cannot import name 'pubsub'`.

- [ ] **Paso 3: Implementar**

`app/canales/pubsub.py`:

```python
"""Lector de Pub/Sub por suscripcion pull (API REST de Google).

Pull en vez de push: si el servidor esta caido, los mensajes esperan en
Google. El ack se envia recien cuando la OC quedo guardada en la base; si
algo falla antes, Google reenvia el mensaje y la bandeja lo descarta por
clave primaria.

Un mensaje que no se puede leer se registra en el log con su contenido y se
confirma igual: reenviarlo para siempre no lo arregla y bloquearia la cola.
"""
import base64
import logging
from pathlib import Path

import google.auth.transport.requests
import httpx
from google.oauth2 import service_account

from app.canales import formatos
from app.config import PUBSUB_KEY_FILE, PUBSUB_SUBSCRIPTION
from app.pedidos import bandeja

log = logging.getLogger("pubsub")

API = "https://pubsub.googleapis.com/v1"
SCOPES = ["https://www.googleapis.com/auth/pubsub"]

_credenciales = None


def habilitado() -> bool:
    return Path(PUBSUB_KEY_FILE).exists()


def _token() -> str:
    global _credenciales
    if _credenciales is None:
        _credenciales = service_account.Credentials.from_service_account_file(
            PUBSUB_KEY_FILE, scopes=SCOPES)
    if not _credenciales.valid:
        _credenciales.refresh(google.auth.transport.requests.Request())
    return _credenciales.token


def _post(ruta: str, cuerpo: dict, timeout: float = 30) -> dict:
    r = httpx.post(f"{API}/{ruta}", json=cuerpo, timeout=timeout,
                   headers={"Authorization": f"Bearer {_token()}"})
    r.raise_for_status()
    return r.json() if r.content else {}


def revisar(max_mensajes: int = 20) -> int:
    """Trae mensajes pendientes, anota sus OC y los confirma. Devuelve cuantas OC nuevas."""
    respuesta = _post(f"{PUBSUB_SUBSCRIPTION}:pull", {"maxMessages": max_mensajes}, timeout=40)
    nuevas = 0
    ack_ids: list[str] = []
    for recibido in respuesta.get("receivedMessages", []):
        mensaje = recibido["message"]
        data = base64.b64decode(mensaje.get("data", ""))
        try:
            oc_id = formatos.parsear_mensaje(data, mensaje.get("attributes") or {})
        except ValueError as e:
            log.error("Mensaje %s ilegible, se confirma sin procesar: %s",
                      mensaje.get("messageId"), e)
            ack_ids.append(recibido["ackId"])
            continue
        if bandeja.recibir(oc_id, "pubsub", mensaje.get("messageId")):
            nuevas += 1
            log.info("OC %s recibida por Pub/Sub (%s)", oc_id, mensaje.get("messageId"))
        ack_ids.append(recibido["ackId"])
    if ack_ids:
        _post(f"{PUBSUB_SUBSCRIPTION}:acknowledge", {"ackIds": ack_ids})
    return nuevas
```

`app/scripts/crear_suscripcion.py`:

```python
"""Crea la suscripcion pull del grupo. Se corre una vez por ambiente.

  docker compose run --rm --no-deps -v "$PWD/keys:/keys-rw" pedidos \
      python -m app.scripts.crear_suscripcion /keys-rw/pubsub-dev.json

Guarda la llave de la cuenta de servicio en la ruta indicada (permisos 600)
y crea la suscripcion. Si ya existe, no hace nada.
"""
import json
import os
import sys
from pathlib import Path

import google.auth.transport.requests
import httpx
from google.oauth2 import service_account

from app import ordenes_client
from app.canales.pubsub import API, SCOPES
from app.config import PUBSUB_SUBSCRIPTION, PUBSUB_TOPIC


def main(salida: str) -> None:
    llave = ordenes_client.pubsub_key()
    ruta = Path(salida)
    ruta.write_text(json.dumps(llave))
    os.chmod(ruta, 0o600)
    print(f"Llave guardada en {ruta}")

    cred = service_account.Credentials.from_service_account_info(llave, scopes=SCOPES)
    cred.refresh(google.auth.transport.requests.Request())
    r = httpx.put(
        f"{API}/{PUBSUB_SUBSCRIPTION}",
        json={"topic": PUBSUB_TOPIC, "ackDeadlineSeconds": 60,
              "messageRetentionDuration": "604800s"},
        headers={"Authorization": f"Bearer {cred.token}"},
        timeout=30,
    )
    if r.status_code == 409:
        print(f"La suscripcion {PUBSUB_SUBSCRIPTION} ya existia")
        return
    r.raise_for_status()
    print(f"Suscripcion {PUBSUB_SUBSCRIPTION} creada sobre {PUBSUB_TOPIC}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Uso: python -m app.scripts.crear_suscripcion <ruta de la llave>")
    main(sys.argv[1])
```

- [ ] **Paso 4: Correr la prueba y ver que pasa**

Run: `python -m unittest tests/test_canales.py -v`
Esperado: todo OK.

- [ ] **Paso 5: Commit (con OK de Mario)**

```bash
git add app/canales/pubsub.py app/scripts/crear_suscripcion.py tests/test_canales.py
git commit -m "Leer ordenes de compra desde Pub/Sub con suscripcion pull."
```

---

### Tarea 11: Reposición automática de kits

**Archivos:**
- Modificar: `app/produccion.py`
- Crear: `app/reposicion.py`
- Prueba: `tests/test_reposicion.py`

**Interfaces:**
- Consume: `stock.minimo`, `stock.comprometido`, `custodia.stock_disponible`, `custodia.en_camino`, `operaciones.catalogo`.
- Produce:
  - `produccion.ProduccionOcupada(RuntimeError)`
  - `produccion.una_vuelta(objetivos: dict[str, int], tanda: int = 10, estado: dict | None = None) -> dict[str, int]`
  - `produccion.intentar_vuelta(objetivos, estado) -> dict[str, int] | None`
  - `reposicion.faltantes() -> dict[str, int]`

- [ ] **Paso 1: Escribir la prueba que falla**

`tests/test_reposicion.py`:

```python
"""Tests de la reposicion automatica de kits (sin red ni Postgres)."""
from __future__ import annotations

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://farma:x@localhost/farma")

from app import produccion, reposicion  # noqa: E402

CATALOGO = {"KIT-A": {"sellable": True}, "KIT-B": {"sellable": True},
            "API-X": {"sellable": False}}


class FaltantesTest(unittest.TestCase):
    def _faltantes(self, stock, en_camino, comprometido, minimo=3):
        with patch.object(reposicion, "catalogo", return_value=CATALOGO), \
             patch.object(reposicion.stock, "minimo", return_value=minimo), \
             patch.object(reposicion.stock, "comprometido", side_effect=comprometido.get), \
             patch.object(reposicion.custodia, "stock_disponible", side_effect=stock.get), \
             patch.object(reposicion.custodia, "en_camino", side_effect=en_camino.get):
            return reposicion.faltantes()

    def test_repone_hasta_el_minimo_mas_lo_comprometido(self):
        r = self._faltantes(stock={"KIT-A": 1, "KIT-B": 3}, en_camino={"KIT-A": 0, "KIT-B": 0},
                            comprometido={"KIT-A": 2, "KIT-B": 0})
        self.assertEqual(r, {"KIT-A": 4})  # 3 + 2 - 1; KIT-B ya esta en el minimo

    def test_descuenta_lo_que_viene_en_camino(self):
        r = self._faltantes(stock={"KIT-A": 0, "KIT-B": 3}, en_camino={"KIT-A": 2, "KIT-B": 0},
                            comprometido={"KIT-A": 0, "KIT-B": 0})
        self.assertEqual(r, {"KIT-A": 1})

    def test_solo_kits(self):
        r = self._faltantes(stock={"KIT-A": 3, "KIT-B": 3}, en_camino={"KIT-A": 0, "KIT-B": 0},
                            comprometido={"KIT-A": 0, "KIT-B": 0})
        self.assertEqual(r, {})


class IntentarVueltaTest(unittest.TestCase):
    def test_si_hay_produccion_manual_devuelve_none(self):
        def ocupado():
            raise produccion.ProduccionOcupada("otro proceso")
        with patch.object(produccion, "_candado", side_effect=ocupado):
            self.assertIsNone(produccion.intentar_vuelta({"KIT-A": 1}, {}))

    def test_un_error_dentro_de_la_vuelta_no_se_confunde_con_candado_ocupado(self):
        from contextlib import nullcontext
        with patch.object(produccion, "_candado", return_value=nullcontext()), \
             patch.object(produccion, "una_vuelta", side_effect=RuntimeError("PoW fallo")):
            with self.assertRaises(RuntimeError):
                produccion.intentar_vuelta({"KIT-A": 1}, {})


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Paso 2: Correrla y ver que falla**

Run: `python -m unittest tests/test_reposicion.py -v`
Esperado: FALLA con `ImportError: cannot import name 'reposicion'`.

- [ ] **Paso 3: Implementar**

`app/produccion.py`:

1. Agregar, después de `LOCK_PRODUCCION = 4_000_002`:

```python
class ProduccionOcupada(RuntimeError):
    """Otro proceso tiene el candado de produccion."""
```

2. En `_candado`, cambiar `raise RuntimeError("Ya hay otro proceso de produccion corriendo")`
   por `raise ProduccionOcupada("Ya hay otro proceso de produccion corriendo")`.

3. Agregar antes de `def producir`:

```python
def una_vuelta(objetivos: dict[str, int], tanda: int = 10,
               estado: dict | None = None) -> dict[str, int]:
    """Una vuelta del orquestador. objetivos = {kit: cuantos faltan pedir}.
    Hay que llamarla con el candado tomado. Devuelve cuantos kits se pidieron
    en esta vuelta. `estado` guarda entre vueltas el contador del rompe-atascos."""
    estado = estado if estado is not None else {}
    kits = set(objetivos)
    activos = [k for k, n in objetivos.items() if n > 0]  # lista: mantiene el orden
    pedidos: dict[str, int] = defaultdict(int)

    _despejar(kits)
    _liberar_buffer()

    fabricados = 0

    # 1. Kits: armar todo lo que alcance
    for kit in activos:
        n = _intentar_fabricar(kit, objetivos[kit])
        pedidos[kit] += n
        fabricados += n

    # 2. Planificar la tanda actual con lo que queda
    en_tanda = {k: min(tanda, objetivos[k] - pedidos[k])
                for k in activos if objetivos[k] > pedidos[k]}
    plan = planificar(en_tanda)

    # 3. Intermedios (primero los de nivel mas alto)
    sin_espacio = False
    for sku in sorted(plan, key=_profundidad, reverse=True):
        if sku in kits or not catalogo()[sku]["components"]:
            continue
        n = _intentar_fabricar(sku, plan[sku])
        fabricados += n
        if n == 0 and _cuantos_caben(sku, plan[sku]) == 0:
            sin_espacio = True

    # Si acondicionamiento esta lleno de intermedios esperando, se sacan a bodega
    if sin_espacio and not any(_cuantos_alcanzan(k, 1) for k in activos):
        intermedios = {s for s in catalogo() if catalogo()[s]["components"] and s not in kits}
        _despejar(intermedios)

    # Rompe-atascos: si acondicionamiento esta lleno y nada avanza hace varias
    # vueltas (y no hay nada en camino), se vacia completo y se reintenta
    sin_avance = 0 if fabricados else estado.get("sin_avance", 0) + 1
    if sin_espacio and sin_avance >= 6 and custodia.fabricaciones_en_camino() == 0:
        log.warning("Acondicionamiento atascado; lo vacio a la bodega")
        _vaciar_acondicionamiento()
        sin_avance = 0
    estado["sin_avance"] = sin_avance

    # 4. Insumos: comprar lo que falta y no viene en camino
    for sku, cantidad in plan.items():
        if not catalogo()[sku]["components"]:
            try:
                comprar(sku, cantidad)
            except Exception:
                log.exception("Fallo comprando %d x %s", cantidad, sku)

    return dict(pedidos)


def intentar_vuelta(objetivos: dict[str, int], estado: dict) -> dict[str, int] | None:
    """Para el reponedor: una vuelta si nadie mas esta produciendo.
    Devuelve None si el candado esta tomado (p. ej. un producir() manual)."""
    # Solo _candado levanta ProduccionOcupada: un error dentro de la vuelta
    # (p. ej. un PoW que falla) sale como su propia excepcion
    try:
        with _candado():
            return una_vuelta(objetivos, estado=estado)
    except ProduccionOcupada:
        return None
```

4. Reemplazar el cuerpo del `while True:` de `producir()` (desde `_despejar(kits)`
   hasta el `time.sleep(ESPERA)` inclusive) para que use `una_vuelta`:

```python
    with _candado():
        estado: dict = {}
        while True:
            restantes = {k: n - pedidos[k] for k, n in objetivos.items() if n > pedidos[k]}
            if not restantes:
                break
            if time.time() > limite:
                log.error("Se alcanzo el limite de %s horas; quedan %s", max_horas, restantes)
                break

            for kit, n in una_vuelta(restantes, tanda, estado).items():
                pedidos[kit] += n

            avance = ", ".join(f"{k} {pedidos[k]}/{n}" for k, n in objetivos.items())
            log.info("Avance: %s", avance)
            time.sleep(ESPERA)
```

   La variable `sin_avance = 0` que estaba antes del `with` se borra (ahora vive en `estado`).
   La parte que espera los últimos kits y despeja, después del `while`, queda igual.

`app/reposicion.py`:

```python
"""Reposicion automatica: mantiene un minimo de cada kit para cumplir las OC.

faltan = minimo + comprometido - (stock vendible + en camino)

El stock vendible no cuenta lo reservado: al reservar para una OC el stock
baja y el reponedor fabrica mas.
"""
from app import custodia, stock
from app.operaciones import catalogo


def faltantes() -> dict[str, int]:
    faltan: dict[str, int] = {}
    for sku, prod in catalogo().items():
        if not prod.get("sellable"):
            continue
        n = (stock.minimo(sku) + stock.comprometido(sku)
             - custodia.stock_disponible(sku) - custodia.en_camino(sku))
        if n > 0:
            faltan[sku] = n
    return faltan
```

- [ ] **Paso 4: Correr las pruebas y ver que pasan**

Run: `python -m unittest tests/test_reposicion.py tests/test_checkout_pow.py -v`
Esperado: todo OK.
Además, en dev: `docker compose run --rm --build worker python -m app.scripts.producir KIT-RESP-ADULTO 1`
debe seguir funcionando igual que antes (el script usa `producir()`).

- [ ] **Paso 5: Commit (con OK de Mario)**

```bash
git add app/produccion.py app/reposicion.py tests/test_reposicion.py
git commit -m "Reponer kits automaticamente hasta el minimo de cada uno."
```

---

### Tarea 12: Workers, salud y despliegue

**Archivos:**
- Crear: `app/salud.py`, `worker/pedidos.py`, `worker/reponedor.py`
- Modificar: `app/main.py`, `docker-compose.yml`, `README.md`
- Prueba: `tests/test_pedidos_db.py`

**Interfaces:**
- Consume: todo lo anterior.
- Produce: `salud.ok(nombre)`, `salud.fallo(nombre, error)`, `salud.resumen() -> dict`, `GET /api/salud/pedidos`.

- [ ] **Paso 1: Escribir la prueba que falla**

Agregar a `tests/test_pedidos_db.py`, dentro del bloque `if TEST_DB:`:

```python
    from app import salud
```

y la clase:

```python
@unittest.skipUnless(TEST_DB, "TEST_DATABASE_URL no definido")
class SaludTest(BaseDB):
    def test_registra_ok_y_error_por_componente(self):
        nombre = f"test-{self.sufijo}"
        salud.ok(nombre)
        salud.fallo(nombre, "se cayo")
        comp = salud.resumen()["componentes"][nombre]
        self.assertIsNotNone(comp["ultimo_ok"])
        self.assertEqual(comp["ultimo_error"], "se cayo")

    def test_resumen_cuenta_oc_por_estado(self):
        bandeja.recibir(_oc_id(), "sftp", "x.xml")
        self.assertGreaterEqual(salud.resumen()["ordenes"].get("nueva", 0), 1)
```

- [ ] **Paso 2: Correrla y ver que falla**

Run: `python -m unittest tests/test_pedidos_db.py -v`
Esperado: FALLA con `ImportError: cannot import name 'salud'`.

- [ ] **Paso 3: Implementar**

`app/salud.py`:

```python
"""Salud de las piezas de pedidos: ultima ejecucion correcta y ultimo error.

Lo escriben los workers y lo lee GET /api/salud/pedidos. Sirve para notar
durante la evaluacion que un lector dejo de funcionar antes de perder OC.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app import custodia
from app.db import SessionLocal
from app.models import OrdenCompra, SaludComponente
from app.pedidos import bandeja


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def ok(nombre: str) -> None:
    with SessionLocal.begin() as s:
        s.execute(insert(SaludComponente).values(nombre=nombre, ultimo_ok=_ahora())
                  .on_conflict_do_update(index_elements=["nombre"],
                                         set_={"ultimo_ok": _ahora()}))


def fallo(nombre: str, error: str) -> None:
    valores = {"ultimo_error_en": _ahora(), "ultimo_error": error[:2000]}
    with SessionLocal.begin() as s:
        s.execute(insert(SaludComponente).values(nombre=nombre, **valores)
                  .on_conflict_do_update(index_elements=["nombre"], set_=valores))


def resumen() -> dict:
    with SessionLocal() as s:
        componentes = {
            c.nombre: {"ultimo_ok": c.ultimo_ok, "ultimo_error_en": c.ultimo_error_en,
                       "ultimo_error": c.ultimo_error}
            for c in s.scalars(select(SaludComponente))
        }
        pronto = list(s.scalars(
            select(OrdenCompra)
            .where(OrdenCompra.estado == "aceptada",
                   OrdenCompra.vencimiento < _ahora() + timedelta(minutes=30))
            .order_by(OrdenCompra.vencimiento)))
    return {
        "componentes": componentes,
        "ordenes": bandeja.contar_por_estado(),
        "proximas_a_vencer": [
            {"id": o.id, "sku": o.sku, "cantidad": o.cantidad, "vencimiento": o.vencimiento,
             "despachadas": custodia.despachadas_de_venta(o.venta_id) if o.venta_id else 0}
            for o in pronto
        ],
    }
```

`app/main.py`:

1. Cambiar `from app import catalogo, trazabilidad, ventas` por
   `from app import catalogo, salud, trazabilidad, ventas`.
2. Agregar después de `health()`:

```python
@app.get("/api/salud/pedidos")
def api_salud_pedidos():
    return salud.resumen()
```

`worker/pedidos.py`:

```python
"""Worker de pedidos: recibe, decide y despacha las OC de sFTP y Pub/Sub.

Cada TICK_SECONDS:
  Pub/Sub -> procesar OC nuevas -> reintentar decisiones -> asignar -> despachar
Cada SFTP_CADA revisa la casilla sFTP y cada CONCILIAR_CADA concilia con el
sistema de ordenes. Un error en una pieza no detiene a las demas.
"""
import logging
import time

from app import salud
from app.canales import pubsub, sftp
from app.config import SFTP_HOST
from app.pedidos import conciliador, despachador, procesador

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("paramiko").setLevel(logging.WARNING)
log = logging.getLogger("pedidos")

TICK_SECONDS = 10
SFTP_CADA = 60
CONCILIAR_CADA = 300


def _paso(nombre: str, fn) -> None:
    try:
        fn()
        salud.ok(nombre)
    except Exception as e:
        log.exception("Fallo %s", nombre)
        try:
            salud.fallo(nombre, repr(e))
        except Exception:
            log.exception("No se pudo registrar la salud de %s", nombre)


def main():
    log.info("Worker de pedidos iniciado (sFTP: %s, Pub/Sub: %s)",
             bool(SFTP_HOST), pubsub.habilitado())
    ultimo_sftp = ultimo_conciliar = 0.0
    while True:
        ahora = time.monotonic()
        if pubsub.habilitado():
            _paso("pubsub", pubsub.revisar)
        if SFTP_HOST and ahora - ultimo_sftp >= SFTP_CADA:
            _paso("sftp", sftp.revisar)
            ultimo_sftp = ahora
        _paso("procesador", procesador.procesar_nuevas)
        _paso("decisiones", procesador.reintentar_decisiones)
        _paso("asignacion", despachador.asignar_pendientes)
        _paso("despacho", despachador.despachar_pendientes)
        if ahora - ultimo_conciliar >= CONCILIAR_CADA:
            _paso("conciliador", conciliador.conciliar)
            ultimo_conciliar = ahora
        time.sleep(TICK_SECONDS)


if __name__ == "__main__":
    main()
```

`worker/reponedor.py`:

```python
"""Reponedor: mantiene el minimo de cada kit con una vuelta de produccion por tick.

Corre en su propio contenedor porque el PoW de fabricacion usa CPU por
minutos y no debe frenar la atencion de las OC.
"""
import logging
import os
import time

from app import produccion, reposicion, salud

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("reponedor")

TICK_SECONDS = 20


def main():
    os.nice(10)  # prioridad baja frente al portal y a los pedidos
    log.info("Reponedor iniciado")
    estado: dict = {}
    while True:
        try:
            objetivos = reposicion.faltantes()
            if objetivos:
                pedidos = produccion.intentar_vuelta(objetivos, estado)
                if pedidos is None:
                    log.info("Hay una produccion manual en curso; espero")
                elif any(pedidos.values()):
                    log.info("Faltantes %s; pedidos en esta vuelta %s", objetivos, pedidos)
            salud.ok("reponedor")
        except Exception as e:
            log.exception("Error en el reponedor")
            try:
                salud.fallo("reponedor", repr(e))
            except Exception:
                log.exception("No se pudo registrar la salud del reponedor")
        time.sleep(TICK_SECONDS)


if __name__ == "__main__":
    main()
```

`docker-compose.yml`, agregar después del servicio `worker`:

```yaml
  pedidos:
    build: .
    restart: unless-stopped
    command: ["python", "-m", "worker.pedidos"]
    env_file: .env
    volumes:
      - ./keys:/code/keys:ro              # llave de Pub/Sub y known_hosts del sFTP
    depends_on:
      db:
        condition: service_healthy
    mem_limit: 192m

  reponedor:
    build: .
    restart: unless-stopped
    command: ["python", "-m", "worker.reponedor"]
    env_file: .env
    depends_on:
      db:
        condition: service_healthy
    cpus: "1.0"                           # el PoW nunca puede usar mas de 1 de los 2 nucleos
    mem_limit: 256m
```

`README.md`, agregar al final:

````markdown
## Pedidos (Entrega 2)

Dos contenedores nuevos: `pedidos` (sFTP, Pub/Sub, decisión y despacho de OC)
y `reponedor` (mantiene el mínimo de cada kit). Diseño en `docs/04`.

Configuración inicial, una vez por ambiente:

    mkdir -p keys && chmod 700 keys
    ssh-keyscan -p 22 choripan10.ing.uc.cl > keys/known_hosts
    docker compose run --rm --no-deps -v "$PWD/keys:/keys-rw" pedidos \
        python -m app.scripts.crear_suscripcion /keys-rw/pubsub-dev.json
    docker compose run --rm web alembic upgrade head
    docker compose up -d --build

Estado en vivo:

    curl http://127.0.0.1:3000/api/salud/pedidos
    docker compose logs -f pedidos reponedor
````

- [ ] **Paso 4: Correr las pruebas y levantar en local**

Run:
```bash
python -m unittest tests/test_pedidos_db.py -v
python -m unittest tests/test_config_stock.py tests/test_ordenes_client.py tests/test_regla.py tests/test_canales.py tests/test_reposicion.py tests/test_checkout_pow.py -v
docker compose up -d --build && docker compose ps
curl http://127.0.0.1:3000/api/salud/pedidos
```
Esperado: todos los tests OK; los cinco servicios `Up`; el endpoint responde JSON con `componentes`, `ordenes` y `proximas_a_vencer`.

- [ ] **Paso 5: Commit (con OK de Mario)**

```bash
git add app/salud.py app/main.py worker/pedidos.py worker/reponedor.py docker-compose.yml README.md tests/test_pedidos_db.py
git commit -m "Correr pedidos y reponedor en sus propios contenedores con registro de salud."
```

---

### Tarea 13: Verificación en dev (antes del 26 de octubre)

Sin código nuevo: se prueba todo contra el ambiente de desarrollo real.
Cada paso se hace con OK de Mario.

- [ ] **Paso 1:** Conseguir la contraseña sFTP de dev en el portal de grupo y
  completar `SFTP_*` en el `.env` del servidor de dev.
- [ ] **Paso 2:** Generar `keys/known_hosts` y crear la suscripción de dev
  (comandos del README).
- [ ] **Paso 3:** Levantar `pedidos` y `reponedor` con `STOCK_MINIMO_DEFAULT=3`.
- [ ] **Paso 4:** Durante al menos 3 horas, revisar cada 30 min
  `GET /api/salud/pedidos` y los logs. Anotar:
  - OC recibidas por canal y cuántas se aceptaron, rechazaron, cumplieron y vencieron;
  - qué kits se piden más;
  - cuánto tarda en reponerse un kit desde que se reserva;
  - memoria real de cada contenedor (`docker stats --no-stream`).
- [ ] **Paso 5:** Con esos números, ajustar `STOCK_MINIMO` por kit y, si hace
  falta, `MARGEN_DESPACHO_MIN` y los `mem_limit`.
- [ ] **Paso 6:** Confirmar en el portal del grupo que el porcentaje de OC
  cumplidas de dev está sobre 80%.
- [ ] **Paso 7:** Abrir el PR contra `develop` (con OK de Mario).

## Fuera de este plan

- Canal de mensajería (pedidos en lenguaje natural) y retiro de lote: planes aparte, reutilizan
  `ordenes_compra` (canal `mensajeria`), `despachador` y la custodia por OC.
- PRs abiertos #3 (marcar unidades vencidas) y #4 (expirar reservas del
  portal): no bloquean este plan, pero conviene mergearlos antes del 27 de
  octubre. Sin el #3, el stock puede contar unidades que ya vencieron.
