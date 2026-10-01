"""Clientes HTTP hacia los servicios publicados (uno por servicio).

Uno por proceso y servicio: reutiliza conexiones (pool) entre solicitudes.
main.py los cierra al apagar la aplicación. Un servicio con
<SERVICIO>_ENABLED=false no tiene cliente: la central no abre conexiones hacia
un servicio deshabilitado. Si se deshabilita desde el panel, el cliente existe
pero no se usa.
"""

import httpx

from app.core.services import SERVICES

clients: dict[str, httpx.AsyncClient] = {
    name: httpx.AsyncClient(
        base_url=info.url,
        timeout=info.timeout,
        # httpx no reintenta por defecto; tampoco sigue redirecciones: se
        # devuelven tal cual al cliente.
        follow_redirects=False,
        # No usar HTTP_PROXY/HTTPS_PROXY del sistema: el tráfico es interno.
        trust_env=False,
    )
    for name, info in SERVICES.items()
    if info.enabled_by_config
}


async def close_all() -> None:
    for client in clients.values():
        await client.aclose()
