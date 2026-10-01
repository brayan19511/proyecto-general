from datetime import datetime, timezone
from uuid import uuid7

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column


def utcnow():
    return datetime.now(timezone.utc)


def new_id() -> str:
    # uuid7 (Python 3.14): ordenado por tiempo, mejor para índices que uuid4.
    return str(uuid7())


def _same_as(column: str):
    """Default que copia otro valor del mismo INSERT (alta: updated_* = created_*)."""
    return lambda context: context.get_current_parameters()[column]


class AuditMixin:
    """Campos comunes de identificación, auditoría y baja lógica.

    Los actores son filas de notificaciones.actors: usuarios de auth, procesos
    internos (worker, retención) u otros servicios. "actors.id" se resuelve en
    el schema notificaciones de Base; no hay FK a tablas de auth.

    El servidor asigna actor y fechas; nunca el body. created_by es
    obligatorio: toda fila tiene un responsable identificado. En el alta,
    updated_at/updated_by toman el mismo valor que created_at/created_by. En
    cada actualización el código los asigna explícitamente (no hay onupdate).
    """

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_by: Mapped[str] = mapped_column(ForeignKey("actors.id"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_same_as("created_at")
    )
    updated_by: Mapped[str] = mapped_column(
        ForeignKey("actors.id"), default=_same_as("created_by")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Baja lógica: DELETE fija is_active=false, deleted_at y deleted_by.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_by: Mapped[str | None] = mapped_column(ForeignKey("actors.id"))
