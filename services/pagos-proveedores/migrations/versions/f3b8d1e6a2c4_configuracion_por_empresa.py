"""configuración por empresa (plantilla por defecto)

Revision ID: f3b8d1e6a2c4
Revises: e1a4c2b7d9f3
Create Date: 2026-10-01 19:00:00

company_settings: una fila activa por empresa con default_template_code
(plantilla de notificaciones de los lotes; NULL = la del servicio).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f3b8d1e6a2c4'
down_revision: Union[str, Sequence[str], None] = 'e1a4c2b7d9f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Aplica los cambios de esta revisión."""
    op.create_table('company_settings',
    sa.Column('company_id', sa.String(length=36), nullable=False),
    sa.Column('default_template_code', sa.String(length=100), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_by', sa.String(length=36), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_by', sa.String(length=36), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('deleted_by', sa.String(length=36), nullable=True),
    sa.ForeignKeyConstraint(['created_by'], ['pagos_proveedores.actors.id'], ),
    sa.ForeignKeyConstraint(['deleted_by'], ['pagos_proveedores.actors.id'], ),
    sa.ForeignKeyConstraint(['updated_by'], ['pagos_proveedores.actors.id'], ),
    sa.PrimaryKeyConstraint('id'),
    schema='pagos_proveedores'
    )
    op.create_index('uq_company_settings_company_active', 'company_settings', ['company_id'], unique=True, schema='pagos_proveedores', postgresql_where=sa.text('is_active'), mssql_where=sa.text('is_active = 1'))


def downgrade() -> None:
    """Los retrocesos destructivos requieren una decisión explícita."""
    raise RuntimeError(
        "Downgrade deshabilitado; preparar una migración correctiva."
    )
