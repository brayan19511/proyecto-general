import secrets
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from platform_audit import set_actor

from app.core.client_ip import client_ip
from app.core.config import settings
from app.core.db.connection import get_db
from app.models.common.mixin_model import utcnow
from app.services.rate_limit import RateLimitExceededError, hit, ip_key
from app.models.entities import AuthSession, User
from app.services.access_service import (
    AccessService,
    CompanyAccessDeniedError,
    CompanyContext,
)
from app.services.api_key_service import ApiKeyService, InvalidApiKeyError, restrict_to_scopes
from app.services.auth_service import AuthService, InvalidAccessTokenError


def require_seed_token(x_seed_token: str | None = Header(default=None)) -> None:
    """Rechaza la solicitud si no trae el secreto de bootstrap correcto."""
    expected = settings.SEED_TOKEN
    if (
        expected is None
        or x_seed_token is None
        or not secrets.compare_digest(
            x_seed_token.encode(),
            expected.get_secret_value().encode(),
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No autorizado.",
        )


def ip_rate_limit(operation: str, limit_setting: str, window_setting: str):
    """Crea una dependencia que limita el volumen de una operación por IP.

    Uso: `dependencies=[Depends(ip_rate_limit("login", "LOGIN_IP_LIMIT", "LOGIN_IP_WINDOW_MINUTES"))]`.
    Los valores se leen de settings en cada solicitud (nombres de variables de entorno).
    """

    def dependency(request: Request, db: Session = Depends(get_db)) -> None:
        try:
            hit(
                db,
                ip_key(operation, client_ip(request)),
                getattr(settings, limit_setting),
                getattr(settings, window_setting),
                utcnow(),
            )
        except RateLimitExceededError as exc:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Demasiadas solicitudes. Intenta más tarde.",
                headers={"Retry-After": str(exc.retry_after_seconds)},
            ) from exc

    return dependency


# Lee "Authorization: Bearer <token>". auto_error=False para responder con
# nuestro propio 401; además habilita el botón "Authorize" en /docs.
bearer_scheme = HTTPBearer(auto_error=False)


@dataclass
class CurrentUser:
    """Identidad validada de la solicitud: usuario y sesión, ambos vigentes."""

    user: User
    session: AuthSession


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> CurrentUser:
    """Dependencia de toda ruta protegida: `current: CurrentUser = Depends(get_current_user)`.

    FastAPI reutiliza la misma sesión ORM (get_db) dentro de la solicitud,
    así la ruta y esta dependencia comparten conexión.
    """
    if credentials is None:
        raise _unauthorized()
    try:
        user, auth_session = AuthService(db).authenticate(credentials.credentials)
    except InvalidAccessTokenError as exc:
        raise _unauthorized() from exc
    set_actor(user.id)  # Identidad ya validada: se registra en el log.
    return CurrentUser(user=user, session=auth_session)


def require_platform_admin(
    current: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    """Dependencia de las rutas /admin: solo el master admin (is_platform_admin).

    No usa X-Company-Id: estas rutas trabajan sobre todas las empresas.
    """
    if not current.user.is_platform_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo el administrador de plataforma puede usar esta ruta.",
        )
    return current


# Header de las API keys; habilita también su botón en "Authorize" de /docs.
api_key_scheme = APIKeyHeader(name="X-API-Key", auto_error=False)


def get_user_company_context(
    x_company_id: str = Header(
        description="Empresa activa. Se valida contra las membresías del usuario.",
    ),
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CompanyContext:
    """Contexto de empresa para un usuario con sesión (solo Bearer).

    El header solo propone la empresa: se comprueba en la base que exista, esté
    activa y que el usuario tenga una membresía activa (o sea master admin).
    Lo usan directamente las rutas que una API key no debe poder usar, como
    crear o revocar keys.
    """
    try:
        ctx = AccessService(db).build_context(current.user, x_company_id)
    except CompanyAccessDeniedError as exc:
        raise _no_company_access() from exc
    set_actor(current.user.id, ctx.company.id)
    return ctx


def get_company_context(
    x_company_id: str | None = Header(
        default=None,
        description="Empresa activa. Obligatorio con Bearer; con API key es opcional (la de la key).",
    ),
    x_api_key: str | None = Depends(api_key_scheme),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> CompanyContext:
    """Dependencia de toda ruta empresarial: acepta Bearer o X-API-Key.

    Con API key, los permisos son los actuales de la membresía intersectados con
    los scopes de la key, y nunca actúa como master admin.
    """
    if x_api_key:
        try:
            user, api_key = ApiKeyService(db).authenticate(x_api_key)
        except InvalidApiKeyError as exc:
            raise _unauthorized() from exc
        if x_company_id is not None and x_company_id != api_key.company_id:
            raise _no_company_access()
        try:
            # Sin poderes de plataforma: solo lo que dan sus puestos, luego ∩ scopes.
            ctx = AccessService(db).build_context(user, api_key.company_id, as_platform_admin=False)
        except CompanyAccessDeniedError as exc:
            raise _no_company_access() from exc
        # La membresía de la key debe seguir vigente (build_context la busca activa).
        if ctx.membership is None or ctx.membership.id != api_key.membership_id:
            raise _no_company_access()
        set_actor(user.id, ctx.company.id)
        return restrict_to_scopes(ctx, api_key.scopes)

    current = get_current_user(credentials, db)
    if x_company_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Falta el header X-Company-Id.",
        )
    return get_user_company_context(x_company_id, current, db)


def _no_company_access() -> HTTPException:
    # Mismo 403 si la empresa no existe o si no perteneces: no revela qué empresas existen.
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="No tienes acceso a esta empresa.",
    )


def require_permission(permission: str):
    """Crea una dependencia que exige el permiso con algún alcance.

    Uso: `ctx: CompanyContext = Depends(require_permission("areas.manage"))`.
    Solo decide si la ruta se puede usar. Si el permiso es de alcance area,
    la ruta debe comprobar cada recurso con `ctx.can(permiso, area_id=...)`.
    """

    def dependency(ctx: CompanyContext = Depends(get_company_context)) -> CompanyContext:
        if not ctx.has_any(permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes permiso para esta operación.",
            )
        return ctx

    return dependency


def _unauthorized() -> HTTPException:
    # Un solo mensaje: no revela si faltó el token, venció o la sesión se cerró.
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No autenticado.",
        headers={"WWW-Authenticate": "Bearer"},
    )
