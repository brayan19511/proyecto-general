"""Cliente HTTP hacia auth.

Uno solo por proceso: reutiliza conexiones (pool) entre solicitudes. main.py lo
cierra al apagar la aplicación. Con AUTH_ENABLED=false no se crea (None): la
central no abre conexiones hacia un servicio deshabilitado.
"""

import httpx

from app.core.config import settings

auth_client: httpx.AsyncClient | None = None
if settings.AUTH_ENABLED:
    auth_client = httpx.AsyncClient(
        base_url=settings.AUTH_URL,
        timeout=settings.AUTH_TIMEOUT_SECONDS,
        # httpx no reintenta por defecto; tampoco sigue redirecciones: se devuelven
        # tal cual al cliente.
        follow_redirects=False,
        # No usar HTTP_PROXY/HTTPS_PROXY del sistema: el tráfico a auth es interno.
        trust_env=False,
    )
