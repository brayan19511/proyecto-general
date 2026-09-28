"""Rechaza con 403 las solicitudes de IPs bloqueadas (gateway.ip_blocks).

Va antes del enrutamiento: aplica a todos los servicios publicados y a la
administración. Excepción: /health y /ready, para que Docker y los
orquestadores sigan comprobando la central.

Orden en main.py: dentro de AuditMiddleware (el rechazo queda en los logs con
la IP) y dentro de CORS (el navegador puede leer el 403).
"""

import json

from app.core import ip_blocks
from app.core.client_ip import client_ip

EXEMPT_PATHS = frozenset({"/health", "/ready"})
BODY = json.dumps({"detail": "Acceso denegado."}).encode()


class IpBlockMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["path"] not in EXEMPT_PATHS:
            peer = scope["client"][0] if scope.get("client") else None
            forwarded = next(
                (v.decode("latin-1") for k, v in scope["headers"] if k == b"x-forwarded-for"), ""
            )
            if ip_blocks.is_blocked(client_ip(peer, forwarded)):
                # Respuesta genérica: no revela el motivo ni que existe una lista.
                await send({
                    "type": "http.response.start",
                    "status": 403,
                    "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(BODY)).encode())],
                })
                await send({"type": "http.response.body", "body": BODY})
                return
        await self.app(scope, receive, send)
