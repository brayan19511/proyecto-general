"""Reenvío de solicitudes públicas a auth.

La central no aplica reglas de auth: reenvía la solicitud y devuelve la
respuesta tal cual (un 401 o un 429 de auth no es una falla de la central).
Solo se reenvía lo que está en PUBLIC_ROUTES; lo demás responde 404 sin llegar
a auth. Con AUTH_ENABLED=false, las rutas publicadas responden 503 sin llegar a auth. El path no se reescribe: /auth/login en la central es /auth/login en auth.

Correlación en los logs (schema audit): el middleware de la central ya creó el
trace_id y su operación; se envían a auth como X-Trace-Id y
X-Parent-Operation-Id, y auth los acepta porque la conexión viene de la
central (su TRUSTED_PROXIES).
"""

import httpx
from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from app.clients.auth_client import auth_client
from app.core import services
from app.core.tracing import upstream_headers

router = APIRouter(tags=["auth"])

READ = {"GET"}
WRITE = {"GET", "POST", "PATCH", "DELETE"}

# Rutas de auth publicadas por la central: (prefijo, métodos). Un prefijo
# incluye todo lo que cuelga de él ("/auth/me" cubre "/auth/me/sessions/...").
# Para dejar de publicar algo: borra o comenta su línea, o quita un método.
# Para ser más fino, agrega una línea más específica y quita la general.
# Cada cambio requiere redesplegar la central.
PUBLIC_ROUTES: tuple[tuple[str, set[str]], ...] = (
    # Comprobaciones y documentación de auth.
    ("/auth/health", READ),
    ("/auth/ready", READ),
    ("/auth/docs", READ),
    ("/auth/redoc", READ),
    ("/auth/openapi.json", READ),
    # Registro, login y sesión.
    ("/auth/users", {"POST"}),
    ("/auth/login", {"POST"}),
    ("/auth/refresh", {"POST"}),
    ("/auth/logout", {"POST"}),
    # Cuenta propia: perfil, documentos, sesiones, permisos y contraseña.
    ("/auth/me", WRITE),
    ("/auth/catalog", READ),
    # Organización de la empresa activa.
    ("/auth/areas", WRITE),
    ("/auth/positions", WRITE),
    ("/auth/roles", WRITE),
    ("/auth/members", WRITE),
    ("/auth/history", READ),
    ("/auth/api-keys", WRITE),
    # Administración de plataforma (incluye /auth/admin/logs).
    ("/auth/admin", WRITE),
    # Bootstrap: auth solo registra la ruta con SEED_ENABLED=true y exige X-Seed-Token.
    ("/auth/seed", {"POST"}),
)

# Headers que pasan del cliente a auth (lista positiva). Cookie, Host y otros
# no se reenvían. X-Forwarded-For y la traza los arma la central.
REQUEST_HEADERS = ("content-type", "accept", "authorization", "x-company-id", "x-api-key", "x-seed-token", "user-agent")
# Headers que pasan de auth al cliente. X-Trace-Id lo agrega el middleware de
# la central (es la misma traza).
RESPONSE_HEADERS = ("content-type", "retry-after")


def is_public(method: str, path: str) -> bool:
    # "." y ".." (también %2e%2e, ya decodificado en path) podrían saltarse la
    # lista al normalizarse después: /auth/me/../seed. Se rechazan.
    if any(segment in (".", "..") for segment in path.split("/")):
        return False
    return any(
        (path == prefix or path.startswith(prefix + "/")) and method in methods
        for prefix, methods in PUBLIC_ROUTES
    )


@router.api_route("/auth/{path:path}", methods=sorted(WRITE | {"PUT"}), include_in_schema=False)
async def proxy_to_auth(request: Request) -> Response:
    path = request.url.path
    if not is_public(request.method, path):
        return JSONResponse({"detail": "Not Found"}, status_code=404)
    if not services.is_enabled("auth") or auth_client is None:  # AUTH_ENABLED=false
        return JSONResponse({"detail": "El servicio auth está deshabilitado."}, status_code=503)

    headers = {name: value for name in REQUEST_HEADERS if (value := request.headers.get(name)) is not None}
    headers |= upstream_headers(request)

    try:
        upstream = await auth_client.request(
            request.method,
            path,
            params=request.query_params.multi_items(),
            content=await request.body(),
            headers=headers,
        )
    except httpx.TimeoutException:
        # Sin reintento: una mutación podría haberse aplicado en auth.
        return JSONResponse({"detail": "El servicio auth no respondió a tiempo."}, status_code=504)
    except httpx.TransportError:
        return JSONResponse({"detail": "El servicio auth no está disponible."}, status_code=502)

    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers={name: value for name in RESPONSE_HEADERS if (value := upstream.headers.get(name)) is not None},
    )
