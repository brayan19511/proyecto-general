"""aviso de pago repetido por datos

Revision ID: e1a4c2b7d9f3
Revises: d70bd8fa94a8
Create Date: 2026-10-01 18:00:00

batch_files.already_sent_match: cómo se detectó que el pago ya se envió en
otro lote ("file": mismo PDF; "data": otro PDF con los mismos datos). Las
filas existentes con aviso se marcaron por sha256: se completan con "file".
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e1a4c2b7d9f3'
down_revision: Union[str, Sequence[str], None] = 'd70bd8fa94a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Aplica los cambios de esta revisión."""
    op.add_column('batch_files', sa.Column('already_sent_match', sa.String(length=10), nullable=True), schema='pagos_proveedores')
    op.execute(
        "UPDATE pagos_proveedores.batch_files SET already_sent_match = 'file' "
        "WHERE already_sent_in_batch_id IS NOT NULL"
    )


def downgrade() -> None:
    """Los retrocesos destructivos requieren una decisión explícita."""
    raise RuntimeError(
        "Downgrade deshabilitado; preparar una migración correctiva."
    )
