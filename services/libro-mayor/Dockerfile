# Imagen del servicio libro-mayor.
#
# El contexto de build es la RAÍZ del repositorio, porque la imagen incluye el
# paquete compartido packages/platform-audit:
#
#   docker build -f services/libro-mayor/Dockerfile -t libro-mayor:0.1.0 .
#
# No incluye secretos: el .env se entrega al ejecutar (variables de entorno o
# un archivo montado de solo lectura).
#
# Incluye migrations/ y alembic.ini para migrar desde el contenedor:
#   python -m alembic upgrade head && python scripts/migrate_audit.py
#
# La misma imagen corre la API (CMD por defecto) y el worker de sincronización:
#   docker run ... libro-mayor:0.1.0 python -m app.worker

# Python 3.14: uuid.uuid7 está en la biblioteca estándar.
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Misma estructura que el repositorio: requirements.txt referencia el paquete
# como ../../packages/platform-audit.
WORKDIR /app/services/libro-mayor

# 1. Dependencias primero (capa cacheada mientras no cambien).
COPY packages/platform-audit /app/packages/platform-audit
COPY services/libro-mayor/requirements.txt ./requirements.txt
RUN pip install -r requirements.txt

# 2. Código del servicio.
COPY services/libro-mayor/app ./app
COPY services/libro-mayor/scripts ./scripts
COPY services/libro-mayor/migrations ./migrations
COPY services/libro-mayor/alembic.ini ./alembic.ini

# Usuario sin privilegios: el proceso no corre como root.
RUN useradd --create-home --uid 10001 appuser && chown -R appuser /app
USER appuser

EXPOSE 8000

# Docker marca el contenedor como no sano si /libro-mayor/health deja de responder.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/libro-mayor/health', timeout=4)"

# --no-proxy-headers: la IP real detrás de proxies la resuelve la aplicación con
# TRUSTED_PROXIES; Uvicorn no debe reescribirla por su cuenta.
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers"]
