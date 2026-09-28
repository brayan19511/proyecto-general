from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# Carpeta del servicio, independientemente de dónde ejecutes Python.
BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Lee configuración del entorno y del .env del servicio; no conecta a la BD."""

    # Plantilla: al copiarla, cambia estos defaults por los del nuevo servicio.
    PROJECT_NAME: str = "Base"
    # Identificación en los logs (audit.logs.service / service_version).
    SERVICE_NAME: str = "base"
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

    # Las variables del proceso tienen prioridad sobre .env.
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        # Una variable vacía (PROJECT_NAME=) se trata como no definida y usa su default.
        env_ignore_empty=True,
    )


settings = Settings()
