"""Pasos y mensajes manuales dentro de una operación.

Uso como bloque:
    with step("crear sesión"):
        ...

Uso como decorador:
    @step("calcular permisos")
    def build_context(...): ...

Cada paso escribe una fila al empezar y otra al terminar (o al fallar), en el
momento: así se ve en qué parte va una operación larga. Fuera de una solicitud
(sin middleware) no hace nada.
"""

import time
from contextlib import contextmanager

from platform_audit import writer
from platform_audit.context import current_operation
from platform_audit.models import LogDetail, LogStep


def _short(text: str | None, limit: int = 1000) -> str | None:
    return text[:limit] if text else text


@contextmanager
def step(name: str, message: str | None = None):
    operation = current_operation()
    if operation is None:
        yield
        return

    step_id = writer.new_id()
    started = time.monotonic()
    writer.add_step(
        LogStep(
            id=writer.new_id(), log_id=operation.log_id, step_id=step_id,
            name=name[:150], phase="start", message=_short(message), created_at=writer.now(),
        )
    )
    try:
        yield
    except Exception as exc:
        # Solo el tipo de error: el mensaje puede contener datos sensibles.
        writer.add_step(
            LogStep(
                id=writer.new_id(), log_id=operation.log_id, step_id=step_id,
                name=name[:150], phase="error", message=type(exc).__name__,
                duration_ms=(time.monotonic() - started) * 1000, created_at=writer.now(),
            )
        )
        raise
    writer.add_step(
        LogStep(
            id=writer.new_id(), log_id=operation.log_id, step_id=step_id,
            name=name[:150], phase="end",
            duration_ms=(time.monotonic() - started) * 1000, created_at=writer.now(),
        )
    )


def log_message(level: str, message: str, data: dict | None = None) -> None:
    """Detalle manual: level = info, success, warning o error.

    `data` debe contener solo campos permitidos (se enmascaran las claves
    sensibles igualmente)."""
    operation = current_operation()
    config = writer.get_config()
    if operation is None or config is None:
        return
    writer.add_detail(
        LogDetail(
            id=writer.new_id(), log_id=operation.log_id, level=level, kind="message",
            message=_short(message), data=config.masker.redact(data) if data else None,
            created_at=writer.now(),
        )
    )
