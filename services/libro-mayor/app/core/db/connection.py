"""Conexión y sesiones ORM. Importar este módulo no crea tablas.

Base local del servicio (PostgreSQL). SAP HANA tendrá su propia conexión de
solo lectura en un paso posterior. Configuración: readme.md.
"""
from sqlalchemy import URL, create_engine
from collections.abc import Generator
from sqlalchemy.orm import Session, sessionmaker
from app.core.config import settings

if settings.DB_ENGINE == "postgresql":
    driver="postgresql+psycopg"
    options={
        }
else:
    driver = "mssql+pyodbc"
    # SQL Server necesita pyodbc y ODBC Driver 18 instalados.
    # Se exige cifrado y un certificado verificable; no se omite su validación.
    options = {
        "driver": "ODBC Driver 18 for SQL Server",
        "Encrypt": "yes",
        "TrustServerCertificate": "no",
    }
# URL.create recibe los campos separados: admite caracteres especiales en password.
# SecretStr oculta el valor al mostrar Settings; el driver necesita el valor real.
database_url = URL.create(
    drivername=driver,
    username=settings.DB_USER,
    password=settings.DB_PASSWORD.get_secret_value(),
    host=settings.DB_HOST,
    port=settings.DB_PORT,
    database=settings.DB_NAME,
    query=options,
)

# El engine administra un pool; conecta realmente al ejecutar una operación.
engine = create_engine(
    database_url,
    pool_pre_ping=True,  # Comprueba conexiones reutilizadas; no reintenta transacciones.
    hide_parameters=True,  # Oculta parámetros en mensajes SQLAlchemy, no en todo log propio.
)

# Fábrica compartida; cada llamada crea una sesión independiente.
# Una Session ORM no es una AuthSession de usuario.
SessionLocal = sessionmaker(
    bind=engine,
    expire_on_commit=False,  # Mantiene atributos cargados después del commit.
)


def get_db() -> Generator[Session, None, None]:
    """Dependencia futura de FastAPI: entrega una sesión y la cierra al terminar.

    No confirma cambios. La operación de negocio debe definir su transacción
    y guardar el cambio junto con su historial. Al cerrar, lo no confirmado
    se revierte y se libera la conexión.
    """
    with SessionLocal() as db:
        yield db
