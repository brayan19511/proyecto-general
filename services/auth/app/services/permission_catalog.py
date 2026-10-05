"""Catálogo de permisos para los clientes (GET /catalog/permissions) y su carga.

La fuente es el código (app/core/permissions.py); la tabla permissions la llenan
el seed o POST /admin/permissions/sync. Se informan los dos: un permiso que está
en el código pero aún no en la base no se puede conceder (422) hasta cargarlo, y
así el cliente puede avisarlo en lugar de ocultarlo.
"""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.permissions import PERMISSIONS
from app.models.common.mixin_model import utcnow
from app.models.entities import Permission
from app.services.common import audit_create, history_event


class PermissionSyncConflictError(Exception):
    """Otra carga simultánea insertó el mismo permiso."""


def list_permission_catalog(db: Session) -> list[dict]:
    with db.begin():
        loaded = set(
            db.scalars(
                select(Permission.code).where(Permission.is_active.is_(True), Permission.deleted_at.is_(None))
            )
        )
    return [
        {"code": code, "scopes": list(scopes), "loaded": code in loaded}
        for code, scopes in sorted(PERMISSIONS.items())
    ]


def sync_permission_catalog(db: Session, actor_id: str) -> dict:
    """Inserta los permisos del código que no existen en la base. Idempotente.

    Solo crea códigos del catálogo del código (nunca códigos libres): un permiso
    solo tiene sentido si algún servicio lo comprueba. No asigna roles. Si un
    código ya existe dado de baja, no lo reactiva: lo informa en "inactive".
    Cada alta queda en el historial con el usuario que la pidió.
    """
    now = utcnow()
    created: list[str] = []
    inactive: list[str] = []
    try:
        with db.begin():
            existing = {
                permission.code: permission
                for permission in db.scalars(select(Permission).where(Permission.code.in_(PERMISSIONS)))
            }
            for code in sorted(PERMISSIONS):
                permission = existing.get(code)
                if permission is not None:
                    if not permission.is_active or permission.deleted_at is not None:
                        inactive.append(code)
                    continue
                permission = Permission(code=code, **audit_create(actor_id, now))
                db.add(permission)
                db.flush()  # Asigna el id antes de referenciarlo en el historial.
                db.add(
                    history_event(
                        "permission.loaded", permission.id, None, actor_id, now,
                        before={},
                        after={"code": code, "is_active": True},
                    )
                )
                created.append(code)
    except IntegrityError as exc:
        raise PermissionSyncConflictError() from exc
    return {"created": created, "inactive": inactive}
