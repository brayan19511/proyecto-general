"""Contexto de la operación en curso (una por solicitud), sin pasarlo por parámetros.

El middleware lo crea; el código del servicio lo usa para registrar pasos y
detalles, y para indicar quién es el usuario una vez validado.
"""

import time
from contextvars import ContextVar
from dataclasses import dataclass, field


@dataclass
class Operation:
    log_id: str
    trace_id: str
    started_monotonic: float = field(default_factory=time.monotonic)
    # Los completa el servicio tras validar la identidad (set_actor).
    user_id: str | None = None
    company_id: str | None = None


_current: ContextVar[Operation | None] = ContextVar("platform_audit_operation", default=None)


def current_operation() -> Operation | None:
    return _current.get()


def current_trace_id() -> str | None:
    operation = _current.get()
    return operation.trace_id if operation else None


def set_actor(user_id: str | None, company_id: str | None = None) -> None:
    """Registra en la cabecera del log quién hace la solicitud.

    Llamarlo solo con una identidad YA validada (token, sesión, API key).
    Nunca con datos que el cliente afirma sin comprobar.
    """
    operation = _current.get()
    if operation is None:
        return
    operation.user_id = user_id
    if company_id is not None:
        operation.company_id = company_id
