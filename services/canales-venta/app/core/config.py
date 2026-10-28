from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Carpeta del servicio, independientemente de dónde ejecutes Python.
BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Lee configuración del entorno y de canales-venta.env (carpeta del servicio); no conecta a la BD."""

    PROJECT_NAME: str = "Canales de venta"
    # Identificación en los logs (audit.logs.service / service_version).
    SERVICE_NAME: str = "canales-venta"
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

    # Lista JSON en canales-venta.env con los orígenes web permitidos por CORS (ver main.py).
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

    # Código en auth de la única empresa dueña de lastmiller (p. ej. RASH). Las
    # tablas de Ofisis no distinguen empresas: otra empresa, aunque tenga los
    # permisos lastmiller.*, recibe 404. Vacío = lastmiller deshabilitado (409).
    LASTMILLER_COMPANY_CODE: str | None = None
    # Filas por transacción al escribir en Ofisis (cargas masivas). Cada lote se
    # confirma por separado: lotes chicos = bloqueos cortos para lastmiller.
    # Bajo el umbral de ~5000 bloqueos en que SQL Server bloquea la tabla entera.
    LASTMILLER_WRITE_BATCH_SIZE: int = Field(default=200, ge=1, le=1000)

    # Ofisis (SQL Server externo, base EcommDB): tablas de SKU y promociones de
    # lastmiller. No es una base propia: ver app/external/ofisis.py.
    # Sin OFISIS_HOST el servicio arranca igual; las operaciones de lastmiller
    # fallan con un error claro. Con OFISIS_HOST, usuario y contraseña son obligatorios.
    OFISIS_HOST: str | None = None
    OFISIS_PORT: int = Field(default=1433, ge=1, le=65535)
    OFISIS_USER: str | None = None
    OFISIS_PASSWORD: SecretStr | None = None
    OFISIS_DATABASE: str = "EcommDB"
    # Nombre del driver ODBC instalado. La imagen Docker trae el 18; en Windows
    # puede ser "ODBC Driver 17 for SQL Server" si es el que tienes.
    OFISIS_DRIVER: str = "ODBC Driver 18 for SQL Server"
    # Cifrado y validación del certificado activos por defecto. Si el servidor no
    # tiene un certificado válido, desactivarlos es una decisión explícita del despliegue.
    OFISIS_ENCRYPT: bool = True
    OFISIS_TRUST_SERVER_CERTIFICATE: bool = False
    # Límites para no quedar esperando a una base externa:
    # - CONNECT: segundos para abrir la conexión (login).
    # - QUERY: segundos máximos por consulta; al superarlos se cancela.
    # - LOCK: milisegundos esperando un bloqueo de otro proceso antes de fallar.
    OFISIS_CONNECT_TIMEOUT_SECONDS: int = Field(default=10, ge=1, le=60)
    OFISIS_QUERY_TIMEOUT_SECONDS: int = Field(default=30, ge=1, le=300)
    OFISIS_LOCK_TIMEOUT_MS: int = Field(default=5000, ge=0, le=60000)

    @model_validator(mode="after")
    def check_dependencies(self):
        if self.AUTH_URL.rstrip("/").endswith("/auth"):
            # El cliente ya agrega /auth/me: con /auth aquí llamaría a /auth/auth/me (404).
            raise ValueError("AUTH_URL va sin la ruta /auth (p. ej. http://127.0.0.1:8001)")
        if self.OFISIS_HOST and not (self.OFISIS_USER and self.OFISIS_PASSWORD):
            raise ValueError("Con OFISIS_HOST faltan OFISIS_USER y/o OFISIS_PASSWORD")
        return self

    # Las variables del proceso tienen prioridad sobre canales-venta.env (en Docker llegan con env_file).
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / "canales-venta.env",
        env_file_encoding="utf-8",
        extra="ignore",
        # Una variable vacía (PROJECT_NAME=) se trata como no definida y usa su default.
        env_ignore_empty=True,
    )


settings = Settings()
