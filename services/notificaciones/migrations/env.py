"""Entorno Alembic de notificaciones: solo el schema notificaciones.

- La versión se guarda en notificaciones.alembic_version, separada de la de
  auth, libro-mayor, la central y audit: cada uno migra lo suyo aunque
  compartan base.
- El schema se crea aquí si no existe, antes de la tabla de versión.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy.schema import CreateSchema

from app.core.db.connection import database_url, engine
from app.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
SCHEMA = target_metadata.schema


def include_name(name, type_, parent_names):
    """Limita autogenerate al schema y tablas declaradas por este servicio."""
    if type_ == "schema":
        return name == SCHEMA
    if type_ == "table":
        # No proponer eliminar tablas ajenas o retiradas del modelo por accidente.
        return parent_names["schema_qualified_table_name"] in target_metadata.tables
    return True


def run_migrations_offline():
    """Genera SQL sin abrir una conexión a la base."""
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        include_schemas=True,
        include_name=include_name,
        version_table_schema=SCHEMA,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Usa la conexión del servicio para consultar o aplicar migraciones."""
    with engine.connect() as connection:
        connection.execute(CreateSchema(SCHEMA, if_not_exists=True))
        connection.commit()
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
            include_name=include_name,
            version_table_schema=SCHEMA,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
