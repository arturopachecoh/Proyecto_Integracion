"""lot_relations, reservada y venta_items

Revision ID: e1a7c0d1e2f3
Revises: b64296a4c597
Create Date: 2026-10-06 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e1a7c0d1e2f3"
down_revision: Union[str, None] = "b64296a4c597"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("ck_unidades_estado_unidad", "unidades", type_="check")
    op.create_check_constraint(
        "ck_unidades_estado_unidad",
        "unidades",
        "estado IN ('en_stock', 'reservada', 'consumida', 'despachada', 'vencida', 'cuarentena')",
    )

    op.create_table(
        "lot_relations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("parent_lote_id", sa.Integer(), nullable=False),
        sa.Column("child_lote_id", sa.Integer(), nullable=False),
        sa.Column("cantidad", sa.Integer(), nullable=False),
        sa.Column("solicitud_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["child_lote_id"], ["lotes.id"],
            name=op.f("fk_lot_relations_child_lote_id_lotes"),
        ),
        sa.ForeignKeyConstraint(
            ["parent_lote_id"], ["lotes.id"],
            name=op.f("fk_lot_relations_parent_lote_id_lotes"),
        ),
        sa.ForeignKeyConstraint(
            ["solicitud_id"], ["solicitudes.id"],
            name=op.f("fk_lot_relations_solicitud_id_solicitudes"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_lot_relations")),
        sa.UniqueConstraint(
            "parent_lote_id", "child_lote_id",
            name="uq_lot_relations_parent_child",
        ),
    )
    op.create_index(op.f("ix_lot_relations_child_lote_id"), "lot_relations", ["child_lote_id"])
    op.create_index(op.f("ix_lot_relations_parent_lote_id"), "lot_relations", ["parent_lote_id"])
    op.create_index(op.f("ix_lot_relations_solicitud_id"), "lot_relations", ["solicitud_id"])

    op.create_table(
        "venta_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("venta_id", sa.Integer(), nullable=False),
        sa.Column("sku", sa.String(length=40), nullable=False),
        sa.Column("cantidad", sa.Integer(), nullable=False),
        sa.Column("precio_unitario", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["venta_id"], ["ventas.id"],
            name=op.f("fk_venta_items_venta_id_ventas"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_venta_items")),
    )
    op.create_index(op.f("ix_venta_items_venta_id"), "venta_items", ["venta_id"])

    op.execute(
        """
        INSERT INTO lot_relations (parent_lote_id, child_lote_id, cantidad, solicitud_id)
        SELECT c.lote_id, l.id, COUNT(*)::int, c.solicitud_id
        FROM consumos c
        INNER JOIN lotes l ON l.solicitud_id = c.solicitud_id
        GROUP BY c.lote_id, l.id, c.solicitud_id
        """
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_venta_items_venta_id"), table_name="venta_items")
    op.drop_table("venta_items")
    op.drop_index(op.f("ix_lot_relations_solicitud_id"), table_name="lot_relations")
    op.drop_index(op.f("ix_lot_relations_parent_lote_id"), table_name="lot_relations")
    op.drop_index(op.f("ix_lot_relations_child_lote_id"), table_name="lot_relations")
    op.drop_table("lot_relations")
    op.drop_constraint("ck_unidades_estado_unidad", "unidades", type_="check")
    op.create_check_constraint(
        "ck_unidades_estado_unidad",
        "unidades",
        "estado IN ('en_stock', 'consumida', 'despachada', 'vencida', 'cuarentena')",
    )
