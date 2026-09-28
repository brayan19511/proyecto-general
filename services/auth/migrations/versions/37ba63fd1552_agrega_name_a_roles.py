"""agrega name a roles

Revision ID: 37ba63fd1552
Revises: b902cd601f20
Create Date: 2026-09-27 15:43:52.385610

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '37ba63fd1552'
down_revision: Union[str, Sequence[str], None] = 'b902cd601f20'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Tabla mínima para esta migración (no se importan los modelos ORM).
roles = sa.table(
    "roles",
    sa.column("code", sa.String),
    sa.column("name", sa.String),
    schema="auth",
)


def upgrade() -> None:
    """Aplica los cambios de esta revisión."""
    # Una columna NOT NULL no puede agregarse directamente a una tabla con
    # filas. Tres pasos portables: nullable → rellenar → NOT NULL.
    op.add_column('roles', sa.Column('name', sa.String(length=150), nullable=True), schema='auth')

    # Los roles existentes toman su código como nombre inicial; se pueden
    # renombrar después con PATCH /roles/{id}. Es un relleno técnico de la
    # columna nueva, no un cambio de negocio: no genera historial.
    op.execute(roles.update().values(name=roles.c.code))

    op.alter_column(
        'roles',
        'name',
        existing_type=sa.String(length=150),
        nullable=False,
        schema='auth',
    )


def downgrade() -> None:
    """Los retrocesos destructivos requieren una decisión explícita."""
    raise RuntimeError(
        "Downgrade deshabilitado; preparar una migración correctiva."
    )
