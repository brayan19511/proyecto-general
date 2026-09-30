from datetime import time
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Carpeta del servicio, independientemente de dónde ejecutes Python.
BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Lee configuración del entorno y del .env del servicio; no conecta a la BD."""

    PROJECT_NAME: str = "Libro mayor"
    # Identificación en los logs (audit.logs.service / service_version).
    SERVICE_NAME: str = "libro-mayor"
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

    # SAP HANA (solo lectura). Sin SAP_HOST, SAP queda deshabilitado: el servicio
    # arranca y administra cuentas, pero no consulta ni sincroniza. El schema y
    # la vista de cada empresa están en libro_mayor.sap_companies, no aquí.
    SAP_HOST: str | None = None
    SAP_PORT: int = Field(default=30015, ge=1, le=65535)
    SAP_USER: str | None = None  # Usuario con permiso SELECT sobre las vistas, nada más.
    SAP_PASSWORD: SecretStr | None = None
    # TLS hacia HANA. Si el servidor no lo admite, SAP_ENCRYPT=false (tráfico sin cifrar).
    SAP_ENCRYPT: bool = True
    SAP_VALIDATE_CERTIFICATE: bool = True
    # Espera para abrir la conexión y máximo por consulta (una carga puede tardar).
    SAP_CONNECT_TIMEOUT_SECONDS: int = Field(default=30, ge=1, le=300)
    SAP_QUERY_TIMEOUT_SECONDS: int = Field(default=300, ge=1, le=3600)

    # Sincronización (worker: python -m app.worker).
    # Máximo de días por ejecución manual: acota el trabajo de una sola solicitud.
    SYNC_MAX_DAYS: int = Field(default=366, ge=1, le=3660)
    # Cada cuántos segundos el worker busca ejecuciones pendientes.
    SYNC_POLL_SECONDS: int = Field(default=10, ge=1, le=3600)
    # Una ejecución "running" sin avance (heartbeat) en este tiempo se marca
    # fallida como interrumpida (worker caído). Debe superar lo que tarda un día.
    SYNC_STALE_MINUTES: int = Field(default=30, ge=1, le=1440)

    # Reclasificación: líneas por lote (una transacción por lote).
    CLASSIFY_BATCH_SIZE: int = Field(default=2000, ge=100, le=50000)
    # Consultas en vivo a SAP (POST /live-queries): responden en la misma solicitud.
    LIVE_QUERY_MAX_DAYS: int = Field(default=366, ge=1, le=1830)
    LIVE_QUERY_MAX_ACCOUNTS: int = Field(default=20, ge=1, le=200)
    # Consultas a SAP a la vez en este proceso, sumando TODAS las solicitudes:
    # protege a SAP aunque lleguen muchas consultas juntas.
    LIVE_QUERY_PARALLEL: int = Field(default=4, ge=1, le=32)
    # Máximo de líneas en una respuesta con detalle (view=full). El resumen no
    # guarda líneas en memoria y no tiene este límite.
    LIVE_QUERY_MAX_LINES: int = Field(default=100_000, ge=100, le=2_000_000)
    # Tiempo máximo de una consulta; pasado, 504. La API central debe tener un
    # timeout mayor para esta ruta (su default es 30 s).
    LIVE_QUERY_TIMEOUT_SECONDS: int = Field(default=120, ge=5, le=1800)

    # Horario del worker (fase C): horas locales HH:MM separadas por coma, en
    # SAP_TIMEZONE. "off" = sin horario (solo ejecuciones manuales); vacío usa
    # el default (una variable vacía se trata como no definida). En cada turno
    # se sincroniza cada cuenta activa (carga inicial o delta).
    SYNC_SCHEDULE: str = "06:00,10:00,14:00,18:00"
    # Zona horaria del servidor SAP: sus fechas vienen en hora local sin zona.
    # Define qué día es "hoy" para SAP (marca de agua) y el horario de arriba.
    SAP_TIMEZONE: str = "America/Lima"

    # Carga inicial (POST /libro-mayor/admin/seed). Habilitar solo para ejecutarla.
    SEED_ENABLED: bool = False

    @model_validator(mode="after")
    def check_sap(self):
        if self.AUTH_URL.rstrip("/").endswith("/auth"):
            # El cliente ya agrega /auth/me: con /auth aquí llamaría a /auth/auth/me (404).
            raise ValueError("AUTH_URL va sin la ruta /auth (p. ej. http://127.0.0.1:8001)")
        if self.SAP_HOST and not (self.SAP_USER and self.SAP_PASSWORD):
            raise ValueError("Con SAP_HOST faltan SAP_USER y/o SAP_PASSWORD")
        try:
            ZoneInfo(self.SAP_TIMEZONE)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError(f"SAP_TIMEZONE desconocida: {self.SAP_TIMEZONE}") from None
        self.schedule_times  # Valida el formato al arrancar.
        return self

    @property
    def schedule_times(self) -> list[time]:
        """SYNC_SCHEDULE como horas ordenadas y sin repetir ([] = "off", sin horario)."""
        if self.SYNC_SCHEDULE.strip().lower() == "off":
            return []
        try:
            return sorted({time.fromisoformat(part.strip()) for part in self.SYNC_SCHEDULE.split(",") if part.strip()})
        except ValueError:
            raise ValueError(f"SYNC_SCHEDULE inválido (HH:MM,HH:MM… u off): {self.SYNC_SCHEDULE}") from None

    @property
    def sap_zone(self) -> ZoneInfo:
        return ZoneInfo(self.SAP_TIMEZONE)

    # Las variables del proceso tienen prioridad sobre .env.
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        # Una variable vacía (PROJECT_NAME=) se trata como no definida y usa su default.
        env_ignore_empty=True,
    )


settings = Settings()
