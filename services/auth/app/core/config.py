from pathlib import Path
from typing import Literal

from pydantic import EmailStr, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Carpeta services/auth, independientemente de dónde ejecutes Python.
BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Lee configuración del entorno y de services/auth/.env; no conecta a la BD."""

    PROJECT_NAME: str = "Auth"
    # Identificación en los logs (audit.logs.service / service_version).
    SERVICE_NAME: str = "auth"
    SERVICE_VERSION: str = "0.1.0"

    # Logs (paquete platform_audit, schema audit). AUDIT_ENABLED=false los apaga
    # sin tocar el código; AUDIT_MAX_BODY_BYTES limita cuánto body se guarda.
    AUDIT_ENABLED: bool = True
    AUDIT_MAX_BODY_BYTES: int = Field(default=4096, ge=0, le=65536)

    # Motor seleccionable por despliegue. No garantiza portabilidad de los modelos.
    DB_ENGINE: Literal["postgresql", "mssql"] = "postgresql"
    DB_HOST: str = "localhost"  # Desde Docker sería el nombre del servicio de BD.
    DB_PORT: int = Field(default=5432, ge=1, le=65535)
    # Sin default: estos tres valores son obligatorios.
    DB_NAME: str = Field(min_length=1)
    DB_USER: str = Field(min_length=1)
    DB_PASSWORD: SecretStr = Field(min_length=1)  # Oculta la representación; no cifra.

    # Lista JSON en .env con los orígenes web permitidos por CORS (ver main.py).
    CORS_ORIGINS: list[str] = Field(default_factory=list)

    # JWT (RS256). La clave privada firma y solo la tiene auth; la pública
    # verifica y puede entregarse a otros servicios. Generar con scripts/generate_jwt_keys.py.
    JWT_PRIVATE_KEY_FILE: Path = BASE_DIR / "secrets" / "jwt_private.pem"
    JWT_PUBLIC_KEY_FILE: Path = BASE_DIR / "secrets" / "jwt_public.pem"
    # Claims iss (quién emite) y aud (para quién es); los consumidores verifican ambos.
    JWT_ISSUER: str = "auth"
    JWT_AUDIENCE: str = "platform"
    ACCESS_TOKEN_MINUTES: int = Field(default=15, ge=1, le=60)

    # Sesión absoluta desde el login y máximo simultáneo cuando
    # users.max_sessions es NULL (el valor del usuario tiene prioridad).
    SESSION_HOURS: int = Field(default=5, ge=1, le=24)
    MAX_SESSIONS: int = Field(default=3, ge=1)

    # Bloqueo de login: LOGIN_MAX_FAILURES contraseñas fallidas del mismo email
    # desde la misma IP dentro de LOGIN_WINDOW_MINUTES bloquean esa combinación
    # durante LOGIN_BLOCK_MINUTES. Por email + IP: un tercero no puede bloquear
    # a otro usuario desde su propia IP.
    LOGIN_MAX_FAILURES: int = Field(default=5, ge=1, le=100)
    LOGIN_WINDOW_MINUTES: int = Field(default=15, ge=1, le=1440)
    LOGIN_BLOCK_MINUTES: int = Field(default=15, ge=1, le=1440)

    # Límites de volumen por IP (todas las solicitudes, correctas o no).
    # Protegen de avalanchas aunque auth se exponga sin la API central; la
    # central tendrá sus propios límites en otro espacio de nombres.
    REGISTER_IP_LIMIT: int = Field(default=10, ge=1)  # registros por IP...
    REGISTER_IP_WINDOW_MINUTES: int = Field(default=60, ge=1)  # ...en esta ventana.
    LOGIN_IP_LIMIT: int = Field(default=30, ge=1)
    LOGIN_IP_WINDOW_MINUTES: int = Field(default=15, ge=1)
    REFRESH_IP_LIMIT: int = Field(default=120, ge=1)
    REFRESH_IP_WINDOW_MINUTES: int = Field(default=15, ge=1)

    # Proxies propios (API central, balanceador): IPs exactas ("10.0.0.5") o
    # rangos CIDR ("172.30.0.0/24"). Solo si la conexión viene de uno de ellos
    # se leen X-Forwarded-For, X-Trace-Id y X-Parent-Operation-Id; si no, un
    # cliente podría falsificarlos. Un rango confía en todo lo que contiene:
    # usar una red exclusiva de la central y auth. Lista JSON; vacía = sin proxies.
    TRUSTED_PROXIES: list[str] = Field(default_factory=list)

    # Máximo de API keys activas y vigentes por usuario (entre todas sus empresas).
    API_KEYS_MAX: int = Field(default=5, ge=1, le=50)

    # Bootstrap: la ruta /seed solo se registra si esto es true.
    SEED_ENABLED: bool = False
    # Secreto que debe enviar quien ejecuta el seed. Solo necesario si está habilitado.
    SEED_TOKEN: SecretStr | None = Field(default=None, min_length=10)
    # Admin inicial: solo se usan con SEED_ENABLED=true; el validador los exige.
    SEED_ADMIN_EMAIL: EmailStr | None = None
    # Mismos límites que Password en schemas/user.py.
    SEED_ADMIN_PASSWORD: SecretStr | None = Field(
        default=None, min_length=3, max_length=100
    )

    @model_validator(mode="after")
    def check_seed(self):
        if self.SEED_ENABLED:
            missing = [
                name
                for name in ("SEED_TOKEN", "SEED_ADMIN_EMAIL", "SEED_ADMIN_PASSWORD")
                if getattr(self, name) is None
            ]
            if missing:
                raise ValueError(f"Con SEED_ENABLED=true faltan: {', '.join(missing)}")
        return self

    # Las variables del proceso tienen prioridad sobre .env.
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        # Una variable vacía (SEED_TOKEN=) se trata como no definida y usa su default.
        env_ignore_empty=True,
    )


settings = Settings()
