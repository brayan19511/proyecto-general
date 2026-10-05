"""Actores (sap_operaciones.actors): quién hizo cada cambio.

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
    query = select(Actor.id).where(Actor.kind == "user", Actor.subject_ref == user_id)
    actor_id = db.scalar(query)
    if actor_id is not None:
        return actor_id

    actor_id = new_id()
    try:
        # Savepoint: si otra solicitud registró el mismo actor a la vez, la
        # unicidad (kind, subject_ref) falla y solo se deshace este insert,
        # no la transacción del cambio que se está haciendo.
        with db.begin_nested():
            db.add(Actor(id=actor_id, created_by=actor_id, kind="user", subject_ref=user_id))
    except IntegrityError:
        return db.scalar(query)
    return actor_id


# Worker de trabajos (proceso interno): registra el fin de cada trabajo.
WORKER = "sap-operaciones.worker"


def system_actor_id(db: Session, process: str) -> str:
    """Actor de un proceso interno, p. ej. WORKER. Llamar dentro de una transacción."""
    query = select(Actor.id).where(Actor.kind == "system", Actor.subject_ref == process)
    actor_id = db.scalar(query)
    if actor_id is not None:
        return actor_id
    actor_id = new_id()
    try:
        with db.begin_nested():
            db.add(Actor(id=actor_id, created_by=actor_id, kind="system", subject_ref=process))
    except IntegrityError:
        return db.scalar(query)
    return actor_id
