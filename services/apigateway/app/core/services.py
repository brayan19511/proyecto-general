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
from app.models.entities import ServiceState

@dataclass(frozen=True)
class ServiceInfo:
    name: str
    enabled_by_config: bool
    panel_managed: bool


# Un servicio nuevo publicado en la central se agrega aquí, con su
# <SERVICIO>_ENABLED y su <SERVICIO>_URL en config.py.
SERVICES: dict[str, ServiceInfo] = {
    "auth": ServiceInfo("auth", enabled_by_config=settings.AUTH_ENABLED, panel_managed=False),
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

