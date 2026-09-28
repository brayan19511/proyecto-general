from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from platform_audit import AuditConfig, AuditMiddleware

from app.api.routes import health_router
from app.core.audit import SENSITIVE_KEY_PARTS, SENSITIVE_KEYS
from app.core.config import settings
from app.core.db.connection import engine

# Todo el servicio vive bajo su prefijo: la misma ruta directo y a través de la
# API central (que reenvía /<servicio>/* sin reescribir). Al copiar la
# plantilla, cámbialo por el nombre del servicio.
PREFIX = "/base"

app = FastAPI(
    title=settings.PROJECT_NAME,
    docs_url=f"{PREFIX}/docs",
    redoc_url=f"{PREFIX}/redoc",
    openapi_url=f"{PREFIX}/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    # Sin cookies: las credenciales viajan en headers.
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
)

# Logs de cada solicitud en el schema audit (paquete compartido platform_audit).
# Se agrega después de CORS, así queda por fuera y mide la solicitud completa.
app.add_middleware(
    AuditMiddleware,
    config=AuditConfig(
        engine=engine,
        service=settings.SERVICE_NAME,
        service_version=settings.SERVICE_VERSION,
        enabled=settings.AUDIT_ENABLED,
        trusted_proxies=frozenset(settings.TRUSTED_PROXIES),
        max_body_bytes=settings.AUDIT_MAX_BODY_BYTES,
        sensitive_keys=SENSITIVE_KEYS,
        sensitive_key_parts=SENSITIVE_KEY_PARTS,
        # Sin log: documentación y comprobaciones frecuentes del gateway/Docker.
        exclude_paths=frozenset(
            f"{PREFIX}{path}"
            for path in ("/docs", "/redoc", "/openapi.json", "/health", "/ready")
        ),
    ),
)

api = APIRouter(prefix=PREFIX)
api.include_router(health_router.router)

app.include_router(api)
