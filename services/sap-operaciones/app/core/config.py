from pathlib import Path
from typing import Literal

from cryptography.fernet import Fernet
from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Carpeta del servicio, independientemente de dónde ejecutes Python.
BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Lee configuración del entorno y del .env del servicio; no conecta a la BD."""

    PROJECT_NAME: str = "Operaciones SAP"
    # Identificación en los logs (audit.logs.service / service_version).
    SERVICE_NAME: str = "sap-operaciones"
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

    # Proxies propios (API central, balanceador): IPs exactas o rangos CIDR. Solo
    # si la conexión viene de uno de ellos se aceptan X-Forwarded-For, X-Trace-Id
    # y X-Parent-Operation-Id. Vacía = sin proxies.
    TRUSTED_PROXIES: list[str] = Field(default_factory=list)

    # Auth valida la identidad y los permisos de cada solicitud (app/api/dependencies.py).
    # URL interna, sin la ruta /auth: p. ej. http://auth:8000 en el Compose.
    AUTH_URL: str = Field(pattern=r"^https?://")
    # Espera máxima de cada llamada a auth; sin reintentos.
    AUTH_TIMEOUT_SECONDS: float = Field(default=30, gt=0, le=300)

    # SAP Business One Service Layer, p. ej. https://sap-host:50000/b1s/v1.
    # Sin valor el servicio arranca, pero no se pueden ejecutar trabajos (409).
    SAP_SERVICE_LAYER_URL: str | None = Field(default=None, pattern=r"^https?://")
    # Verificar el certificado TLS del Service Layer. Desactivarlo es una decisión
    # explícita del despliegue (certificado autofirmado sin CA instalable).
    SAP_VERIFY_TLS: bool = True
    # CA propia (ruta a un .pem dentro del contenedor) para un certificado interno.
    # Vacío = las CA del sistema. Solo se usa con SAP_VERIFY_TLS=true.
    SAP_CA_FILE: str | None = None
    # Espera para conectar y por cada llamada al Service Layer. Sin reintentos:
    # una llamada que modifica SAP y se corta queda "incierta" (ver worker).
    SAP_CONNECT_TIMEOUT_SECONDS: float = Field(default=10, gt=0, le=120)
    SAP_REQUEST_TIMEOUT_SECONDS: float = Field(default=120, gt=0, le=900)

    # Claves Fernet (lista JSON) para cifrar las claves SAP de los operadores
    # guardadas en los trabajos. Obligatoria. Se cifra con la primera y se
    # descifra con cualquiera (rotación: agregar la nueva al inicio y luego
    # retirar la vieja). Perder todas las claves deja ilegibles las guardadas.
    CREDENTIALS_ENCRYPTION_KEYS: list[SecretStr] = Field(min_length=1)

    # Desfase horario de las fechas en las descargas CSV (se guardan en UTC). Fijo,
    # sin base de zonas horarias: Perú (UTC-5) no tiene horario de verano.
    EXPORT_UTC_OFFSET_HOURS: int = Field(default=-5, ge=-12, le=14)

    # Límites de un trabajo.
    JOB_MAX_ITEMS: int = Field(default=50_000, ge=1, le=200_000)
    # Worker (python -m app.worker): cada cuántos segundos busca trabajos y por
    # cuánto toma un trabajo sin renovar. Si el worker cae, otro lo retoma al
    # vencer el bloqueo; el ítem que estaba en curso queda "uncertain".
    WORKER_POLL_SECONDS: float = Field(default=5, ge=1, le=300)
    WORKER_LOCK_SECONDS: int = Field(default=300, ge=30, le=3600)

    @field_validator("CREDENTIALS_ENCRYPTION_KEYS")
    @classmethod
    def _valid_fernet_keys(cls, keys: list[SecretStr]) -> list[SecretStr]:
        for position, key in enumerate(keys, start=1):
            try:
                Fernet(key.get_secret_value())
            except ValueError:
                # Sin mostrar la clave: solo su posición en la lista.
                raise ValueError(f"CREDENTIALS_ENCRYPTION_KEYS: la clave {position} no es una clave Fernet válida")
        return keys

    @model_validator(mode="after")
    def _check(self):
        if self.AUTH_URL.rstrip("/").endswith("/auth"):
            # El cliente ya agrega /auth/me: con /auth aquí llamaría a /auth/auth/me (404).
            raise ValueError("AUTH_URL va sin la ruta /auth (p. ej. http://127.0.0.1:8001)")
        return self

    # Las variables del proceso tienen prioridad sobre .env.
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        # Una variable vacía (PROJECT_NAME=) se trata como no definida y usa su default.
        env_ignore_empty=True,
    )


settings = Settings()
