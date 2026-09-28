"""platform_audit: seguimiento propio común a los servicios de la plataforma.

Uso en un servicio FastAPI/Starlette:

    from platform_audit import AuditConfig, AuditMiddleware, set_actor, step, log_message

    app.add_middleware(AuditMiddleware, config=AuditConfig(engine=engine, service="auth", service_version="0.1.0"))

    # Tras validar la identidad:
    set_actor(user.id, company_id)

    # Pasos manuales:
    with step("crear sesión"):
        ...

Migraciones del schema audit: platform_audit.migrate.upgrade(engine).
Detalle del contrato: docs/plan-observabilidad.md (raíz del repositorio).
"""

from platform_audit.config import AuditConfig
from platform_audit.context import current_trace_id, set_actor
from platform_audit.middleware import AuditMiddleware
from platform_audit.steps import log_message, step

__all__ = [
    "AuditConfig",
    "AuditMiddleware",
    "current_trace_id",
    "log_message",
    "set_actor",
    "step",
]
