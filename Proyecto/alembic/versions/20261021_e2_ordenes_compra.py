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
