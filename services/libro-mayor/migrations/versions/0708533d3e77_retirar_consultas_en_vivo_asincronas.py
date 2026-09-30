"""retirar consultas en vivo asincronas

Revision ID: 0708533d3e77
Revises: f1cfc1eac2ab
Create Date: 2026-09-30 06:48:13.900349

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0708533d3e77'
down_revision: Union[str, Sequence[str], None] = 'f1cfc1eac2ab'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Aplica los cambios de esta revisión."""
    # Escrita a mano (autogenerate nunca propone borrar tablas: ver env.py).
    # Decisión del usuario (2026-09-30): la consulta en vivo pasa a responder en
    # la misma solicitud sin guardar resultados; se retiran las tablas de la
    # versión asíncrona, creadas en f1cfc1eac2ab. Solo contenían resultados de
    # consultas (no datos de negocio). Orden inverso a sus claves foráneas.
    for table in ("live_query_lines", "live_query_parts", "live_queries"):
        op.drop_table(table, schema="libro_mayor")


def downgrade() -> None:
    """Los retrocesos destructivos requieren una decisión explícita."""
    raise RuntimeError(
        "Downgrade deshabilitado; preparar una migración correctiva."
    )