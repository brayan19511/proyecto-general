from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column


def utcnow():
    return datetime.now(timezone.utc)


def new_id() -> str:
    # uuid4: funciona en Python 3.13 (uuid7 es de 3.14). Las tablas de la
    # central son pequeñas y no necesitan ids ordenados por tiempo.
    return str(uuid4())


class AuditMixin:
    """Campos comunes de identificación, auditoría y baja lógica.

    created_by / updated_by / deleted_by guardan el id del usuario de auth
    validado por GET /auth/me (administrador). Sin clave foránea: la central
    no accede a las tablas de auth. El servidor los asigna; nunca el body.
    """

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_by: Mapped[str | None] = mapped_column(String(36))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_by: Mapped[str | None] = mapped_column(String(36))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_by: Mapped[str | None] = mapped_column(String(36))
