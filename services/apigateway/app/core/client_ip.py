"""X-Forwarded-For que la central envía a los servicios.

- Si la conexión viene de un proxy confiable (TRUSTED_PROXIES, p. ej. Nginx),
  se conserva la cadena que trae y se agrega la IP de ese proxy.
- Si no (el cliente llega directo), se descarta lo que traiga: el cliente
  podría inventarlo. Se envía solo la IP de la conexión.

El servicio (auth) confía en este header solo porque la conexión viene de la
central (su TRUSTED_PROXIES).
"""

from fastapi import Request
from platform_audit.proxies import is_trusted, parse_trusted

from app.core.config import settings

# Se calcula una vez al importar; un valor inválido falla al arrancar.
TRUSTED_NETWORKS = parse_trusted(settings.TRUSTED_PROXIES)


def forwarded_for(request: Request) -> str:
    peer = request.client.host if request.client else "unknown"
    if not is_trusted(peer, TRUSTED_NETWORKS):
        return peer
    incoming = request.headers.get("x-forwarded-for", "").strip()
    return f"{incoming}, {peer}" if incoming else peer
