"""cargas canceladas

Agrega el estado "cancelled" a sku_imports (vista previa descartada sin aplicar).
Alembic no detecta cambios en restricciones CHECK: migración escrita a mano.

Revision ID: b2c4e6f8a1d3
Revises: 67a01cd1068a
Create Date: 2026-10-04 23:30:00

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'b2c4e6f8a1d3'
down_revision: Union[str, Sequence[str], None] = '67a01cd1068a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Aplica los cambios de esta revisión."""
    # Se reemplaza la restricción por una que admite un estado más; no se toca ninguna fila.
    op.drop_constraint('ck_sku_imports_status', 'sku_imports', schema='canales_venta', type_='check')
    op.create_check_constraint(
        'ck_sku_imports_status',
        'sku_imports',
        "status IN ('previewed', 'invalid', 'applying', 'applied', 'failed', 'interrupted', 'cancelled')",
        schema='canales_venta',
    )


def downgrade() -> None:
    """Los retrocesos destructivos requieren una decisión explícita."""
    raise RuntimeError(
        "Downgrade deshabilitado; preparar una migración correctiva."
    )
