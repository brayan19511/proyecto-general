# Imagen del servicio pagos-proveedores.
#
# El contexto de build es la RAÍZ del repositorio, porque la imagen incluye el
# paquete compartido packages/platform-audit:
#
#   docker build -f services/pagos-proveedores/Dockerfile -t pagos-proveedores:0.1.0 .
#
# No incluye secretos: el .env se entrega al ejecutar (variables de entorno o
# un archivo montado de solo lectura).
#
# Incluye migrations/ y alembic.ini para migrar desde el contenedor:
#   python -m alembic upgrade head && python scripts/migrate_audit.py
# Incluye tesseract (con el idioma spa) y poppler para el OCR de constancias
# escaneadas (OCR_ENABLED). Con OCR_ENABLED=false no se usan.

# Python 3.14: uuid.uuid7 está en la biblioteca estándar.
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Programas del sistema para el OCR: tesseract con el idioma español y poppler
# (pdftoppm, que usa pdf2image). Sin recomendados ni caché de apt: imagen más chica.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-spa poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# Misma estructura que el repositorio: requirements.txt referencia el paquete
# como ../../packages/platform-audit.
WORKDIR /app/services/pagos-proveedores

# 1. Dependencias primero (capa cacheada mientras no cambien).
COPY packages/platform-audit /app/packages/platform-audit
COPY services/pagos-proveedores/requirements.txt ./requirements.txt
RUN pip install -r requirements.txt

# 2. Código del servicio.
COPY services/pagos-proveedores/app ./app
COPY services/pagos-proveedores/migrations ./migrations
COPY services/pagos-proveedores/alembic.ini ./alembic.ini
COPY services/pagos-proveedores/scripts ./scripts

# Usuario sin privilegios: el proceso no corre como root.
RUN useradd --create-home --uid 10001 appuser && chown -R appuser /app
USER appuser

EXPOSE 8000

# Docker marca el contenedor como no sano si /pagos-proveedores/health deja de responder.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/pagos-proveedores/health', timeout=4)"

# --no-proxy-headers: la IP real detrás de proxies la resuelve la aplicación con
# TRUSTED_PROXIES; Uvicorn no debe reescribirla por su cuenta.
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers"]
