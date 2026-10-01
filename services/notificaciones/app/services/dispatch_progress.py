"""Estado y progreso de un envío, calculados contando sus mensajes (acuerdo 1 del modelo).

No se guardan en dispatches: así varios workers no actualizan la misma fila y
el dato nunca queda desfasado. Usa el índice (dispatch_id, status).
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.entities import Actor, Dispatch, Message
from app.schemas.dispatches import DispatchCounts, DispatchOut, DispatchStatus

_IN_PROGRESS = ("pending", "sending", "retrying")


def count_by_status(db: Session, dispatch_ids: list[str]) -> dict[str, DispatchCounts]:
    """Conteo por estado de varios envíos en una sola consulta."""
    counts = {dispatch_id: DispatchCounts() for dispatch_id in dispatch_ids}
    if not dispatch_ids:
        return counts
    rows = db.execute(
        select(Message.dispatch_id, Message.status, func.count())
        .where(Message.dispatch_id.in_(dispatch_ids))
        .group_by(Message.dispatch_id, Message.status)
    )
    for dispatch_id, status, amount in rows:
        setattr(counts[dispatch_id], status, amount)
        counts[dispatch_id].total += amount
    return counts


def derive_status(counts: DispatchCounts) -> DispatchStatus:
    """pending: ninguno empezó · in_progress: alguno en curso · completed: todos
    enviados · completed_with_errors: ninguno en curso y alguno fallido,
    incierto o cancelado."""
    if counts.total == counts.pending:
        return "pending"
    if any(getattr(counts, status) for status in _IN_PROGRESS):
        return "in_progress"
    if counts.sent == counts.total:
        return "completed"
    return "completed_with_errors"


def to_out(db: Session, dispatches: list[Dispatch]) -> list[DispatchOut]:
    """DispatchOut de varios envíos con dos consultas (conteos y solicitantes)."""
    counts = count_by_status(db, [d.id for d in dispatches])
    actor_ids = {d.created_by for d in dispatches}
    rows = db.execute(select(Actor.id, Actor.subject_ref).where(Actor.id.in_(actor_ids), Actor.kind == "user"))
    users = {actor_id: subject_ref for actor_id, subject_ref in rows}
    return [
        DispatchOut(
            id=d.id, kind=d.kind, consumer=d.consumer, consumer_reference=d.consumer_reference,
            status=derive_status(counts[d.id]), counts=counts[d.id],
            requested_by_user_id=users.get(d.created_by), requested_by_email=d.requester_email,
            created_at=d.created_at,
        )
        for d in dispatches
    ]
