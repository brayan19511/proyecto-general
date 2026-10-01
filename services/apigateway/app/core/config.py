from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Carpeta del servicio, independientemente de dónde ejecutes Python.
BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Lee configuración del entorno y del .env del servicio; no conecta a la BD."""

    # Datos mostrados en /docs y en los logs.
    PROJECT_NAME: str = "API central"
    # Identificación en los logs (audit.logs.service / service_version).
    SERVICE_NAME: str = "apigateway"
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

    # Proxies delante de la central (Nginx, balanceador): IPs exactas o rangos
    # CIDR. Solo si la conexión viene de uno de ellos se aceptan X-Forwarded-For,
    # X-Trace-Id y X-Parent-Operation-Id; si no, un cliente podría falsificarlos.
    # Vacía = los clientes llegan directo.
    TRUSTED_PROXIES: list[str] = Field(default_factory=list)

    # Auth habilitado en la central. false = /auth/* responde 503 sin llegar a
    # auth; auth sigue corriendo (no se detiene ni se toca). Cambiarlo requiere
    # reiniciar solo la central. Ver docs/modulos-y-administracion.md.
    AUTH_ENABLED: bool = True
    # Auth: dirección INTERNA (la que usa la central, no el cliente). Sin
    # default: ninguna URL de otro servicio se fija en el código. Obligatoria
    # si AUTH_ENABLED=true. Ejemplos: http://127.0.0.1:8000 (local),
    # http://auth.internal:8000 (Compose).
    AUTH_URL: str | None = Field(default=None, pattern=r"^https?://")
    # Espera máxima por cada llamada a auth (conectar, enviar y recibir). Sin
    # reintentos: si se agota, la central responde 504.
    AUTH_TIMEOUT_SECONDS: float = Field(default=30, gt=0, le=300)

    # Libro mayor / gastos (/libro-mayor/*). Mismo patrón que auth, pero apagado
    # por defecto: se publica solo cuando se configura. Con false, /libro-mayor/*
    # responde 503 sin llegar al servicio. También se puede apagar desde el panel
    # (gateway.service_states) sin reiniciar.
    LIBRO_MAYOR_ENABLED: bool = False
    # Dirección INTERNA de libro-mayor. Ejemplos: http://127.0.0.1:8002 (local),
    # http://libro-mayor.internal:8000 (Compose). Obligatoria si está habilitado.
    LIBRO_MAYOR_URL: str | None = Field(default=None, pattern=r"^https?://")
    # Espera por defecto de sus rutas. Las que tardan más tienen su propio
    # timeout en app/core/public_routes.py (p. ej. /libro-mayor/live-queries).
    LIBRO_MAYOR_TIMEOUT_SECONDS: float = Field(default=30, gt=0, le=300)

    # Notificaciones (/notificaciones/*). Mismo patrón que libro-mayor: apagado
    # por defecto, también se apaga desde el panel sin reiniciar.
    NOTIFICACIONES_ENABLED: bool = False
    # Dirección INTERNA. Ejemplos: http://127.0.0.1:8010 (local),
    # http://notificaciones.internal:8000 (Compose). Obligatoria si está habilitado.
    NOTIFICACIONES_URL: str | None = Field(default=None, pattern=r"^https?://")
    # Espera por defecto de sus rutas. POST /notificaciones/dispatches tiene la
    # suya en app/core/public_routes.py (subida de adjuntos).
    NOTIFICACIONES_TIMEOUT_SECONDS: float = Field(default=30, gt=0, le=300)

    # Pagos a proveedores (/pagos-proveedores/*). Mismo patrón: apagado por
    # defecto, también se apaga desde el panel sin reiniciar.
    PAGOS_PROVEEDORES_ENABLED: bool = False
    # Dirección INTERNA. Ejemplos: http://127.0.0.1:8012 (local),
    # http://pagos-proveedores.internal:8000 (Compose). Obligatoria si está habilitado.
    PAGOS_PROVEEDORES_URL: str | None = Field(default=None, pattern=r"^https?://")
    # Espera por defecto de sus rutas. Crear y enviar lotes tienen la suya en
    # app/core/public_routes.py (lectura de PDFs con OCR y envío a notificaciones).
    PAGOS_PROVEEDORES_TIMEOUT_SECONDS: float = Field(default=30, gt=0, le=300)

    # Cada cuántos segundos la central relee de la base el estado de los
    # servicios (gateway.service_states). Un cambio desde la administración
    # aplica en todas las réplicas en ≤ este tiempo, sin reiniciar.
    GATEWAY_STATE_TTL_SECONDS: float = Field(default=5, ge=1, le=300)

    # Lista negra de IPs (gateway.ip_blocks). false = no se aplica ningún bloqueo:
    # interruptor para recuperar el acceso si un bloqueo deja fuera a quien no
    # debía. Cambiarlo requiere reiniciar la central.
    IP_BLOCKS_ENABLED: bool = True

    @model_validator(mode="after")
    def check_services(self):
        if self.AUTH_ENABLED and not self.AUTH_URL:
            raise ValueError("Con AUTH_ENABLED=true falta AUTH_URL")
        if self.LIBRO_MAYOR_ENABLED and not self.LIBRO_MAYOR_URL:
            raise ValueError("Con LIBRO_MAYOR_ENABLED=true falta LIBRO_MAYOR_URL")
        if self.NOTIFICACIONES_ENABLED and not self.NOTIFICACIONES_URL:
            raise ValueError("Con NOTIFICACIONES_ENABLED=true falta NOTIFICACIONES_URL")
        if self.PAGOS_PROVEEDORES_ENABLED and not self.PAGOS_PROVEEDORES_URL:
            raise ValueError("Con PAGOS_PROVEEDORES_ENABLED=true falta PAGOS_PROVEEDORES_URL")
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
