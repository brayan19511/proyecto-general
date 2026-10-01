"""Cliente HTTP hacia auth.

Uno solo por proceso: reutiliza conexiones (pool) entre solicitudes. main.py lo
cierra al apagar la aplicación. Síncrono porque las rutas del servicio son
síncronas (SQLAlchemy síncrono); FastAPI las ejecuta en hilos.
"""

import httpx

from app.core.config import settings

auth_client = httpx.Client(
    base_url=settings.AUTH_URL,
    timeout=settings.AUTH_TIMEOUT_SECONDS,
    # httpx no reintenta por defecto: una consulta fallida es un error, no se repite.
    follow_redirects=False,
    # No usar HTTP_PROXY/HTTPS_PROXY del sistema: el tráfico a auth es interno.
    trust_env=False,
)
