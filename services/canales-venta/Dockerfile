# Imagen del servicio canales-venta.
#
# El contexto de build es la RAÍZ del repositorio, porque la imagen incluye el
# paquete compartido packages/platform-audit:
#
#   docker build -f services/canales-venta/Dockerfile -t canales-venta:0.1.0 .
#
# No incluye secretos: el .env se entrega al ejecutar (variables de entorno o
# un archivo montado de solo lectura).
#
# Incluye migrations/ y alembic.ini: el contenedor *-migrate del Compose aplica
# las migraciones con la misma imagen.

# Python 3.14: uuid.uuid7 está en la biblioteca estándar.
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Misma estructura que el repositorio: requirements.txt referencia el paquete
# como ../../packages/platform-audit.
WORKDIR /app/services/canales-venta

# 0. Driver ODBC de Microsoft para SQL Server (Ofisis), desde el repositorio
#    oficial de Microsoft para Debian 13 (base de python:3.14-slim).
#    libgssapi-krb5-2: dependencia del driver que no se instala sola.
#    curl y gnupg solo se usan para registrarlo y se eliminan después.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl gnupg \
    && curl -sSL https://packages.microsoft.com/config/debian/13/packages-microsoft-prod.deb \
        -o /tmp/packages-microsoft-prod.deb \
    && dpkg -i /tmp/packages-microsoft-prod.deb \
    && rm /tmp/packages-microsoft-prod.deb \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends \
        msodbcsql18 unixodbc libgssapi-krb5-2 \
    && apt-get purge -y --auto-remove curl gnupg \
    && rm -rf /var/lib/apt/lists/*

# 1. Dependencias primero (capa cacheada mientras no cambien).
COPY packages/platform-audit /app/packages/platform-audit
COPY services/canales-venta/requirements.txt ./requirements.txt
RUN pip install -r requirements.txt

# 2. Código del servicio.
COPY services/canales-venta/app ./app
COPY services/canales-venta/scripts ./scripts
COPY services/canales-venta/migrations ./migrations
COPY services/canales-venta/alembic.ini ./alembic.ini

# Usuario sin privilegios: el proceso no corre como root.
RUN useradd --create-home --uid 10001 appuser && chown -R appuser /app
USER appuser

EXPOSE 8000

# Docker marca el contenedor como no sano si /canales-venta/health deja de responder.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/canales-venta/health', timeout=4)"

# --no-proxy-headers: la IP real detrás de proxies la resuelve la aplicación con
# TRUSTED_PROXIES; Uvicorn no debe reescribirla por su cuenta.
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers"]
