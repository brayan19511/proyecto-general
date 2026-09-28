"""Registro del historial de negocio (libro_mayor.change_history)."""

from datetime import datetime

from platform_audit import current_trace_id
from sqlalchemy.orm import Session

from app.models.entities import ChangeHistory


def record_change(
    db: Session,
    *,
    action: str,
    resource_type: str,
    resource_id: str,
    company_id: str | None,
    actor_id: str,
    now: datetime,
    before: dict,
    after: dict,
) -> None:
    """Agrega el evento a la transacción en curso: se confirma junto con el cambio.

    before/after: solo campos permitidos del recurso ({} si no aplica).
    """
    db.add(
        ChangeHistory(
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            company_id=company_id,
            trace_id=current_trace_id(),
            before=before,
            after=after,
            created_at=now,
            created_by=actor_id,
        )
    )
