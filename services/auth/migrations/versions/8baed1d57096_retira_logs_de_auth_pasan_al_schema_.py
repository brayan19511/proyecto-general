"""retira logs de auth (pasan al schema audit)

Revision ID: 8baed1d57096
Revises: b920b3502d47
Create Date: 2026-09-27 18:12:51.769212

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8baed1d57096'
down_revision: Union[str, Sequence[str], None] = 'b920b3502d47'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Aplica los cambios de esta revisión."""
    # Decisión del usuario: los logs técnicos pasan al schema audit del paquete
    # compartido platform_audit. Estas tablas nunca se usaron.
    # Salvaguarda: solo se eliminan si siguen vacías; si tuvieran filas, la
    # migración se detiene para no perder datos.
    bind = op.get_bind()
    for table in ("logs_steps", "logs_detail", "logs"):
        rows = bind.execute(sa.text(f"SELECT COUNT(*) FROM auth.{table}")).scalar_one()
        if rows:
            raise RuntimeError(f"auth.{table} tiene {rows} filas; migrarlas antes de retirarla.")

    # Orden: primero las que tienen FK hacia logs.
    op.drop_table("logs_steps", schema="auth")
    op.drop_table("logs_detail", schema="auth")
    op.drop_table("logs", schema="auth")


def downgrade() -> None:
    """Los retrocesos destructivos requieren una decisión explícita."""
    raise RuntimeError(
        "Downgrade deshabilitado; preparar una migración correctiva."
    )