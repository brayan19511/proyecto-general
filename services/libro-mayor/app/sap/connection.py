"""Conexión a SAP HANA, solo lectura.

Se crea la primera vez que se usa (no al importar): sin SAP_HOST el servicio
arranca igual y las operaciones que necesitan SAP responden 409. El engine es
distinto al de la base propia; nunca se mezclan sesiones ni transacciones.
La restricción real de solo lectura es el usuario HANA (solo SELECT); este
módulo, además, solo ejecuta SELECT.
"""

from functools import lru_cache

from sqlalchemy import URL, Engine, create_engine

from app.core.config import settings
from app.services.errors import ConflictError


def sap_enabled() -> bool:
    return bool(settings.SAP_HOST)


@lru_cache(maxsize=1)
def sap_engine() -> Engine:
    """Engine único por proceso (pool de conexiones a HANA)."""
    if not sap_enabled():
        raise ConflictError("SAP no está configurado en este servicio (SAP_HOST).")
    url = URL.create(
        drivername="hana+hdbcli",
        username=settings.SAP_USER,
        password=settings.SAP_PASSWORD.get_secret_value(),
        host=settings.SAP_HOST,
        port=settings.SAP_PORT,
    )
    return create_engine(
        url,
        pool_pre_ping=True,  # Detecta conexiones cortadas por el servidor antes de usarlas.
        pool_recycle=3600,  # Renueva conexiones de más de una hora.
        hide_parameters=True,  # Sin valores de parámetros en mensajes de error.
        connect_args={
            # Propiedades de conexión de hdbcli (milisegundos en los timeouts).
            "encrypt": settings.SAP_ENCRYPT,
            "sslValidateCertificate": settings.SAP_VALIDATE_CERTIFICATE,
            "connectTimeout": settings.SAP_CONNECT_TIMEOUT_SECONDS * 1000,
            "communicationTimeout": settings.SAP_QUERY_TIMEOUT_SECONDS * 1000,
        },
    )
