"""Identidad y permisos de las rutas de libro-mayor.

libro-mayor no valida tokens por su cuenta: pregunta a auth reenviando el
Bearer recibido (como la central). Auth comprueba firma, vencimiento, sesión,
usuario y membresía en su base, así que una sesión revocada o una membresía
dada de baja pierde el acceso de inmediato. Coste: llamadas a auth por solicitud.

- GET /auth/me: id del usuario y si es administrador de plataforma.
- GET /auth/me/permissions con X-Company-Id: empresa validada y permisos con
  su alcance (company / area_ids / own) en esa empresa.

Venir de la central o estar autenticado no concede nada: cada ruta exige su
permiso. Por ahora solo Bearer; X-API-Key se agregará cuando haga falta.
"""

from dataclasses import dataclass

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
    area_ids: frozenset[str]
    own: bool


@dataclass(frozen=True)
class Identity:
    user_id: str
    is_platform_admin: bool


@dataclass(frozen=True)
class CompanyContext:
    user_id: str
    company_id: str  # Validado por auth, no el valor crudo del header.
    company_code: str  # Código estable de la empresa en auth (p. ej. RASH).
    is_platform_admin: bool
    grants: dict[str, Grant]

    def has_company_scope(self, permission: str) -> bool:
        """El permiso vale en toda la empresa (el administrador de plataforma, siempre)."""
        if self.is_platform_admin:
            return True
        grant = self.grants.get(permission)
        return grant is not None and grant.company


# Lee "Authorization: Bearer <token>" y agrega el botón "Authorize" en /docs.
bearer = HTTPBearer(auto_error=False)


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No autenticado.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _ask_auth(path: str, token: str, extra_headers: dict[str, str] | None = None) -> dict:
    headers = {"authorization": f"Bearer {token}", **(extra_headers or {})}
    # Enlaza el log de auth con el de esta solicitud (auth los acepta solo si
    # libro-mayor está en su TRUSTED_PROXIES). No concede permisos.
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


def get_identity(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> Identity:
    if credentials is None:
        raise _unauthorized()
    me = _ask_auth("/auth/me", credentials.credentials)
    set_actor(me["id"])  # Identidad validada por auth: queda en audit.logs.
    return Identity(user_id=me["id"], is_platform_admin=me.get("is_platform_admin") is True)


def get_company_context(
    identity: Identity = Depends(get_identity),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    x_company_id: str | None = Header(default=None, alias="X-Company-Id"),
) -> CompanyContext:
    if not x_company_id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Falta el header X-Company-Id.")
    data = _ask_auth("/auth/me/permissions", credentials.credentials, {"x-company-id": x_company_id})
    company_id = data["company"]["id"]
    set_actor(identity.user_id, company_id)
    return CompanyContext(
        user_id=identity.user_id,
        company_id=company_id,
        company_code=data["company"]["code"],
        is_platform_admin=data.get("is_platform_admin") is True,
        grants={
            p["code"]: Grant(company=p["company"], area_ids=frozenset(p["area_ids"]), own=p["own"])
            for p in data["permissions"]
        },
    )


def require_company_permission(permission: str):
    """Dependencia que exige el permiso con alcance company en la empresa activa.

    Uso: `ctx: CompanyContext = Depends(require_company_permission(ACCOUNTS_MANAGE))`.
    """

    def dependency(ctx: CompanyContext = Depends(get_company_context)) -> CompanyContext:
        if not ctx.has_company_scope(permission):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No tienes permiso para esta operación.")
        return ctx

    return dependency


def require_platform_admin_in_company(ctx: CompanyContext = Depends(get_company_context)) -> CompanyContext:
    """Solo el administrador de plataforma, sobre la empresa de X-Company-Id."""
    if not ctx.is_platform_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo el administrador de plataforma puede usar esta ruta.")
    return ctx


def require_platform_admin(identity: Identity = Depends(get_identity)) -> Identity:
    """Solo el administrador de plataforma (rutas sin empresa, p. ej. logs)."""
    if not identity.is_platform_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo el administrador de plataforma puede usar esta ruta.")
    return identity
