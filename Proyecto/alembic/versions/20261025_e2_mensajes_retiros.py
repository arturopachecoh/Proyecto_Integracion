"""E2: mensajes del canal de mensajeria y retiros de lote

Revision ID: e2c7a3f1b8d2
Revises: e2b5d1c0a9f4
Create Date: 2026-10-25 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e2c7a3f1b8d2"
down_revision: Union[str, None] = "e2b5d1c0a9f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _enum(*valores: str, name: str) -> sa.Enum:
    return sa.Enum(*valores, name=name, native_enum=False, create_constraint=True, length=20)


def _ahora() -> sa.TextClause:
    return sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "mensajes",
        sa.Column("id", sa.String(80), nullable=False),
        sa.Column("remitente", sa.String(160)),
        sa.Column("telefono", sa.String(40)),
        sa.Column("texto", sa.Text(), nullable=False),
        sa.Column("recibido_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("estado", _enum("pendiente", "respondiendo", "pedido", "descartado",
                                  "sin_respuesta", name="estado_mensaje"), nullable=False),
        sa.Column("interpretacion", sa.JSON()),
        sa.Column("decision", sa.JSON()),
        sa.Column("respuesta", sa.JSON()),
        sa.Column("oc_id", sa.String(40)),
        sa.Column("intentos", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ultimo_error", sa.Text()),
        sa.Column("llegado_en", sa.DateTime(timezone=True), nullable=False, server_default=_ahora()),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=False,
                  server_default=_ahora()),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mensajes")),
    )
    op.create_index("ix_mensajes_estado_recibido_en", "mensajes", ["estado", "recibido_en"])

    op.create_table(
        "retiros",
        sa.Column("id", sa.String(60), nullable=False),
        sa.Column("lote", sa.String(60), nullable=False),
        sa.Column("sku", sa.String(50)),
        sa.Column("motivo", sa.Text()),
        sa.Column("emitido_en", sa.DateTime(timezone=True)),
        sa.Column("plazo", sa.DateTime(timezone=True)),
        sa.Column("estado", _enum("pendiente", "reportado", "completo", name="estado_retiro"),
                  nullable=False),
        sa.Column("reporte", sa.JSON()),
        sa.Column("reportado_en", sa.DateTime(timezone=True)),
        sa.Column("completado_en", sa.DateTime(timezone=True)),
        sa.Column("intentos", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ultimo_error", sa.Text()),
        sa.Column("recibido_en", sa.DateTime(timezone=True), nullable=False, server_default=_ahora()),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_retiros")),
    )

    op.create_table(
        "retiro_unidades",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("retiro_id", sa.String(60), nullable=False),
        sa.Column("unidad_id", sa.String(40), nullable=False),
        sa.Column("sku", sa.String(40), nullable=False),
        sa.Column("lote_codigo", sa.String(60), nullable=False),
        sa.Column("espacio_original", sa.String(20)),
        sa.Column("en_cuarentena", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.ForeignKeyConstraint(["retiro_id"], ["retiros.id"],
                                name=op.f("fk_retiro_unidades_retiro_id_retiros")),
        sa.ForeignKeyConstraint(["unidad_id"], ["unidades.id"],
                                name=op.f("fk_retiro_unidades_unidad_id_unidades")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_retiro_unidades")),
        sa.UniqueConstraint("retiro_id", "unidad_id", name="uq_retiro_unidades_retiro_unidad"),
    )
    op.create_index(op.f("ix_retiro_unidades_retiro_id"), "retiro_unidades", ["retiro_id"])

    op.create_table(
        "retiro_notificaciones",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("retiro_id", sa.String(60), nullable=False),
        sa.Column("oc_id", sa.String(40), nullable=False),
        sa.Column("cuerpo", sa.JSON(), nullable=False),
        sa.Column("enviada_en", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["retiro_id"], ["retiros.id"],
                                name=op.f("fk_retiro_notificaciones_retiro_id_retiros")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_retiro_notificaciones")),
        sa.UniqueConstraint("retiro_id", "oc_id", name="uq_retiro_notificaciones_retiro_oc"),
    )
    op.create_index(op.f("ix_retiro_notificaciones_retiro_id"), "retiro_notificaciones",
                    ["retiro_id"])


def downgrade() -> None:
    op.drop_table("retiro_notificaciones")
    op.drop_table("retiro_unidades")
    op.drop_table("retiros")
    op.drop_index("ix_mensajes_estado_recibido_en", table_name="mensajes")
    op.drop_table("mensajes")
