from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from platform_audit import AuditConfig, AuditMiddleware

from app.api.routes import auth_proxy, health_router
from app.clients.auth_client import auth_client
from app.core.audit import SENSITIVE_KEY_PARTS, SENSITIVE_KEYS
from app.core.config import settings
from app.core.db.connection import engine

# La central es el borde: sus rutas propias van en la raíz (/health, /ready,
# /docs). Cada servicio conserva su prefijo (/auth/...) y la central lo
# reenviará sin reescribir, así no hay choques.
PREFIX = ""


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    # Al apagar: cierra las conexiones abiertas hacia los servicios.
    if auth_client is not None:
        await auth_client.aclose()


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
    # X-Company-Id: empresa activa. X-API-Key: credencial alternativa al Bearer.
    allow_headers=["Content-Type", "Authorization", "X-Company-Id", "X-API-Key"],
    # Headers de respuesta que el JavaScript del cliente puede leer.
    expose_headers=["X-Trace-Id", "Retry-After"],
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
# Reenvío a auth: solo las rutas de auth_proxy.PUBLIC_ROUTES.
api.include_router(auth_proxy.router)

app.include_router(api)
