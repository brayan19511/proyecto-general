from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context


from app.core.db.connection import database_url, engine
from app.models import Base

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
# target_metadata = None
target_metadata = Base.metadata


def include_name(name, type_, parent_names):
    """Limita autogenerate al schema y tablas declaradas por este servicio."""
    if type_ == "schema":
        return name == target_metadata.schema
    if type_ == "table":
        # No proponer eliminar tablas ajenas o retiradas del modelo por accidente.
        # Una retirada de tabla requerirá una decisión y migración explícitas.
        return parent_names["schema_qualified_table_name"] in target_metadata.tables
    return True

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline():
    """Genera SQL sin abrir una conexión a la base."""
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        include_schemas=True,
        include_name=include_name,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Utiliza la conexión de auth para consultar o aplicar migraciones."""
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
            include_name=include_name,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
