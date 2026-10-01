"""Servicios que la central publica y si están habilitados.

Estado efectivo = configuración (<SERVICIO>_ENABLED) Y estado en la base
(gateway.service_states), si el servicio se administra desde el panel.

- La configuración es el interruptor maestro: con false, nada lo habilita.
- Sin fila en la base, vale la configuración.
- panel_managed=False: solo se cambia por configuración (auth: si el panel lo
  deshabilitara, nadie podría iniciar sesión para volver a habilitarlo).

La base se relee cada GATEWAY_STATE_TTL_SECONDS en segundo plano
(app/core/refresh.py): las solicitudes nunca esperan a la base.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db.connection import engine
from app.core.public_routes import (
    AUTH_ROUTES,
    LIBRO_MAYOR_ROUTES,
    NOTIFICACIONES_ROUTES,
    PAGOS_PROVEEDORES_ROUTES,
    Route,
)
from app.models.entities import ServiceState

@dataclass(frozen=True)
class ServiceInfo:
    name: str
    enabled_by_config: bool
    panel_managed: bool
    # Primer segmento de sus rutas (/auth, /libro-mayor). La central reenvía el
    # path sin reescribirlo: /auth/login en la central es /auth/login en auth.
    prefix: str = ""
    url: str | None = None  # Dirección interna (<SERVICIO>_URL).
    timeout: float = 30  # <SERVICIO>_TIMEOUT_SECONDS; una ruta puede tener el suyo.
    routes: tuple[Route, ...] = ()  # Rutas publicadas (app/core/public_routes.py).


# Un servicio nuevo publicado en la central se agrega aquí, con su
# <SERVICIO>_ENABLED, <SERVICIO>_URL y <SERVICIO>_TIMEOUT_SECONDS en config.py
# y sus rutas en public_routes.py. El reenvío (app/api/routes/proxy.py) y el
# cliente HTTP (app/clients/upstream.py) salen de aquí, sin más código.
SERVICES: dict[str, ServiceInfo] = {
    "auth": ServiceInfo(
        "auth", enabled_by_config=settings.AUTH_ENABLED, panel_managed=False,
        prefix="/auth", url=settings.AUTH_URL, timeout=settings.AUTH_TIMEOUT_SECONDS, routes=AUTH_ROUTES,
    ),
    "libro-mayor": ServiceInfo(
        "libro-mayor", enabled_by_config=settings.LIBRO_MAYOR_ENABLED, panel_managed=True,
        prefix="/libro-mayor", url=settings.LIBRO_MAYOR_URL, timeout=settings.LIBRO_MAYOR_TIMEOUT_SECONDS,
        routes=LIBRO_MAYOR_ROUTES,
    ),
    "notificaciones": ServiceInfo(
        "notificaciones", enabled_by_config=settings.NOTIFICACIONES_ENABLED, panel_managed=True,
        prefix="/notificaciones", url=settings.NOTIFICACIONES_URL, timeout=settings.NOTIFICACIONES_TIMEOUT_SECONDS,
        routes=NOTIFICACIONES_ROUTES,
    ),
    "pagos-proveedores": ServiceInfo(
        "pagos-proveedores", enabled_by_config=settings.PAGOS_PROVEEDORES_ENABLED, panel_managed=True,
        prefix="/pagos-proveedores", url=settings.PAGOS_PROVEEDORES_URL,
        timeout=settings.PAGOS_PROVEEDORES_TIMEOUT_SECONDS, routes=PAGOS_PROVEEDORES_ROUTES,
    ),
}

# Último estado leído de la base: {servicio: is_enabled}. Se reemplaza entero
# en cada lectura (nunca se modifica a medias).
_db_states: dict[str, bool] = {}


def load_states() -> None:
    """Lee gateway.service_states (bloqueante: llamar desde un hilo)."""
    global _db_states
    with Session(engine) as session:
        rows = session.execute(
            select(ServiceState.service, ServiceState.is_enabled).where(ServiceState.is_active.is_(True))
        ).all()
    _db_states = {service: enabled for service, enabled in rows}


def db_state(name: str) -> bool | None:
    return _db_states.get(name)


def is_enabled(name: str) -> bool:
    info = SERVICES.get(name)
    if info is None or not info.enabled_by_config:
        return False
    if not info.panel_managed:
        return True
    return _db_states.get(name, True)

