"""Migraciones del schema audit, propias del paquete.

Cada servicio las ejecuta con SU engine (no hay URL aparte):

    from platform_audit.migrate import upgrade
    upgrade(engine)

- Crea el schema audit si no existe y aplica las revisiones pendientes.
- La versión se guarda en audit.alembic_version, separada de la de cada
  servicio: no interfiere con sus migraciones.
- Es idempotente: si varios servicios comparten la base, el segundo no hace nada.

Para desarrolladores del paquete (nuevas revisiones):
    revision(engine, "descripcion")   # autogenerate; revisar el archivo antes de publicar.
"""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.engine import Engine
from sqlalchemy.schema import CreateSchema

from platform_audit.models import SCHEMA

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def _config(connection) -> Config:
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    config.attributes["connection"] = connection
    return config


def upgrade(engine: Engine, revision: str = "head") -> None:
    with engine.begin() as connection:
        connection.execute(CreateSchema(SCHEMA, if_not_exists=True))
        command.upgrade(_config(connection), revision)


def revision(engine: Engine, message: str) -> None:
    with engine.begin() as connection:
        connection.execute(CreateSchema(SCHEMA, if_not_exists=True))
        command.revision(_config(connection), message=message, autogenerate=True)


def current(engine: Engine) -> None:
    with engine.connect() as connection:
        command.current(_config(connection))
