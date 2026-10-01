from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from platform_audit import AuditConfig, AuditMiddleware

from app.api.routes import batches_router, health_router, providers_router, settings_router
from app.clients.auth_client import auth_client
from app.clients.notifications_client import notifications_client
from app.core.audit import SENSITIVE_KEY_PARTS, SENSITIVE_KEYS
from app.core.config import settings
from app.core.db.connection import engine
from app.services.errors import ServiceError

# Todo el servicio vive bajo su prefijo: la misma ruta directo y a través de la
# API central (que reenvía /<servicio>/* sin reescribir).
PREFIX = "/pagos-proveedores"


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    auth_client.close()  # Libera las conexiones hacia auth y notificaciones al apagar.
    notifications_client.close()


app = FastAPI(
    title=settings.PROJECT_NAME,
    lifespan=lifespan,
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
    allow_headers=["Content-Type", "Authorization", "X-Company-Id"],
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


@app.exception_handler(ServiceError)
def service_error_handler(_: Request, exc: ServiceError) -> JSONResponse:
    """Errores de negocio (app/services/errors.py) → {"detail", "code"?, ...extra} con su status."""
    content = {"detail": str(exc)}
    if exc.code is not None:
        content["code"] = exc.code
    content.update(exc.extra)
    return JSONResponse(status_code=exc.status_code, content=content)


api = APIRouter(prefix=PREFIX)
api.include_router(health_router.router)
api.include_router(providers_router.router)
api.include_router(batches_router.router)
api.include_router(settings_router.router)

app.include_router(api)
