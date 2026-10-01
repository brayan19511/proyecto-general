from ipaddress import ip_network
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from cryptography.fernet import Fernet
from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Carpeta del servicio, independientemente de dónde ejecutes Python.
BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Lee configuración del entorno y del .env del servicio; no conecta a la BD."""

    PROJECT_NAME: str = "Notificaciones"
    # Identificación en los logs (audit.logs.service / service_version).
    SERVICE_NAME: str = "notificaciones"
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

    @field_validator("AUTH_URL")
    @classmethod
    def _auth_url_without_path(cls, url: str) -> str:
        if url.rstrip("/").endswith("/auth"):
            # El cliente ya agrega /auth/me/...: con /auth aquí llamaría a /auth/auth/... (404).
            raise ValueError("AUTH_URL va sin la ruta /auth (p. ej. http://127.0.0.1:8001)")
        return url

    # Claves Fernet (lista JSON) para cifrar las contraseñas SMTP guardadas en la
    # base. Obligatoria: sin ella el servicio no arranca. Se cifra con la primera
    # y se descifra con cualquiera (rotación: agregar la nueva al inicio,
    # re-cifrar y luego retirar la vieja). Perder todas las claves obliga a
    # volver a ingresar las contraseñas.
    SMTP_ENCRYPTION_KEYS: list[SecretStr] = Field(min_length=1)

    # Conexiones SMTP salientes (app/services/smtp_transport.py). Las define quien
    # despliega, no el admin de una empresa: así una cuenta SMTP no puede usarse
    # para llegar a servicios internos (SSRF).
    # Puertos que una cuenta puede usar (se valida al guardar y al conectar).
    SMTP_ALLOWED_PORTS: list[int] = Field(default_factory=lambda: [25, 465, 587, 2525])
    # Redes internas permitidas (CIDR, lista JSON), p. ej. ["192.168.30.199/32"]
    # para un relay propio. Vacía = solo direcciones públicas.
    SMTP_ALLOWED_PRIVATE_NETWORKS: list[str] = Field(default_factory=list)
    # CA adicional (archivo PEM) para relays con certificado de una CA interna.
    # Se suma a las CA públicas del sistema. Vacío = solo las públicas.
    SMTP_CA_BUNDLE: Path | None = None
    # Hosts (tal como se guardan en la cuenta) a los que se conecta con TLS SIN
    # verificar el certificado. Cifra, pero no impide suplantar al servidor:
    # solo para relays internos que no admiten otra opción. Vacía = verificar siempre.
    SMTP_TLS_UNVERIFIED_HOSTS: list[str] = Field(default_factory=list)

    # Worker de envío (python -m app.worker, app/services/delivery_service.py).
    # Segundos entre búsquedas cuando no hay mensajes pendientes.
    WORKER_POLL_SECONDS: int = Field(default=5, ge=1, le=300)
    # Duración del bloqueo de un mensaje tomado. Debe superar el envío más lento
    # (conexión + 25 MB por todas las cuentas). Si vence con el mensaje en
    # sending, pasa a uncertain (el worker pudo morir después de transmitirlo).
    WORKER_LOCK_SECONDS: int = Field(default=600, ge=60, le=3600)
    # Espera antes de cada reintento automático, en segundos (lista JSON). Su
    # largo es la cantidad de reintentos: acuerdo 3 (4 intentos en total).
    # Esperas de 1, 5 y 15 minutos (confirmadas por el usuario, 2026-10-01).
    RETRY_DELAYS_SECONDS: list[int] = Field(default_factory=lambda: [60, 300, 900])

    # Retención (lo ejecuta el worker cada RETENTION_INTERVAL_SECONDS,
    # app/services/retention_service.py). Plazos desde el último intento de un
    # mensaje failed o uncertain sin reproceso. Acuerdo: aviso a las 48 h y
    # cancelación (con purga de adjuntos) a las 72 h.
    RETENTION_NOTICE_AFTER_HOURS: int = Field(default=48, ge=1, le=24 * 30)
    RETENTION_CANCEL_AFTER_HOURS: int = Field(default=72, ge=1, le=24 * 30)
    RETENTION_INTERVAL_SECONDS: int = Field(default=600, ge=60, le=86400)
    # Zona horaria de las fechas que muestra el aviso (los plazos se calculan en UTC).
    NOTICE_TIMEZONE: str = "America/Lima"
    # Enlace opcional "Revisar el envío" en el aviso. {dispatch_id} se reemplaza
    # por el id del envío, p. ej. https://plataforma.example/notificaciones/{dispatch_id}.
    # Vacío = el aviso no lleva enlace (hoy no hay pantalla en el front).
    NOTICE_LINK_TEMPLATE: str | None = Field(default=None, pattern=r"^https://.*\{dispatch_id\}")

    @field_validator("NOTICE_TIMEZONE")
    @classmethod
    def _valid_timezone(cls, name: str) -> str:
        try:
            ZoneInfo(name)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError(f"NOTICE_TIMEZONE: zona horaria desconocida '{name}'")
        return name

    @model_validator(mode="after")
    def _notice_before_cancel(self):
        if self.RETENTION_NOTICE_AFTER_HOURS >= self.RETENTION_CANCEL_AFTER_HOURS:
            raise ValueError("RETENTION_NOTICE_AFTER_HOURS debe ser menor que RETENTION_CANCEL_AFTER_HOURS")
        return self

    @field_validator("RETRY_DELAYS_SECONDS")
    @classmethod
    def _valid_delays(cls, delays: list[int]) -> list[int]:
        if any(not 1 <= delay <= 86400 for delay in delays):
            raise ValueError("RETRY_DELAYS_SECONDS: segundos entre 1 y 86400")
        return delays

    # Carga inicial (POST /notificaciones/admin/seed, app/seeds/data.py). La ruta
    # solo existe con true; habilitar solo para ejecutarla y volver a false.
    SEED_ENABLED: bool = False

    # Tamaño máximo de un mensaje MIME completo (cuerpo + adjuntos codificados), en
    # bytes. Acuerdo: 25 MB; los servidores SMTP miden el mensaje completo.
    MESSAGE_MAX_BYTES: int = Field(default=25 * 1024 * 1024, ge=1024, le=100 * 1024 * 1024)

    @field_validator("SMTP_ALLOWED_PORTS")
    @classmethod
    def _valid_ports(cls, ports: list[int]) -> list[int]:
        if not ports or any(not 1 <= port <= 65535 for port in ports):
            raise ValueError("SMTP_ALLOWED_PORTS: lista no vacía de puertos entre 1 y 65535")
        return ports

    @field_validator("SMTP_ALLOWED_PRIVATE_NETWORKS")
    @classmethod
    def _valid_networks(cls, networks: list[str]) -> list[str]:
        for network in networks:
            try:
                ip_network(network, strict=False)
            except ValueError:
                raise ValueError(f"SMTP_ALLOWED_PRIVATE_NETWORKS: '{network}' no es una red CIDR válida")
        return networks

    @field_validator("SMTP_CA_BUNDLE")
    @classmethod
    def _ca_bundle_exists(cls, path: Path | None) -> Path | None:
        if path is not None and not path.is_file():
            raise ValueError(f"SMTP_CA_BUNDLE: no existe el archivo {path}")
        return path

    @field_validator("SMTP_TLS_UNVERIFIED_HOSTS")
    @classmethod
    def _lowercase_hosts(cls, hosts: list[str]) -> list[str]:
        return [host.strip().lower() for host in hosts]

    @field_validator("SMTP_ENCRYPTION_KEYS")
    @classmethod
    def _valid_fernet_keys(cls, keys: list[SecretStr]) -> list[SecretStr]:
        for position, key in enumerate(keys, start=1):
            try:
                Fernet(key.get_secret_value())
            except ValueError:
                # Sin mostrar la clave: solo su posición en la lista.
                raise ValueError(f"SMTP_ENCRYPTION_KEYS: la clave {position} no es una clave Fernet válida")
        return keys

    # Las variables del proceso tienen prioridad sobre .env.
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        # Una variable vacía (PROJECT_NAME=) se trata como no definida y usa su default.
        env_ignore_empty=True,
    )


settings = Settings()
