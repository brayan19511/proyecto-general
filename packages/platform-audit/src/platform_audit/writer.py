"""Escritura en el schema audit, siempre fuera de la transacción de negocio.

Cada escritura usa su propia conexión y transacción corta. Si falla, se emite
un aviso saneado (solo el tipo de error) y la operación de negocio continúa:
un fallo de logging no deshace nada confirmado.
"""

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import update
from sqlalchemy.orm import Session

from platform_audit.config import AuditConfig
from platform_audit.models import Log, LogDetail, LogStep

logger = logging.getLogger("platform_audit")

_config: AuditConfig | None = None


def configure(config: AuditConfig) -> None:
    global _config
    _config = config


def get_config() -> AuditConfig | None:
    return _config


def now() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid.uuid4())


def _write(fn) -> None:
    if _config is None or not _config.enabled:
        return
    try:
        with Session(_config.engine) as session, session.begin():
            fn(session)
    except Exception as exc:  # noqa: BLE001 - el logging nunca rompe la operación.
        logger.warning("platform_audit: no se pudo escribir el log (%s)", type(exc).__name__)


def start_log(log: Log) -> None:
    _write(lambda s: s.add(log))


def finish_log(log_id: str, values: dict, details: list[LogDetail]) -> None:
    def fn(session: Session) -> None:
        session.execute(update(Log).where(Log.id == log_id).values(**values))
        session.add_all(details)

    _write(fn)


def add_detail(detail: LogDetail) -> None:
    _write(lambda s: s.add(detail))


def add_step(step: LogStep) -> None:
    _write(lambda s: s.add(step))
