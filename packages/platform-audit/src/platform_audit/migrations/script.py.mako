"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

# revision identifiers, used by Alembic.
revision: str = ${repr(up_revision)}
down_revision: Union[str, Sequence[str], None] = ${repr(down_revision)}
branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}


def upgrade() -> None:
    """Aplica los cambios de esta revisión."""
    # El schema audit lo crea platform_audit.migrate antes de migrar.
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    """Los retrocesos destructivos requieren una decisión explícita."""
    raise RuntimeError(
        "Downgrade deshabilitado; preparar una migración correctiva."
    )