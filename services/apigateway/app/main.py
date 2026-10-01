import asyncio
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from platform_audit import AuditConfig, AuditMiddleware

from app.api.routes import health_router, ip_blocks_router, logs_router, proxy, services_router
from app.clients.upstream import close_all
from app.core.ip_block_middleware import IpBlockMiddleware
from app.core.refresh import refresh_loop
from app.core.audit import SENSITIVE_KEY_PARTS, SENSITIVE_KEYS
from app.core.config import settings
from app.core.db.connection import engine

# La central es el borde: sus rutas propias van en la raíz (/health, /ready,
# /docs). Cada servicio conserva su prefijo (/auth/..., /libro-mayor/...) y la central lo
# reenviará sin reescribir, así no hay choques.
PREFIX = ""


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Relee en segundo plano el estado de los servicios y la lista negra (app/core/refresh.py).
    refresh = asyncio.create_task(refresh_loop())
    yield
    refresh.cancel()
    # Al apagar: cierra las conexiones abiertas hacia los servicios.
    await close_all()


app = FastAPI(
    title=settings.PROJECT_NAME,
    lifespan=lifespan,
    docs_url=f"{PREFIX}/docs",
    redoc_url=f"{PREFIX}/redoc",
    openapi_url=f"{PREFIX}/openapi.json",
)

# Orden: el último agregado queda por fuera. Así: Audit → CORS → lista negra → rutas.
# El bloqueo queda en los logs (con la IP) y el navegador puede leer el 403.
if settings.IP_BLOCKS_ENABLED:
    app.add_middleware(IpBlockMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    # Sin cookies: las credenciales viajan en headers.
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    # X-Company-Id: empresa activa. X-API-Key: credencial alternativa al Bearer.
    allow_headers=["Content-Type", "Authorization", "X-Company-Id", "X-API-Key"],
    # Headers de respuesta que el JavaScript del cliente puede leer.
    # Content-Disposition: nombre del archivo en descargas (CSV de libro-mayor).
    expose_headers=["X-Trace-Id", "Retry-After", "Content-Disposition"],
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
# Administración de la central (/gateway/admin/...): solo administrador de plataforma.
api.include_router(logs_router.router)
api.include_router(services_router.router)
api.include_router(ip_blocks_router.router)
# Reenvío a los servicios: solo las rutas de app/core/public_routes.py. Va
# al final: las rutas propias de la central tienen prioridad.
api.include_router(proxy.router)

app.include_router(api)
