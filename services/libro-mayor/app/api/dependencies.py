"""Identidad y permisos de las rutas de libro-mayor.

libro-mayor no valida tokens por su cuenta: pregunta a auth reenviando el
Bearer recibido (como la central). Auth comprueba firma, vencimiento, sesión,
usuario y membresía en su base, así que una sesión revocada o una membresía
dada de baja pierde el acceso de inmediato. Coste: llamadas a auth por solicitud.

- Rutas de empresa: UNA llamada a GET /auth/me/permissions, reenviando el
  Bearer o la X-API-Key recibidos. Devuelve usuario, empresa validada y
  permisos con su alcance (company / area_ids / own). Con Bearer hace falta
  X-Company-Id; con API key la empresa es la de la clave (si se envía
  X-Company-Id, auth exige que coincida). Una API key nunca actúa como
  administrador de plataforma y sus permisos se limitan a sus scopes.
- Rutas sin empresa (logs): GET /auth/me, solo Bearer.

Venir de la central o estar autenticado no concede nada: cada ruta exige su
permiso. La API key sirve para integraciones que no pueden renovar un token
(Excel, Power BI): el usuario la crea en auth.
"""

from dataclasses import dataclass, field

import httpx
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from platform_audit import set_actor
from platform_audit.context import current_operation

from app.clients.auth_client import auth_client
from app.core.permissions import CAN_VIEW, VIEW


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
    # Credenciales recibidas (Bearer o X-API-Key), para consultar auth en nombre
    # del mismo usuario (p. ej. sus áreas). Nunca se registran ni se muestran.
    auth_headers: dict[str, str] = field(default_factory=dict, repr=False)

    def has_company_scope(self, permission: str) -> bool:
        """El permiso vale en toda la empresa (el administrador de plataforma, siempre)."""
        if self.is_platform_admin:
            return True
        grant = self.grants.get(permission)
        return grant is not None and grant.company


# Leen "Authorization: Bearer <token>" y "X-API-Key: <clave>"; agregan los
# botones "Authorize" en /docs. auto_error=False: el 401 lo arma cada dependencia.
bearer = HTTPBearer(auto_error=False)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No autenticado.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _ask_auth(path: str, headers: dict[str, str]) -> dict:
    headers = dict(headers)
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
    me = _ask_auth("/auth/me", {"authorization": f"Bearer {credentials.credentials}"})
    set_actor(me["id"])  # Identidad validada por auth: queda en audit.logs.
    return Identity(user_id=me["id"], is_platform_admin=me.get("is_platform_admin") is True)


def get_company_context(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    api_key: str | None = Depends(api_key_header),
    x_company_id: str | None = Header(default=None, alias="X-Company-Id"),
) -> CompanyContext:
    if api_key:
        headers = {"x-api-key": api_key}
    elif credentials is not None:
        if not x_company_id:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Falta el header X-Company-Id.")
        headers = {"authorization": f"Bearer {credentials.credentials}"}
    else:
        raise _unauthorized()
    if x_company_id:
        headers["x-company-id"] = x_company_id
    data = _ask_auth("/auth/me/permissions", headers)
    if "user_id" not in data:
        # auth anterior al campo user_id: actualizar auth (cambio compatible del 2026-09-30).
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="El servicio auth no está actualizado.")
    user_id, company_id = data["user_id"], data["company"]["id"]
    set_actor(user_id, company_id)  # Identidad validada por auth: queda en audit.logs.
    return CompanyContext(
        user_id=user_id,
        company_id=company_id,
        company_code=data["company"]["code"],
        is_platform_admin=data.get("is_platform_admin") is True,
        auth_headers=headers,
        grants={
            p["code"]: Grant(company=p["company"], area_ids=frozenset(p["area_ids"]), own=p["own"])
            for p in data["permissions"]
        },
    )


def require_company_permission(*permissions: str):
    """Dependencia que exige ALGUNO de los permisos con alcance company en la empresa activa.

    Uso: `ctx: CompanyContext = Depends(require_company_permission(*CAN_UPDATE))`
    (CAN_VIEW / CAN_UPDATE / CAN_ADMIN en app/core/permissions.py: un nivel
    mayor incluye a los menores).
    """

    def dependency(ctx: CompanyContext = Depends(get_company_context)) -> CompanyContext:
        if not any(ctx.has_company_scope(permission) for permission in permissions):
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


@dataclass(frozen=True)
class ViewScope:
    """Qué líneas puede ver quien consulta: area_ids None = toda la empresa."""

    ctx: CompanyContext
    area_ids: frozenset[str] | None


def require_view_scope(ctx: CompanyContext = Depends(get_company_context)) -> ViewScope:
    """Para rutas de datos (líneas, resumen, CSV, en vivo).

    - ledger.view / update / admin con alcance company (o admin de plataforma):
      toda la empresa, incluidas líneas sin centro de costo o sin homologar.
    - ledger.view con alcance area: solo las líneas cuyos centros de costo están
      homologados a esas áreas (cost_center_mappings).
    """
    if any(ctx.has_company_scope(permission) for permission in CAN_VIEW):
        return ViewScope(ctx=ctx, area_ids=None)
    grant = ctx.grants.get(VIEW)
    if grant is not None and grant.area_ids:
        return ViewScope(ctx=ctx, area_ids=grant.area_ids)
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No tienes permiso para esta operación.")


def fetch_areas(ctx: CompanyContext) -> dict[str, dict]:
    """Áreas de la empresa según auth (GET /auth/areas), con las credenciales del usuario.

    Devuelve {area_id: {"id", "code", "name", "is_active"}}. libro-mayor no lee
    tablas de auth: así valida que un área existe y es de esta empresa.
    """
    headers = {**ctx.auth_headers, "x-company-id": ctx.company_id}
    return {area["id"]: area for area in _ask_auth("/auth/areas?limit=500", headers)}
