"""Identidad y permisos de las rutas de sap-operaciones (mismo esquema que libro-mayor).

sap-operaciones no valida tokens por su cuenta: pregunta a auth reenviando el
Bearer recibido. Auth comprueba firma, vencimiento, sesión, usuario y
membresía en su base, así que una sesión revocada o una membresía dada de baja
pierde el acceso de inmediato. Coste: una llamada a auth por solicitud.

- Rutas de empresa: una llamada a GET /auth/me/permissions con el Bearer y
  X-Company-Id devuelve usuario, empresa validada y permisos con su alcance.
- Rutas sin empresa (logs): GET /auth/me, solo el administrador de plataforma.

Venir de la central o estar autenticado no concede nada: cada ruta exige su permiso.

Sin X-API-Key por ahora: no hay integraciones que la necesiten.
"""

from dataclasses import dataclass

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
    company_code: str  # Código estable de la empresa en auth (p. ej. RASH).
    is_platform_admin: bool
    company_permissions: frozenset[str]  # Permisos con alcance company.

    def has_any(self, permissions: tuple[str, ...]) -> bool:
        """Alguno de los permisos vale en toda la empresa (el admin de plataforma, siempre)."""
        return self.is_platform_admin or any(p in self.company_permissions for p in permissions)


# Lee "Authorization: Bearer <token>" y agrega el botón "Authorize" en /docs.
# auto_error=False: el 401 lo arma la dependencia.
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
    # sap-operaciones está en su TRUSTED_PROXIES). No concede permisos.
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


def require_platform_admin(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> str:
    """Solo el administrador de plataforma (rutas sin empresa, p. ej. logs).

    Una llamada a GET /auth/me con el Bearer. Devuelve el id del usuario.
    """
    if credentials is None:
        raise _unauthorized()
    me = _ask_auth("/auth/me", {"authorization": f"Bearer {credentials.credentials}"})
    set_actor(me["id"])  # Identidad validada por auth: queda en audit.logs.
    if me.get("is_platform_admin") is not True:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo el administrador de plataforma puede usar esta ruta.")
    return me["id"]


def get_company_context(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    x_company_id: str | None = Header(default=None, alias="X-Company-Id"),
) -> CompanyContext:
    if credentials is None:
        raise _unauthorized()
    if not x_company_id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Falta el header X-Company-Id.")
    data = _ask_auth(
        "/auth/me/permissions",
        {"authorization": f"Bearer {credentials.credentials}", "x-company-id": x_company_id},
    )
    user_id, company_id = data["user_id"], data["company"]["id"]
    set_actor(user_id, company_id)  # Identidad validada por auth: queda en audit.logs.
    return CompanyContext(
        user_id=user_id,
        company_id=company_id,
        company_code=data["company"]["code"],
        is_platform_admin=data.get("is_platform_admin") is True,
        company_permissions=frozenset(p["code"] for p in data["permissions"] if p["company"]),
    )


def require_company_permission(*permissions: str):
    """Dependencia que exige ALGUNO de los permisos con alcance company en la empresa activa.

    Uso: ctx: CompanyContext = Depends(require_company_permission(*CAN_EXECUTE))
    (CAN_VIEW / CAN_EXECUTE en app/core/permissions.py).
    """

    def dependency(ctx: CompanyContext = Depends(get_company_context)) -> CompanyContext:
        if not ctx.has_any(permissions):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No tienes permiso para esta operación.")
        return ctx

    return dependency


def require_platform_admin_in_company(ctx: CompanyContext = Depends(get_company_context)) -> CompanyContext:
    """Solo el administrador de plataforma, sobre la empresa de X-Company-Id
    (p. ej. ver las credenciales guardadas de un trabajo de esa empresa)."""
    if not ctx.is_platform_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo el administrador de plataforma puede usar esta ruta.")
    return ctx
