from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from platform_audit import AuditConfig, AuditMiddleware

from app.core.audit import SENSITIVE_KEY_PARTS, SENSITIVE_KEYS
from app.core.config import settings
from app.core.db.connection import engine
from app.api.routes import (
    admin_router,
    api_keys_router,
    areas_router,
    auth_router,
    catalog_router,
    health_router,
    history_router,
    logs_router,
    me_router,
    members_router,
    positions_router,
    profile_router,
    roles_router,
    seed_router,
    users_router,
)

# Todo el servicio vive bajo /auth: la misma ruta directo y a través del API
# gateway (que reenvía /auth/* sin reescribir), y sin choques con otros servicios.
PREFIX = "/auth"

app = FastAPI(
    title=settings.PROJECT_NAME,
    docs_url=f"{PREFIX}/docs",
    redoc_url=f"{PREFIX}/redoc",
    openapi_url=f"{PREFIX}/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    # Direcciones de las aplicaciones web que pueden consumir la API.
    allow_origins=settings.CORS_ORIGINS,
    # Sin cookies: el access va en Authorization y el refresh en el body.
    allow_credentials=False,
    # Métodos permitidos desde los orígenes configurados.
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    # Headers permitidos en las solicitudes del navegador.
    # X-Company-Id: empresa activa. X-API-Key: credencial alternativa al Bearer.
    allow_headers=["Content-Type", "Authorization", "X-Company-Id", "X-API-Key"],
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
        # Qué se oculta: constantes de app/core/audit.py (paquete + propias de auth).
        sensitive_keys=SENSITIVE_KEYS,
        sensitive_key_parts=SENSITIVE_KEY_PARTS,
        # Sin log: documentación y comprobaciones frecuentes del gateway/Docker.
        exclude_paths=frozenset(
            f"{PREFIX}{path}"
            # for path in ("/health", "/ready")
            for path in ("/docs", "/redoc", "/openapi.json", "/health", "/ready")
        ),
    ),
)


api = APIRouter(prefix=PREFIX)
api.include_router(health_router.router)
api.include_router(users_router.router)
api.include_router(auth_router.router)
api.include_router(me_router.router)
api.include_router(profile_router.router)
api.include_router(catalog_router.router)
api.include_router(areas_router.router)
api.include_router(positions_router.router)
api.include_router(roles_router.router)
api.include_router(members_router.router)
api.include_router(history_router.router)
api.include_router(api_keys_router.router)
api.include_router(logs_router.router)
api.include_router(admin_router.router)
if settings.SEED_ENABLED:
    api.include_router(seed_router.router)

app.include_router(api)
