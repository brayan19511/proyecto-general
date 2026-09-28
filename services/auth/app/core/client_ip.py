"""IP del cliente, considerando proxies confiables.

Detrás de la API central o un balanceador, la conexión llega desde el proxy y
la IP real viaja en X-Forwarded-For ("cliente, proxy1, proxy2"). Ese header lo
puede escribir cualquiera, así que solo se lee si la conexión directa viene de
un proxy de TRUSTED_PROXIES (IPs exactas o rangos CIDR).

La regla es la del paquete platform_audit (proxies.py): la misma IP que se
guarda en los logs es la que usan los límites de auth.
"""

from fastapi import Request
from platform_audit.proxies import client_ip as resolve_client_ip, parse_trusted

from app.core.config import settings

# Se calcula una vez al importar; un valor inválido falla al arrancar.
TRUSTED_NETWORKS = parse_trusted(settings.TRUSTED_PROXIES)


def client_ip(request: Request) -> str:
    peer = request.client.host if request.client else None
    forwarded = request.headers.get("x-forwarded-for", "")
    return resolve_client_ip(peer, forwarded, TRUSTED_NETWORKS) or "unknown"
