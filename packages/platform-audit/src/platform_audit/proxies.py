"""Proxies confiables: IPs exactas o rangos CIDR, y la IP real del cliente.

Una sola regla para toda la plataforma (middleware de logs y servicios):

- TRUSTED_PROXIES acepta "10.0.0.5" (una IP) o "172.30.0.0/24" (un rango).
  Un rango es necesario cuando las IPs cambian (Docker, nube, balanceadores).
- Solo si la conexión directa viene de un proxy confiable se lee
  X-Forwarded-For ("cliente, proxy1, proxy2"); cualquiera puede escribir ese header.
- Confiar en un rango confía en TODO lo que esté dentro: usar redes exclusivas
  (p. ej. una red Docker solo para la central y el servicio).
"""

from collections.abc import Iterable
from ipaddress import IPv4Network, IPv6Network, ip_address, ip_network

Networks = tuple[IPv4Network | IPv6Network, ...]


def parse_trusted(values: Iterable[str]) -> Networks:
    """Convierte la configuración en redes. Un valor inválido lanza ValueError
    al arrancar, en lugar de ignorarse en silencio. Una IP exacta es un /32 (/128)."""
    return tuple(ip_network(value.strip(), strict=False) for value in values)


def is_trusted(ip: str | None, networks: Networks) -> bool:
    if not ip or not networks:
        return False
    try:
        address = ip_address(ip)
    except ValueError:  # "unknown", nombres de host, etc.
        return False
    return any(address in network for network in networks)


def client_ip(peer: str | None, forwarded_for: str, networks: Networks) -> str | None:
    """IP real del cliente. Sin proxy confiable, la de la conexión directa."""
    if not is_trusted(peer, networks):
        return peer
    hops = [hop.strip() for hop in forwarded_for.split(",") if hop.strip()]
    # De derecha a izquierda: cada proxy confiable agrega a quien le habló.
    # El primero que no es un proxy confiable es el cliente real.
    for hop in reversed(hops):
        if not is_trusted(hop, networks):
            return hop[:64]
    return peer
