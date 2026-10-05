"""Conexión a Ofisis (SQL Server externo, base EcommDB).

Ofisis no es una base de este servicio: sus tablas las lee lastmiller. Para no
dejar conexiones abiertas ni retener bloqueos:

- NullPool: cada operación abre su conexión y la cierra de verdad al salir del
  `with`. No quedan conexiones inactivas en el servidor entre solicitudes.
- Lecturas en AUTOCOMMIT: un SELECT no deja una transacción abierta.
- Escrituras en transacciones cortas por lote (ofisis_write), nunca una sola
  transacción larga: con muchas filas SQL Server escalaría a bloqueo de tabla.
- SET LOCK_TIMEOUT: si otro proceso tiene bloqueada la fila o la tabla, la
  consulta falla en OFISIS_LOCK_TIMEOUT_MS en lugar de esperar indefinidamente.
- Timeouts de login y de consulta (OFISIS_CONNECT/QUERY_TIMEOUT_SECONDS).
- APP=<SERVICE_NAME> en la cadena de conexión: el DBA ve quién está conectado.

El engine se crea la primera vez que se usa (no al importar): sin OFISIS_HOST
el servicio arranca igual y las operaciones responden 409. Nunca se mezcla con
la sesión de la base propia.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

import logging

from sqlalchemy import URL, Connection, Engine, create_engine, event
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.services.errors import ConflictError, DeadlineExceededError, UpstreamError

logger = logging.getLogger(__name__)

# Errores de SQL Server/ODBC que significan "esperó demasiado", no "falló":
# HYT00 = timeout de login o de consulta; 1222 = venció SET LOCK_TIMEOUT.
_TIMEOUT_SQLSTATES = {"HYT00", "HYT01"}
_LOCK_TIMEOUT_ERROR = "(1222)"


def ofisis_configured() -> bool:
    return bool(settings.OFISIS_HOST)


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


@lru_cache(maxsize=1)
def ofisis_engine() -> Engine:
    """Engine único por proceso. Con NullPool no guarda conexiones abiertas."""
    if not ofisis_configured():
        raise ConflictError("Ofisis no está configurado en este servicio (OFISIS_HOST).")
    # Usuario y contraseña ya los exige config.py cuando hay OFISIS_HOST.

    url = URL.create(
        drivername="mssql+pyodbc",
        username=settings.OFISIS_USER,
        password=settings.OFISIS_PASSWORD.get_secret_value(),
        host=settings.OFISIS_HOST,
        port=settings.OFISIS_PORT,
        database=settings.OFISIS_DATABASE,
        # Cada clave se agrega tal cual a la cadena de conexión ODBC.
        query={
            "driver": settings.OFISIS_DRIVER,
            "Encrypt": _yes_no(settings.OFISIS_ENCRYPT),
            "TrustServerCertificate": _yes_no(settings.OFISIS_TRUST_SERVER_CERTIFICATE),
            "APP": settings.SERVICE_NAME,
        },
    )
    engine = create_engine(
        url,
        poolclass=NullPool,
        hide_parameters=True,  # Sin valores de parámetros en mensajes de error.
        # pyodbc: timeout = segundos máximos para abrir la conexión (login).
        connect_args={"timeout": settings.OFISIS_CONNECT_TIMEOUT_SECONDS},
    )
    event.listen(engine, "connect", _configure_connection)
    return engine


def _configure_connection(dbapi_connection, _connection_record) -> None:
    """Se ejecuta al abrir cada conexión (con NullPool, en cada operación)."""
    # pyodbc: segundos máximos por consulta en esta conexión; al superarlos la cancela.
    dbapi_connection.timeout = settings.OFISIS_QUERY_TIMEOUT_SECONDS
    cursor = dbapi_connection.cursor()
    try:
        # SET no admite parámetros; el valor es un entero validado en config.py.
        cursor.execute(f"SET LOCK_TIMEOUT {int(settings.OFISIS_LOCK_TIMEOUT_MS)}")
    finally:
        cursor.close()


@contextmanager
def ofisis_read() -> Iterator[Connection]:
    """Conexión de solo lectura en AUTOCOMMIT; se cierra al salir del `with`.

    Uso: with ofisis_read() as connection: connection.execute(...)
    Mantener dentro del `with` solo la consulta, no el procesamiento posterior.
    Los fallos de Ofisis salen como errores de servicio con mensaje seguro.
    """
    try:
        with ofisis_engine().connect() as connection:
            yield connection.execution_options(isolation_level="AUTOCOMMIT")
    except DBAPIError as exc:
        raise _translate(exc) from exc


@contextmanager
def ofisis_write() -> Iterator[Connection]:
    """Conexión para escribir; se cierra al salir del `with`.

    No abre transacción: quien la usa abre transacciones cortas con
    `with connection.begin():` (una por lote), así los bloqueos duran solo lo
    que tarda cada lote y nunca la operación completa. Si un lote falla, se
    revierte ese lote; los anteriores ya quedaron confirmados.
    """
    try:
        with ofisis_engine().connect() as connection:
            yield connection
    except DBAPIError as exc:
        raise _translate(exc) from exc


def _translate(exc: DBAPIError) -> Exception:
    """Error de Ofisis → error de servicio. El detalle técnico va solo al log del proceso."""
    args = getattr(exc.orig, "args", ())
    sqlstate = args[0] if args else None
    # Solo el código y el tipo: el mensaje del driver puede incluir datos de la conexión.
    logger.warning("Ofisis falló: %s (sqlstate=%s)", type(exc.orig).__name__, sqlstate)
    if sqlstate in _TIMEOUT_SQLSTATES:
        return DeadlineExceededError("Ofisis no respondió a tiempo. Intenta de nuevo.")
    if _LOCK_TIMEOUT_ERROR in str(exc.orig):
        return DeadlineExceededError("Los datos de Ofisis están bloqueados por otro proceso. Intenta de nuevo en unos segundos.")
    if isinstance(exc, IntegrityError):
        # Clave duplicada o restricción: otro proceso cambió el dato al mismo tiempo.
        return ConflictError("Ofisis rechazó el cambio: el registro ya existe o cambió al mismo tiempo. Recarga e intenta de nuevo.")
    return UpstreamError("Ofisis no está disponible.")
