"""Identidad y permisos de las rutas de notificaciones.

notificaciones no valida tokens por su cuenta: pregunta a auth reenviando el
Bearer recibido (como libro-mayor y la central). Auth comprueba firma,
vencimiento, sesión, usuario y membresía en su base, así que una sesión
revocada o una membresía dada de baja pierde el acceso de inmediato.

- UNA llamada a GET /auth/me/permissions con el Bearer y X-Company-Id.
  Devuelve usuario, empresa validada y permisos con su alcance (company / own).
- v1 solo acepta Bearer (acuerdo 2026-10-01): el consumidor reenvía el token
  del usuario. Las API keys de auth se aceptarán cuando una integración las
  necesite.

Venir de la central o estar autenticado no concede nada: cada ruta exige su
permiso.
"""

from dataclasses import dataclass, field
from typing import Literal

import httpx
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from platform_audit import set_actor
from platform_audit.context import current_operation

from app.clients.auth_client import auth_client


@dataclass(frozen=True)
class Grant:
    """Alcance de un permiso en la empresa activa (tal como lo calcula auth)."""

    company: bool
    own: bool


@dataclass(frozen=True)
class CompanyContext:
    user_id: str
    company_id: str  # Validado por auth, no el valor crudo del header.
    is_platform_admin: bool
    grants: dict[str, Grant]
    # Email del usuario según auth (no verificado). None si auth es anterior al campo.
    email: str | None = None
    # Código estable de la empresa en auth (p. ej. RASH): elige sus datos de seed.
    company_code: str | None = None
    # Credenciales recibidas, para consultar auth en nombre del mismo usuario.
    # Nunca se registran ni se muestran.
    auth_headers: dict[str, str] = field(default_factory=dict, repr=False)

    def scope_for(self, permissions: tuple[str, ...]) -> Literal["company", "own"] | None:
        """Mayor alcance que concede ALGUNO de los permisos (un nivel).

        company gana a own. El administrador de plataforma siempre tiene company.
        """
        if self.is_platform_admin:
            return "company"
        grants = [self.grants[p] for p in permissions if p in self.grants]
        if any(grant.company for grant in grants):
            return "company"
        if any(grant.own for grant in grants):
            return "own"
        return None


@dataclass(frozen=True)
class Access:
    """Quién llama y sobre qué puede actuar en la ruta.

    scope = "own": la ruta solo ve u opera envíos con created_by = el actor de
    ctx.user_id. scope = "company": todos los de ctx.company_id.
    """

    ctx: CompanyContext
    scope: Literal["company", "own"]


# Lee "Authorization: Bearer <token>" y agrega el botón "Authorize" en /docs.
# auto_error=False: el 401 lo arma cada dependencia.
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
    # notificaciones está en su TRUSTED_PROXIES). No concede permisos.
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
        email=data.get("email"),  # Campo agregado a auth el 2026-10-01 (compatible).
        company_code=data["company"].get("code"),
        auth_headers=headers,
        grants={p["code"]: Grant(company=p["company"], own=p["own"]) for p in data["permissions"]},
    )


def require_permission(*permissions: str):
    """Dependencia que exige ALGUNO de los permisos y devuelve el alcance efectivo.

    Uso: `access: Access = Depends(require_permission(*CAN_VIEW))`
    (CAN_VIEW / CAN_SEND / CAN_RETRY / CAN_ADMIN en app/core/permissions.py).
    """

    def dependency(ctx: CompanyContext = Depends(get_company_context)) -> Access:
        scope = ctx.scope_for(permissions)
        if scope is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No tienes permiso para esta operación.")
        return Access(ctx=ctx, scope=scope)

    return dependency


def require_company_permission(*permissions: str):
    """Como require_permission, pero exige alcance company (p. ej. cuentas SMTP)."""

    def dependency(access: Access = Depends(require_permission(*permissions))) -> Access:
        if access.scope != "company":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No tienes permiso para esta operación.")
        return access

    return dependency


def require_platform_admin_in_company(ctx: CompanyContext = Depends(get_company_context)) -> CompanyContext:
    """Solo el administrador de plataforma, sobre la empresa de X-Company-Id (p. ej. el seed)."""
    if not ctx.is_platform_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo el administrador de plataforma puede usar esta ruta.")
    return ctx
