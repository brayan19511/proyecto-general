"""Relectura periódica de la configuración administrable de la central.

Cada GATEWAY_STATE_TTL_SECONDS lee de la base el estado de los servicios y la
lista negra de IPs. Las solicitudes usan la copia en memoria y nunca esperan a
la base. Si una lectura falla, se conserva el último estado conocido.
main.py inicia la tarea al arrancar y la cancela al apagar.
"""

import logging

import anyio

from app.core import ip_blocks, services
from app.core.config import settings

logger = logging.getLogger(__name__)

LOADERS = (
    ("gateway.service_states", services.load_states),
    ("gateway.ip_blocks", ip_blocks.load_blocks),
)


async def refresh_loop() -> None:
    while True:
        for table, load in LOADERS:
            try:
                await anyio.to_thread.run_sync(load)
            except Exception as exc:  # noqa: BLE001 - la central sigue con el último estado.
                logger.warning("No se pudo leer %s (%s); se mantiene el último estado.", table, type(exc).__name__)
        await anyio.sleep(settings.GATEWAY_STATE_TTL_SECONDS)
