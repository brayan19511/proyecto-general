from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Carpeta del servicio, independientemente de dónde ejecutes Python.
BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Lee configuración del entorno y del .env del servicio; no conecta a la BD."""

    PROJECT_NAME: str = "Pagos a proveedores"
    # Identificación en los logs (audit.logs.service / service_version).
    SERVICE_NAME: str = "pagos-proveedores"
    SERVICE_VERSION: str = "0.1.0"

    # Logs (paquete platform_audit, schema audit). AUDIT_ENABLED=false los apaga
    # sin tocar el código; AUDIT_MAX_BODY_BYTES limita cuánto body se guarda.
    AUDIT_ENABLED: bool = True
    AUDIT_MAX_BODY_BYTES: int = Field(default=4096, ge=0, le=65536)

    # Motor seleccionable por despliegue. No garantiza portabilidad de los modelos.
    DB_ENGINE: Literal["postgresql", "mssql"] = "postgresql"
    # localhost = base en esta máquina. Desde Docker: host.docker.internal (base
    # en tu PC), el nombre del servicio del Compose (db) o el host de la nube.
    DB_HOST: str = "localhost"
    DB_PORT: int = Field(default=5432, ge=1, le=65535)
    # Sin default: estos tres valores son obligatorios.
    DB_NAME: str = Field(min_length=1)
    DB_USER: str = Field(min_length=1)
    DB_PASSWORD: SecretStr = Field(min_length=1)  # Oculta la representación; no cifra.

    # Lista JSON en .env con los orígenes web permitidos por CORS (ver main.py).
    CORS_ORIGINS: list[str] = Field(default_factory=list)

    # Proxies propios (API central, balanceador): IPs exactas o rangos CIDR
    # ("172.30.0.0/24", ver platform_audit/proxies.py). Solo si la
    # conexión viene de uno de ellos se aceptan X-Forwarded-For, X-Trace-Id y
    # X-Parent-Operation-Id; si no, un cliente podría falsificarlos. Vacía = sin proxies.
    TRUSTED_PROXIES: list[str] = Field(default_factory=list)

    # Auth valida la identidad y los permisos de cada solicitud (app/api/dependencies.py).
    # URL interna, sin la ruta /auth: p. ej. http://auth:8000 en el Compose.
    AUTH_URL: str = Field(pattern=r"^https?://")
    # Espera máxima de cada llamada a auth; sin reintentos.
    AUTH_TIMEOUT_SECONDS: float = Field(default=30, gt=0, le=300)

    # Notificaciones: envía los correos del lote (app/services/send_service.py).
    # URL interna, sin la ruta /notificaciones: p. ej. http://notificaciones.internal:8000.
    NOTIFICACIONES_URL: str = Field(pattern=r"^https?://")
    # Espera por llamada. Crear el envío sube los PDFs y notificaciones arma todos
    # los mensajes antes de responder: más que los 30 s habituales. Sin reintentos
    # automáticos (reintentar un lote "sending" es manual y seguro).
    NOTIFICACIONES_TIMEOUT_SECONDS: float = Field(default=120, gt=0, le=300)
    # Plantilla de notificaciones por defecto al enviar un lote.
    DEFAULT_TEMPLATE_CODE: str = Field(default="payment_provider_summary", pattern=r"^[a-z0-9][a-z0-9_.-]{0,99}$")

    @field_validator("NOTIFICACIONES_URL")
    @classmethod
    def _notifications_url_without_path(cls, url: str) -> str:
        if url.rstrip("/").endswith("/notificaciones"):
            raise ValueError("NOTIFICACIONES_URL va sin la ruta /notificaciones (p. ej. http://127.0.0.1:8010)")
        return url

    # Lector de constancias (app/services/pdf_reader.py). Primero se lee el texto
    # del PDF; si tiene menos de OCR_MIN_TEXT_LENGTH caracteres (escaneado) y
    # OCR_ENABLED, se aplica OCR. El OCR necesita poppler y tesseract con el
    # idioma OCR_LANG instalados en la máquina o la imagen.
    OCR_ENABLED: bool = True
    OCR_LANG: str = Field(default="spa", pattern=r"^[a-z_+]{3,40}$")
    OCR_DPI: int = Field(default=250, ge=100, le=600)
    OCR_MIN_TEXT_LENGTH: int = Field(default=80, ge=1, le=10000)

    @field_validator("AUTH_URL")
    @classmethod
    def _auth_url_without_path(cls, url: str) -> str:
        if url.rstrip("/").endswith("/auth"):
            # El cliente ya agrega /auth/me/...: con /auth aquí llamaría a /auth/auth/... (404).
            raise ValueError("AUTH_URL va sin la ruta /auth (p. ej. http://127.0.0.1:8001)")
        return url

    # Las variables del proceso tienen prioridad sobre .env.
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        # Una variable vacía (PROJECT_NAME=) se trata como no definida y usa su default.
        env_ignore_empty=True,
    )


settings = Settings()
