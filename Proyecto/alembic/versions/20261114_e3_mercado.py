"""E3 desarrollador 1: ofertas de mercado y canal `mercado` en las OC.

Revision ID: e3d1a0mercado
Revises: e2c7a3f1b8d2
Create Date: 2026-11-14 22:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e3d1a0mercado"
down_revision: Union[str, None] = "e2c7a3f1b8d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CANALES = ("sftp", "pubsub", "mensajeria", "mercado")


def _enum(*valores: str, name: str) -> sa.Enum:
    return sa.Enum(*valores, name=name, native_enum=False, create_constraint=True, length=20)


def _check_canal(valores: tuple[str, ...]) -> None:
    op.execute("ALTER TABLE ordenes_compra DROP CONSTRAINT IF EXISTS ck_ordenes_compra_canal_oc")
    op.execute("ALTER TABLE ordenes_compra DROP CONSTRAINT IF EXISTS canal_oc")
    op.execute("ALTER TABLE ordenes_compra DROP CONSTRAINT IF EXISTS ck_ordenes_compra_canal")
    lista = ", ".join(f"'{v}'" for v in valores)
    op.execute(
        f"ALTER TABLE ordenes_compra ADD CONSTRAINT ck_ordenes_compra_canal_oc "
        f"CHECK (canal IN ({lista}))"
    )


def upgrade() -> None:
    _check_canal(CANALES)
    op.create_table(
        "ofertas_mercado",
        sa.Column("id", sa.String(80), nullable=False),
        sa.Column("side", _enum("sell", "buy", name="side_oferta"), nullable=False),
        sa.Column("sku", sa.String(40), nullable=False),
        sa.Column("cantidad", sa.Integer(), nullable=False),
        sa.Column("precio_unitario", sa.Integer(), nullable=False),
        sa.Column("estado", _enum(
            "publicando", "abierta", "aceptando", "cerrada", "expirada",
            "cancelada", "cancelando", name="estado_oferta"), nullable=False),
        sa.Column("order_id", sa.String(40)),
        sa.Column("contraparte_grupo", sa.Integer()),
        sa.Column("rol", _enum("vendedor", "comprador", name="rol_oferta"), nullable=False),
        sa.Column("recibidas", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("publicada_en", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("actualizada_en", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ofertas_mercado")),
    )
    op.create_index(op.f("ix_ofertas_mercado_sku"), "ofertas_mercado", ["sku"])
    op.create_index("ix_ofertas_mercado_order_id", "ofertas_mercado", ["order_id"])

    op.create_table(
        "oferta_unidades",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("oferta_id", sa.String(80), nullable=False),
        sa.Column("unidad_id", sa.String(40), nullable=False),
        sa.ForeignKeyConstraint(
            ["oferta_id"], ["ofertas_mercado.id"],
            name=op.f("fk_oferta_unidades_oferta_id_ofertas_mercado"),
            onupdate="CASCADE", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["unidad_id"], ["unidades.id"],
            name=op.f("fk_oferta_unidades_unidad_id_unidades"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_oferta_unidades")),
        sa.UniqueConstraint("unidad_id", name=op.f("uq_oferta_unidades_unidad_id")),
    )
    op.create_index(op.f("ix_oferta_unidades_oferta_id"), "oferta_unidades", ["oferta_id"])

    op.create_table(
        "mercado_faltantes",
        sa.Column("sku", sa.String(40), nullable=False),
        sa.Column("desde", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("sku", name=op.f("pk_mercado_faltantes")),
    )


def downgrade() -> None:
    op.drop_table("mercado_faltantes")
    op.drop_index(op.f("ix_oferta_unidades_oferta_id"), table_name="oferta_unidades")
    op.drop_table("oferta_unidades")
    op.drop_index("ix_ofertas_mercado_order_id", table_name="ofertas_mercado")
    op.drop_index(op.f("ix_ofertas_mercado_sku"), table_name="ofertas_mercado")
    op.drop_table("ofertas_mercado")
    _check_canal(("sftp", "pubsub", "mensajeria"))
