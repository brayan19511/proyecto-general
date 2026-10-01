"""Actores (pagos_proveedores.actors): quién hizo cada cambio.

Cada actor se registra la primera vez que opera y se atribuye su propia alta
(id = created_by), así no hace falta seed ni un actor inventado.
"""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.common.mixin_model import new_id
from app.models.entities import Actor


def user_actor_id(db: Session, user_id: str) -> str:
    """Actor del usuario ya validado por auth. Llamar dentro de la transacción del cambio."""
    return _get_or_create(db, "user", user_id)


def _get_or_create(db: Session, kind: str, subject_ref: str) -> str:
    query = select(Actor.id).where(Actor.kind == kind, Actor.subject_ref == subject_ref)
    actor_id = db.scalar(query)
    if actor_id is not None:
        return actor_id

    actor_id = new_id()
    try:
        # Savepoint: si otra solicitud registró el mismo actor a la vez, la
        # unicidad (kind, subject_ref) falla y solo se deshace este insert,
        # no la transacción del cambio que se está haciendo.
        with db.begin_nested():
            db.add(Actor(id=actor_id, created_by=actor_id, kind=kind, subject_ref=subject_ref))
    except IntegrityError:
        return db.scalar(query)
    return actor_id
