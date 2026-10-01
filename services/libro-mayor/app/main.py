from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from platform_audit import AuditConfig, AuditMiddleware

from app.api.routes import (
    accounts_router,
    cost_centers_router,
    health_router,
    ledger_router,
    live_queries_router,
    logs_router,
    rules_router,
    sap_company_router,
    seed_router,
    sync_runs_router,
)
from app.clients.auth_client import auth_client
from app.core.audit import SENSITIVE_KEY_PARTS, SENSITIVE_KEYS
from app.core.config import settings
from app.core.db.connection import engine
from app.services.errors import ServiceError

# Todo el servicio vive bajo su prefijo: la misma ruta directo y a través de la
# API central (que reenvía /<servicio>/* sin reescribir).
PREFIX = "/libro-mayor"


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    auth_client.close()  # Libera las conexiones hacia auth al apagar.


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
        sensitive_keys=SENSITIVE_KEYS,
        sensitive_key_parts=SENSITIVE_KEY_PARTS,
        # Sin log: documentación y comprobaciones frecuentes del gateway/Docker.
        exclude_paths=frozenset(
            f"{PREFIX}{path}"
            for path in ("/docs", "/redoc", "/openapi.json", "/health", "/ready")
        ),
    ),
)



# Compresión gzip de respuestas de más de 1 KB (si el cliente la acepta). Va
# por fuera del middleware de logs: los logs ven el cuerpo sin comprimir.
# JSON y CSV grandes (líneas) pesan ~10 veces menos en la red.
app.add_middleware(GZipMiddleware, minimum_size=1024)

@app.exception_handler(ServiceError)
def service_error_handler(_: Request, exc: ServiceError) -> JSONResponse:
    """Errores de negocio de los servicios (app/services/errors.py) → HTTP."""
    return JSONResponse(status_code=exc.status_code, content={"detail": str(exc)})


api = APIRouter(prefix=PREFIX)
api.include_router(health_router.router)
api.include_router(accounts_router.router)
api.include_router(sap_company_router.router)
api.include_router(sync_runs_router.router)
api.include_router(sync_runs_router.status_router)
api.include_router(ledger_router.router)
api.include_router(cost_centers_router.router)
api.include_router(rules_router.router)
api.include_router(live_queries_router.router)
api.include_router(logs_router.router)
# Sin SEED_ENABLED=true la ruta no existe (404): se habilita solo para ejecutarla.
if settings.SEED_ENABLED:
    api.include_router(seed_router.router)

app.include_router(api)
