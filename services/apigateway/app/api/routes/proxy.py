"""Reenvío de solicitudes públicas a los servicios (app/core/services.py).

La central no aplica reglas de negocio ni autoriza: reenvía la solicitud y
devuelve la respuesta tal cual (un 401 o un 429 del servicio no es una falla
de la central). Cada servicio valida identidad y permisos.

- Solo se reenvía lo publicado en app/core/public_routes.py; lo demás
  responde 404 sin llegar al servicio.
- Servicio deshabilitado (configuración o panel): 503 sin contactarlo.
- Sin reintentos: agotado el timeout, 504; servicio caído, 502. Una mutación
  podría haberse aplicado, así que repetirla es decisión del cliente.
- El path no se reescribe: /libro-mayor/rules en la central es
  /libro-mayor/rules en el servicio.

Respuesta en streaming: los bytes pasan a medida que llegan, sin cargarse
enteros en memoria (un CSV de un año no ocupa la central). Van sin
descomprimir: si el cliente acepta gzip y el servicio comprime, la central
reenvía el gzip tal cual y el cliente lo descomprime. Si la conexión con el
servicio se corta a mitad, la respuesta queda incompleta (el cliente lo
detecta); no se disfraza de completa.

Correlación en los logs (schema audit): el middleware de la central ya creó el
trace_id y su operación; se envían como X-Trace-Id y X-Parent-Operation-Id, y
el servicio los acepta porque la conexión viene de la central (su
TRUSTED_PROXIES).
"""

import httpx
from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.background import BackgroundTask

from app.clients.upstream import clients
from app.core import services
from app.core.public_routes import WRITE, Route
from app.core.tracing import upstream_headers

router = APIRouter(tags=["proxy"])

# Headers que pasan del cliente al servicio (lista positiva). Cookie, Host y
# otros no se reenvían. X-Forwarded-For y la traza los arma la central.
# X-Seed-Token solo lo usa auth (bootstrap); para los demás no tiene efecto.
REQUEST_HEADERS = (
    "content-type", "accept", "accept-encoding", "authorization", "x-company-id", "x-api-key",
    "x-seed-token", "user-agent",
)
# Headers que pasan del servicio al cliente. Content-Encoding y Content-Length
# describen los bytes tal como llegan (sin descomprimir); Content-Disposition
# lleva el nombre del archivo en descargas (CSV). X-Trace-Id lo agrega el
# middleware de la central (es la misma traza).
RESPONSE_HEADERS = ("content-type", "content-encoding", "content-length", "content-disposition", "retry-after")


def find_route(info: services.ServiceInfo, method: str, path: str) -> Route | None:
    """Ruta publicada que cubre (método, path); None = no publicada."""
    # "." y ".." (también %2e%2e, ya decodificado en path) podrían saltarse la
    # lista al normalizarse después: /auth/me/../seed. Se rechazan.
    if any(segment in (".", "..") for segment in path.split("/")):
        return None
    return next(
        (
            route for route in info.routes
            if (path == route.prefix or path.startswith(route.prefix + "/")) and method in route.methods
        ),
        None,
    )


async def forward(request: Request, info: services.ServiceInfo) -> Response:
    path = request.url.path
    route = find_route(info, request.method, path)
    if route is None:
        return JSONResponse({"detail": "Not Found"}, status_code=404)
    client = clients.get(info.name)
    if not services.is_enabled(info.name) or client is None:
        return JSONResponse({"detail": f"El servicio {info.name} está deshabilitado."}, status_code=503)

    headers = {name: value for name in REQUEST_HEADERS if (value := request.headers.get(name)) is not None}
    # Sin Accept-Encoding del cliente, httpx pondría el suyo (gzip) y la central
    # devolvería bytes comprimidos a quien no los pidió.
    headers.setdefault("accept-encoding", "identity")
    headers |= upstream_headers(request)

    upstream_request = client.build_request(
        request.method,
        path,
        params=request.query_params.multi_items(),
        content=await request.body(),
        headers=headers,
        timeout=route.timeout if route.timeout is not None else info.timeout,
    )
    try:
        upstream = await client.send(upstream_request, stream=True)
    except httpx.TimeoutException:
        return JSONResponse({"detail": f"El servicio {info.name} no respondió a tiempo."}, status_code=504)
    except httpx.TransportError:
        return JSONResponse({"detail": f"El servicio {info.name} no está disponible."}, status_code=502)

    return StreamingResponse(
        upstream.aiter_raw(),  # Bytes tal cual (sin descomprimir).
        status_code=upstream.status_code,
        headers={name: value for name in RESPONSE_HEADERS if (value := upstream.headers.get(name)) is not None},
        background=BackgroundTask(upstream.aclose),  # Libera la conexión al terminar.
    )


def _endpoint(info: services.ServiceInfo):
    async def endpoint(request: Request) -> Response:
        return await forward(request, info)

    return endpoint


# Una ruta comodín por servicio registrado (/auth/..., /libro-mayor/...).
for _info in services.SERVICES.values():
    router.add_api_route(
        f"{_info.prefix}/{{path:path}}",
        _endpoint(_info),
        methods=sorted(WRITE | {"PUT"}),
        include_in_schema=False,
        name=f"proxy_{_info.name}",
    )
