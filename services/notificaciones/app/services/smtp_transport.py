"""Conexión SMTP saliente con las protecciones de la plataforma.

La usan la prueba de cuentas (POST /smtp-accounts/{id}/test) y, más adelante,
el worker. Reglas (acuerdo 2026-10-01):

- Puerto dentro de SMTP_ALLOWED_PORTS.
- SSRF: el host se resuelve aquí y TODAS sus direcciones deben ser públicas o
  estar en SMTP_ALLOWED_PRIVATE_NETWORKS. Loopback, redes privadas, link-local
  (169.254.169.254, metadatos en la nube) y multicast se rechazan. Se conecta a
  la IP ya comprobada (no se resuelve otra vez), así un DNS que cambie entre la
  comprobación y la conexión no lleva a otra máquina.
- TLS obligatorio: starttls (si el servidor no lo ofrece, falla; nunca sigue
  sin cifrar) o ssl. El certificado se verifica contra las CA del sistema más
  SMTP_CA_BUNDLE, salvo los hosts de SMTP_TLS_UNVERIFIED_HOSTS.
"""

import smtplib
import socket
import ssl
from dataclasses import dataclass
from ipaddress import ip_address, ip_network

from app.core.config import settings

_ALLOWED_PRIVATE_NETWORKS = tuple(ip_network(n, strict=False) for n in settings.SMTP_ALLOWED_PRIVATE_NETWORKS)


class BlockedDestinationError(Exception):
    """Puerto no permitido o dirección que no se admite como destino SMTP."""


@dataclass(frozen=True)
class SmtpEndpoint:
    host: str
    port: int
    security: str  # starttls | ssl
    timeout_seconds: int


def check_port(port: int) -> None:
    if port not in settings.SMTP_ALLOWED_PORTS:
        allowed = ", ".join(str(p) for p in settings.SMTP_ALLOWED_PORTS)
        raise BlockedDestinationError(f"Puerto no permitido. Permitidos: {allowed}.")


def _is_allowed_address(address: str) -> bool:
    ip = ip_address(address)
    if any(ip in network for network in _ALLOWED_PRIVATE_NETWORKS):
        return True
    return ip.is_global and not ip.is_multicast


def resolve_allowed_ip(host: str, port: int) -> str:
    """IP a la que conectarse, si el puerto y TODAS las direcciones del host se admiten."""
    check_port(port)
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror:
        raise ConnectionError("No se pudo resolver el host.") from None
    addresses = list(dict.fromkeys(info[4][0] for info in infos))
    # Todas, no alguna: un nombre con una IP pública y otra interna no se admite.
    if not addresses or not all(_is_allowed_address(a) for a in addresses):
        raise BlockedDestinationError("El host apunta a una dirección no permitida.")
    return addresses[0]


def tls_context(host: str) -> ssl.SSLContext:
    if host.lower() in settings.SMTP_TLS_UNVERIFIED_HOSTS:
        # Cifra pero no autentica al servidor (excepción configurada por despliegue).
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        return context
    context = ssl.create_default_context()  # CA del sistema, verificación de nombre.
    if settings.SMTP_CA_BUNDLE is not None:
        context.load_verify_locations(cafile=str(settings.SMTP_CA_BUNDLE))
    return context


class _PinnedSMTP(smtplib.SMTP):
    """SMTP que conecta a una IP ya comprobada; TLS valida contra el nombre del host."""

    def __init__(self, pinned_ip: str, **kwargs):
        self._pinned_ip = pinned_ip
        super().__init__(**kwargs)

    def _get_socket(self, host, port, timeout):
        return socket.create_connection((self._pinned_ip, port), timeout, self.source_address)


class _PinnedSMTPSSL(smtplib.SMTP_SSL):
    def __init__(self, pinned_ip: str, **kwargs):
        self._pinned_ip = pinned_ip
        super().__init__(**kwargs)

    def _get_socket(self, host, port, timeout):
        sock = socket.create_connection((self._pinned_ip, port), timeout, self.source_address)
        return self.context.wrap_socket(sock, server_hostname=self._host)


def open_connection(endpoint: SmtpEndpoint, username: str | None, password: str | None) -> smtplib.SMTP:
    """Conexión abierta, cifrada y autenticada. Quien la usa debe cerrarla (quit/close)."""
    ip = resolve_allowed_ip(endpoint.host, endpoint.port)
    context = tls_context(endpoint.host)
    if endpoint.security == "ssl":
        smtp = _PinnedSMTPSSL(
            ip, host=endpoint.host, port=endpoint.port, timeout=endpoint.timeout_seconds, context=context
        )
    else:
        smtp = _PinnedSMTP(ip, host=endpoint.host, port=endpoint.port, timeout=endpoint.timeout_seconds)
    try:
        smtp.ehlo()
        if endpoint.security == "starttls":
            # Sin STARTTLS anunciado lanza SMTPNotSupportedError: nunca se sigue en claro.
            smtp.starttls(context=context)
            smtp.ehlo()
        if username is not None:
            smtp.login(username, password or "")
    except BaseException:
        smtp.close()
        raise
    return smtp


def classify_error(error: BaseException) -> str:
    """Categoría segura para mostrar o guardar (sin el texto del servidor)."""
    if isinstance(error, BlockedDestinationError):
        return "blocked_address"
    if isinstance(error, smtplib.SMTPAuthenticationError):
        return "auth"
    if isinstance(error, (ssl.SSLError, smtplib.SMTPNotSupportedError)):
        return "tls"
    if isinstance(error, (TimeoutError, socket.timeout)):
        return "timeout"
    if isinstance(error, (smtplib.SMTPException, OSError, ConnectionError)):
        return "connection"
    return "unknown"
