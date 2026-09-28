"""Lista negra de IPs: se comprueba en cada solicitud, sin consultar la base.

La tabla gateway.ip_blocks se relee cada GATEWAY_STATE_TTL_SECONDS
(app/core/refresh.py); aquí queda en memoria como redes ya parseadas. La IP
evaluada es la real del cliente (TRUSTED_PROXIES), la misma que va a los logs.
"""

from datetime import datetime
from ipaddress import IPv4Network, IPv6Network, ip_address, ip_network

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db.connection import engine
from app.models.common.mixin_model import utcnow
from app.models.entities import IpBlock

# Último estado leído: (red, vencimiento). Se reemplaza entero en cada lectura.
_blocks: tuple[tuple[IPv4Network | IPv6Network, datetime | None], ...] = ()


def load_blocks() -> None:
    """Lee los bloqueos activos (bloqueante: llamar desde un hilo)."""
    global _blocks
    with Session(engine) as session:
        rows = session.execute(
            select(IpBlock.network, IpBlock.expires_at).where(IpBlock.is_active.is_(True))
        ).all()
    _blocks = tuple((ip_network(network), expires_at) for network, expires_at in rows)


def is_blocked(ip: str | None) -> bool:
    if not ip or not _blocks:
        return False
    try:
        address = ip_address(ip)
    except ValueError:
        return False
    now = utcnow()
    # El vencimiento se revisa aquí: un bloqueo vencido deja de aplicarse al
    # instante, sin esperar a la próxima lectura.
    return any(
        address in network and (expires_at is None or expires_at > now)
        for network, expires_at in _blocks
    )
