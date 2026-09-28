"""API keys: credenciales de larga duración de un usuario para una empresa.

Requisitos aplicados (docs/requisitos.md, sección API keys):
  - Hasta API_KEYS_MAX (5) activas y vigentes por usuario, entre todas sus
    empresas. Se cuenta bloqueando la fila del usuario: dos creaciones
    simultáneas no superan el máximo.
  - Vinculadas a la membresía y la empresa; sin membresía no hay key.
  - Scopes = permisos que podrá usar. Al crearla no pueden superar los permisos
    actuales, y en cada uso se intersectan con los permisos de ese momento:
    si pierdes un permiso, la key también lo pierde.
  - El secreto se muestra una sola vez; se guarda su hash y un prefijo visible.
  - Revocación irreversible: para reemplazarla se crea otra.
  - expires_at NULL = sin vencimiento, pero revocable.
  - Una key no crea ni revoca keys: esas rutas exigen login (Bearer).

Formato: "ak_<prefijo>.<secreto>". Se envía en el header X-API-Key junto con
las rutas empresariales; X-Company-Id es opcional (la empresa es la de la key).
"""

import hashlib
import secrets
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.permissions import PERMISSIONS
from app.models.common.mixin_model import utcnow
from app.models.entities import ApiKey, User
from app.repositories.api_key_repository import ApiKeyRepository
from app.repositories.auth_repository import AuthRepository
from app.schemas.api_key import ApiKeyCreate, ApiKeyCreated, ApiKeyOut
from app.services.access_service import CompanyContext, PermissionDeniedError
from app.services.auth_service import user_can_login
from app.services.common import audit_create, history_event, touch


class ApiKeyLimitError(Exception):
    """El usuario ya tiene el máximo de keys vigentes."""


class InvalidScopeError(Exception):
    """Un scope no existe en el catálogo."""


class InvalidExpirationError(Exception):
    """La fecha de vencimiento ya pasó."""


class MembershipRequiredError(Exception):
    """Solo un miembro de la empresa puede tener keys en ella."""


class ApiKeyNotFoundError(Exception):
    """No existe, no es tuya o es de otra empresa."""


class InvalidApiKeyError(Exception):
    """Key inexistente, revocada, vencida o de un usuario inhabilitado."""


def hash_key(key: str) -> str:
    # SHA-256 y no Argon2: el secreto es aleatorio y largo, y hay que buscarlo por hash.
    return hashlib.sha256(key.encode()).hexdigest()


def _out(key: ApiKey) -> dict:
    return {
        "id": key.id,
        "name": key.name,
        "description": key.description,
        "prefix": key.prefix,
        "scopes": key.scopes,
        "company_id": key.company_id,
        "expires_at": key.expires_at,
        "revoked_at": key.revoked_at,
        "last_used_at": key.last_used_at,
        "created_at": key.created_at,
    }


class ApiKeyService:
    def __init__(self, session: Session):
        self.session = session
        self.repository = ApiKeyRepository(session)
        self.auth_repository = AuthRepository(session)

    def create(self, ctx: CompanyContext, data: ApiKeyCreate) -> ApiKeyCreated:
        if ctx.membership is None:
            raise MembershipRequiredError()
        scopes = sorted(set(data.scopes))
        for scope in scopes:
            if scope not in PERMISSIONS:
                raise InvalidScopeError()
            # No se puede pedir para la key un permiso que no tienes.
            if not ctx.has_any(scope):
                raise PermissionDeniedError()

        now = utcnow()
        if data.expires_in_days is not None:
            expires_at = now + timedelta(days=data.expires_in_days)
        else:
            expires_at = data.expires_at
        if expires_at is not None and expires_at <= now:
            raise InvalidExpirationError()

        prefix = "ak_" + secrets.token_urlsafe(6)[:8]
        key = f"{prefix}.{secrets.token_urlsafe(32)}"
        actor = ctx.user.id

        with self.session.begin():
            # Bloquea al usuario: serializa creaciones simultáneas y el conteo es exacto.
            self.auth_repository.lock_user(actor)
            if self.repository.count_valid_for_user(actor, now) >= settings.API_KEYS_MAX:
                raise ApiKeyLimitError()
            api_key = self.repository.add(
                ApiKey(
                    user_id=actor,
                    company_id=ctx.company.id,
                    membership_id=ctx.membership.id,
                    name=data.name,
                    description=data.description,
                    prefix=prefix,
                    key_hash=hash_key(key),
                    scopes=scopes,
                    expires_at=expires_at,
                    revoked_at=None,
                    last_used_at=None,
                    **audit_create(actor, now),
                )
            )
            self.repository.add_history(
                history_event(
                    "api_key.created", api_key.id, ctx.company.id, actor, now,
                    before={},
                    # Nunca el secreto ni su hash.
                    after={
                        "name": api_key.name,
                        "prefix": prefix,
                        "scopes": scopes,
                        "expires_at": expires_at.isoformat() if expires_at else None,
                    },
                )
            )
        return ApiKeyCreated(**_out(api_key), key=key)

    def list_own(self, ctx: CompanyContext) -> list[ApiKeyOut]:
        with self.session.begin():
            keys = self.repository.list_for_user(ctx.user.id, ctx.company.id)
        return [ApiKeyOut(**_out(k)) for k in keys]

    def revoke(self, ctx: CompanyContext, key_id: str) -> None:
        now = utcnow()
        with self.session.begin():
            api_key = self.repository.get_own(ctx.user.id, ctx.company.id, key_id)
            if api_key is None:
                raise ApiKeyNotFoundError()
            if api_key.revoked_at is not None:
                return  # Ya revocada: la revocación es irreversible e idempotente.
            api_key.revoked_at = now
            touch(api_key, ctx.user.id, now)
            self.repository.add_history(
                history_event(
                    "api_key.revoked", api_key.id, ctx.company.id, ctx.user.id, now,
                    before={"revoked_at": None},
                    after={"revoked_at": now.isoformat()},
                )
            )

    def authenticate(self, key: str) -> tuple[User, ApiKey]:
        """Valida la key y marca su último uso. Los permisos se calculan después
        (AccessService) y se intersectan con los scopes."""
        now = utcnow()
        with self.session.begin():
            api_key = self.repository.get_by_hash(hash_key(key))
            if (
                api_key is None
                or not api_key.is_active
                or api_key.deleted_at is not None
                or api_key.revoked_at is not None
                or (api_key.expires_at is not None and api_key.expires_at <= now)
            ):
                raise InvalidApiKeyError()
            user = self.session.get(User, api_key.user_id)
            if user is None or not user_can_login(user):
                raise InvalidApiKeyError()
            # Actividad operativa: no genera historial.
            api_key.last_used_at = now
        return user, api_key


def restrict_to_scopes(ctx: CompanyContext, scopes: list[str]) -> CompanyContext:
    """Contexto para una solicitud con API key: permisos actuales ∩ scopes.

    Una key nunca actúa como master admin, aunque su dueño lo sea.
    """
    return CompanyContext(
        user=ctx.user,
        company=ctx.company,
        membership=ctx.membership,
        is_platform_admin=False,
        grants={code: grant for code, grant in ctx.grants.items() if code in scopes},
    )
