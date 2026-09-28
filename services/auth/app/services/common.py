"""Ayudantes compartidos por los CRUD empresariales.

Los asigna el servidor: nunca vienen del body (los schemas usan extra="forbid").
"""

from datetime import datetime

from app.models.entities import ChangeHistory


def audit_create(actor_id: str, now: datetime) -> dict:
    """Campos comunes de un alta: mismo instante y actor en created y updated."""
    return {
        "created_at": now,
        "updated_at": now,
        "created_by": actor_id,
        "updated_by": actor_id,
        "is_active": True,
    }


def touch(entity, actor_id: str, now: datetime) -> None:
    """Marca una modificación: quién y cuándo."""
    entity.updated_at = now
    entity.updated_by = actor_id


def soft_delete(entity, actor_id: str, now: datetime) -> None:
    """Baja lógica: la fila se conserva; nunca se ejecuta DELETE SQL."""
    entity.is_active = False
    entity.deleted_at = now
    entity.deleted_by = actor_id
    touch(entity, actor_id, now)


def restore(entity, actor_id: str, now: datetime) -> None:
    """Deshace una baja lógica o suspensión con una acción explícita.

    Solo la usan operaciones de un usuario autorizado, nunca el seed. Quien la
    llama debe revalidar permisos y generar su evento de historial.
    """
    entity.is_active = True
    entity.deleted_at = None
    entity.deleted_by = None
    touch(entity, actor_id, now)


def history_event(
    action: str,
    resource_id: str,
    company_id: str | None,
    actor_id: str,
    now: datetime,
    before: dict,
    after: dict,
) -> ChangeHistory:
    """Evento de historial de solo anexado. before/after: solo campos permitidos,
    nunca contraseñas, hashes ni tokens."""
    return ChangeHistory(
        action=action,
        resource_id=resource_id,
        company_id=company_id,
        before=before,
        after=after,
        **audit_create(actor_id, now),
    )
