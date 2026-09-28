"""agrega is_platform_admin a users

Revision ID: b902cd601f20
Revises: 81b88abef3a5
Create Date: 2026-09-27 14:26:08.125590

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.models.common.mixin_model import new_id, utcnow


# revision identifiers, used by Alembic.
revision: str = 'b902cd601f20'
down_revision: Union[str, Sequence[str], None] = '81b88abef3a5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Tablas mínimas para esta migración. No se importan los modelos ORM porque
# cambian con el tiempo y la migración debe seguir funcionando igual.
users = sa.table(
    "users",
    sa.column("id", sa.String),
    sa.column("created_by", sa.String),
    sa.column("is_platform_admin", sa.Boolean),
    schema="auth",
)
change_history = sa.table(
    "change_history",
    sa.column("id", sa.String),
    sa.column("action", sa.String),
    sa.column("resource_id", sa.String),
    sa.column("company_id", sa.String),
    sa.column("trace_id", sa.String),
    sa.column("before", sa.JSON),
    sa.column("after", sa.JSON),
    sa.column("created_at", sa.DateTime(timezone=True)),
    sa.column("updated_at", sa.DateTime(timezone=True)),
    sa.column("created_by", sa.String),
    sa.column("updated_by", sa.String),
    sa.column("is_active", sa.Boolean),
    schema="auth",
)


def upgrade() -> None:
    """Aplica los cambios de esta revisión."""
    # sa.false() genera el literal correcto para cada motor (false / 0).
    op.add_column(
        'users',
        sa.Column('is_platform_admin', sa.Boolean(), server_default=sa.false(), nullable=False),
        schema='auth',
    )

    # Completa el bootstrap: el admin que ya creó el seed (el único caso con
    # created_by NULL) pasa a ser master admin. Se ejecuta una sola vez, con
    # esta revisión; volver a correr el seed no restituye la marca si se retira.
    bind = op.get_bind()
    seed_user_ids = bind.execute(
        sa.select(users.c.id).where(users.c.created_by.is_(None))
    ).scalars().all()

    now = utcnow()
    for user_id in seed_user_ids:
        bind.execute(
            users.update()
            .where(users.c.id == user_id)
            .values(is_platform_admin=True)
        )
        bind.execute(
            change_history.insert().values(
                id=new_id(),
                action="seed.user.platform_admin_granted",
                resource_id=user_id,
                company_id=None,
                trace_id=None,
                before={"is_platform_admin": False},
                after={"is_platform_admin": True},
                created_at=now,
                updated_at=now,
                created_by=None,
                updated_by=None,
                is_active=True,
            )
        )


def downgrade() -> None:
    """Los retrocesos destructivos requieren una decisión explícita."""
    raise RuntimeError(
        "Downgrade deshabilitado; preparar una migración correctiva."
    )
