"""Lectura de logs para las rutas de consulta de cada servicio.

Cada servicio consulta SOLO sus filas (filtro obligatorio por service). La
vista conjunta entre servicios se hará por APIs internas, nunca leyendo filas
de otro servicio.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from platform_audit.models import Log, LogDetail, LogStep


def list_logs(
    session: Session,
    service: str,
    *,
    trace_id: str | None = None,
    user_id: str | None = None,
    outcome: str | None = None,
    path_prefix: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Log]:
    statement = select(Log).where(Log.service == service)
    if trace_id:
        statement = statement.where(Log.trace_id == trace_id)
    if user_id:
        statement = statement.where(Log.user_id == user_id)
    if outcome:
        statement = statement.where(Log.outcome == outcome)
    if path_prefix:
        statement = statement.where(Log.path.startswith(path_prefix, autoescape=True))
    statement = statement.order_by(Log.started_at.desc()).limit(limit).offset(offset)
    return list(session.scalars(statement))


def get_log(session: Session, service: str, log_id: str) -> tuple[Log, list[LogDetail], list[LogStep]] | None:
    log = session.scalar(select(Log).where(Log.id == log_id, Log.service == service))
    if log is None:
        return None
    details = list(
        session.scalars(select(LogDetail).where(LogDetail.log_id == log.id).order_by(LogDetail.created_at))
    )
    steps = list(
        session.scalars(select(LogStep).where(LogStep.log_id == log.id).order_by(LogStep.created_at))
    )
    return log, details, steps
