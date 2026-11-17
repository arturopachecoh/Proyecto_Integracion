"""E3: facturacion de las OC cumplidas

Revision ID: e3f2factura
Revises: e3d1a0mercado

"""
from alembic import op
import sqlalchemy as sa

revision = "e3f2factura"
down_revision = "e3d1a0mercado"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ordenes_compra", sa.Column("factura_id", sa.String(40)))
    op.add_column("ordenes_compra", sa.Column("factura_error", sa.Text()))


def downgrade() -> None:
    op.drop_column("ordenes_compra", "factura_error")
    op.drop_column("ordenes_compra", "factura_id")
