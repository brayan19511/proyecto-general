"""Catálogo de permisos para los clientes (GET /catalog/permissions).

La fuente es el código (app/core/permissions.py); la tabla permissions la llena
el seed. Se informan los dos: un permiso que está en el código pero aún no en la
base no se puede conceder (422) hasta ejecutar el seed, y así el cliente puede
avisarlo en lugar de ocultarlo.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import PERMISSIONS
from app.models.entities import Permission


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
