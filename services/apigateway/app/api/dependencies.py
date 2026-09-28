"""Identidad para las rutas de administración de la central (/gateway/admin/...).

La central no valida tokens por su cuenta: pregunta a auth con GET /auth/me,
reenviando el Bearer recibido. Auth comprueba firma, vencimiento, sesión y
usuario en su base, así que una sesión revocada o un usuario dado de baja deja
de tener acceso de inmediato. Coste: una llamada a auth por solicitud
administrativa.

No se concede acceso por venir de la central ni por estar autenticado: se exige
is_platform_admin=true en la respuesta de auth.
"""

from dataclasses import dataclass

import httpx
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from platform_audit import set_actor

from app.clients.auth_client import auth_client
from app.core.tracing import upstream_headers


@dataclass(frozen=True)
class AdminUser:
    id: str
    email: str


# Lee "Authorization: Bearer <token>" y agrega el botón "Authorize" en /docs.
# auto_error=False: el 401 lo arma esta dependencia, con el mismo mensaje que auth.
bearer = HTTPBearer(auto_error=False)


async def require_platform_admin(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> AdminUser:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No autenticado.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if auth_client is None:  # AUTH_ENABLED=false: no hay a quién preguntar.
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="El servicio auth está deshabilitado.")

    headers = {"authorization": f"Bearer {credentials.credentials}", **upstream_headers(request)}
    if user_agent := request.headers.get("user-agent"):
        headers["user-agent"] = user_agent
    try:
        response = await auth_client.get("/auth/me", headers=headers)
    except httpx.TimeoutException:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="El servicio auth no respondió a tiempo.")
    except httpx.TransportError:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="El servicio auth no está disponible.")

    if response.status_code == status.HTTP_401_UNAUTHORIZED:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No autenticado.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if response.status_code != status.HTTP_200_OK:
        # Cualquier otra respuesta de auth es inesperada aquí: no se concede acceso.
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="El servicio auth no está disponible.")

    me = response.json()
    if me.get("is_platform_admin") is not True:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo el administrador de plataforma puede usar esta ruta.",
        )
    set_actor(me["id"])  # Identidad validada por auth: se registra en el log de la central.
    return AdminUser(id=me["id"], email=me["email"])
