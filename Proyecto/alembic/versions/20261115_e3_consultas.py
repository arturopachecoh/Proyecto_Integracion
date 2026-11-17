"""E3: estado "consulta" para los mensajes que preguntan por un pedido anterior

Revision ID: e3g3consulta
Revises: e3f2factura

"""
from alembic import op

revision = "e3g3consulta"
down_revision = "e3f2factura"
branch_labels = None
depends_on = None


def _check(valores: str) -> None:
    op.execute("ALTER TABLE mensajes DROP CONSTRAINT IF EXISTS ck_mensajes_estado_mensaje")
    op.execute(f"ALTER TABLE mensajes ADD CONSTRAINT ck_mensajes_estado_mensaje CHECK (estado IN ({valores}))")


def upgrade() -> None:
    _check("'pendiente', 'respondiendo', 'pedido', 'descartado', 'consulta', 'sin_respuesta'")


def downgrade() -> None:
    op.execute("UPDATE mensajes SET estado = 'descartado' WHERE estado = 'consulta'")
    _check("'pendiente', 'respondiendo', 'pedido', 'descartado', 'sin_respuesta'")
