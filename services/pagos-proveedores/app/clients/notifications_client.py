"""Cliente HTTP hacia notificaciones.

Uno solo por proceso (pool de conexiones); main.py lo cierra al apagar.
Siempre con el token del usuario que envía (acuerdo de notificaciones): este
servicio no tiene credenciales propias allá.
"""

import httpx

from app.core.config import settings

notifications_client = httpx.Client(
    base_url=settings.NOTIFICACIONES_URL,
    timeout=settings.NOTIFICACIONES_TIMEOUT_SECONDS,
    # Sin reintentos automáticos: crear un envío es una mutación. El reintento
    # lo hace el usuario y es seguro por la Idempotency-Key (el id del lote).
    follow_redirects=False,
    trust_env=False,  # Tráfico interno: sin HTTP_PROXY/HTTPS_PROXY del sistema.
)
