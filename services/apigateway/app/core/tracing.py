"""Headers que la central agrega a toda llamada hacia un servicio.

- X-Forwarded-For: IP real del cliente (ver client_ip.py).
- X-Trace-Id / X-Parent-Operation-Id: la traza y la operación de la central,
  creadas por su AuditMiddleware. Así, en audit.logs, la fila del servicio
  queda enlazada a la de la central.

El servicio los acepta solo porque la conexión viene de la central (su
TRUSTED_PROXIES). No conceden permisos: solo correlacionan.
"""

from fastapi import Request
from platform_audit.context import current_operation

from app.core.client_ip import forwarded_for


def upstream_headers(request: Request) -> dict[str, str]:
    headers = {"x-forwarded-for": forwarded_for(request)}
    operation = current_operation()  # None si los logs están apagados.
    if operation is not None:
        headers["x-trace-id"] = operation.trace_id
        headers["x-parent-operation-id"] = operation.log_id
    return headers
