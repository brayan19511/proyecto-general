"""Identidad y permisos de las rutas de pagos-proveedores.

Igual que notificaciones: no valida tokens por su cuenta, pregunta a auth
reenviando el Bearer recibido (GET /auth/me/permissions con X-Company-Id).
Solo Bearer: al enviar, este servicio reenvía el mismo token a notificaciones
(acuerdo de notificaciones: el envío se crea con el token del usuario).

Todos los permisos de este servicio tienen alcance company (app/core/permissions.py).
Venir de la central o estar autenticado no concede nada: cada ruta exige su permiso.
"""

from dataclasses import dataclass, field

import httpx
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from platform_audit import set_actor
from platform_audit.context import current_operation

from app.clients.auth_client import auth_client


@dataclass(frozen=True)
class CompanyContext:
    user_id: str
    company_id: str  # Validado por auth, no el valor crudo del header.
    is_platform_admin: bool
    # Permisos con alcance company en la empresa activa.
    company_permissions: frozenset[str]
    # Credenciales recibidas: se reenvían a notificaciones al enviar un lote.
    # Nunca se registran ni se muestran.
    auth_headers: dict[str, str] = field(default_factory=dict, repr=False)

    def has_any(self, permissions: tuple[str, ...]) -> bool:
        return self.is_platform_admin or any(p in self.company_permissions for p in permissions)


# Lee "Authorization: Bearer <token>" y agrega el botón "Authorize" en /docs.
bearer = HTTPBearer(auto_error=False)


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No autenticado.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _ask_auth(path: str, headers: dict[str, str]) -> dict:
    headers = dict(headers)
    # Enlaza el log de auth con el de esta solicitud (auth los acepta solo si
    # este servicio está en su TRUSTED_PROXIES). No concede permisos.
    operation = current_operation()
    if operation is not None:
        headers["x-trace-id"] = operation.trace_id
        headers["x-parent-operation-id"] = operation.log_id
    try:
        response = auth_client.get(path, headers=headers)
    except httpx.TimeoutException:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="El servicio auth no respondió a tiempo.")
    except httpx.TransportError:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="El servicio auth no está disponible.")

    if response.status_code == status.HTTP_401_UNAUTHORIZED:
        raise _unauthorized()
    if response.status_code == status.HTTP_403_FORBIDDEN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No tienes acceso a esta empresa.")
    if response.status_code != status.HTTP_200_OK:
        # Cualquier otra respuesta es inesperada: no se concede acceso.
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="El servicio auth no está disponible.")
    return response.json()


def get_company_context(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    x_company_id: str | None = Header(default=None, alias="X-Company-Id"),
) -> CompanyContext:
    if credentials is None:
        raise _unauthorized()
    if not x_company_id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Falta el header X-Company-Id.")
    headers = {"authorization": f"Bearer {credentials.credentials}", "x-company-id": x_company_id}
    data = _ask_auth("/auth/me/permissions", headers)
    user_id, company_id = data["user_id"], data["company"]["id"]
    set_actor(user_id, company_id)  # Identidad validada por auth: queda en audit.logs.
    return CompanyContext(
        user_id=user_id,
        company_id=company_id,
        is_platform_admin=data.get("is_platform_admin") is True,
        company_permissions=frozenset(p["code"] for p in data["permissions"] if p["company"]),
        auth_headers=headers,
    )


def require_permission(*permissions: str):
    """Exige ALGUNO de los permisos (con alcance company) en la empresa activa.

    Uso: `ctx: CompanyContext = Depends(require_permission(*CAN_VIEW))`.
    """

    def dependency(ctx: CompanyContext = Depends(get_company_context)) -> CompanyContext:
        if not ctx.has_any(permissions):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No tienes permiso para esta operación.")
        return ctx

    return dependency
