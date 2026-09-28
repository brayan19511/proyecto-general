"""Entorno Alembic del schema audit. Lo invoca platform_audit.migrate con la
conexión del servicio; no se usa alembic.ini ni una URL propia."""

from alembic import context

from platform_audit.models import SCHEMA, Base

target_metadata = Base.metadata


def include_name(name, type_, parent_names):
    """Solo el schema audit y sus tablas: nunca propone cambios en los schemas
    de los servicios (auth, etc.)."""
    if type_ == "schema":
        return name == SCHEMA
    if type_ == "table":
        return parent_names["schema_qualified_table_name"] in target_metadata.tables
    return True


connection = context.config.attributes["connection"]
context.configure(
    connection=connection,
    target_metadata=target_metadata,
    include_schemas=True,
    include_name=include_name,
    version_table="alembic_version",
    version_table_schema=SCHEMA,
)

with context.begin_transaction():
    context.run_migrations()
