"""homologacion por prefijo

Revision ID: b3e8f2a61c57
Revises: 9d1c3497b704
Create Date: 2026-09-30 17:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3e8f2a61c57'
down_revision: Union[str, Sequence[str], None] = '9d1c3497b704'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Aplica los cambios de esta revisión."""
    # Se activa match_mode=prefix: la unicidad pasa a incluir el modo para que
    # "V114" exacto y "V114" prefijo puedan convivir (exacto gana al resolver).
    op.drop_index('uq_cost_center_mappings_company_code_active', table_name='cost_center_mappings', schema='libro_mayor', postgresql_where=sa.text('is_active'), mssql_where=sa.text('is_active = 1'))
    op.create_index('uq_cost_center_mappings_company_code_mode_active', 'cost_center_mappings', ['company_id', 'cost_center_code', 'match_mode'], unique=True, schema='libro_mayor', postgresql_where=sa.text('is_active'), mssql_where=sa.text('is_active = 1'))


def downgrade() -> None:
    """Los retrocesos destructivos requieren una decisión explícita."""
    raise RuntimeError(
        "Downgrade deshabilitado; preparar una migración correctiva."
    )
