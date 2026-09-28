from datetime import datetime, timezone
from uuid import uuid7

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column


def utcnow():
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid7())


class AuditMixin:
    """Campos comunes de identificación, auditoría y baja lógica."""

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=new_id,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
    )

    # NULL permite crear el primer usuario sin depender de otro usuario.
    # En operaciones autenticadas, el servidor asignará el usuario responsable.
    created_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
    )

    updated_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
    )

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    deleted_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
    )
