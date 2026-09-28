"""CRUD de roles de la empresa activa y de sus permisos.

Autorización:
  - Ver roles (con sus permisos): cualquier miembro de la empresa o el master admin.
  - Crear, renombrar y dar de baja roles: roles.manage (solo alcance company).
  - Otorgar un permiso a un rol: roles.manage + regla de delegación.
  - Retirar un permiso de un rol: roles.manage (quitar reduce privilegios).

Regla de delegación: para otorgar el permiso P a un rol, quien actúa debe
tener P con alcance company. Un rol puede quedar vinculado a puestos de
cualquier área, así que tener P solo en un área no alcanza: sería una forma
de ampliar su propio alcance. El master admin cumple siempre.
"""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.permissions import PERMISSIONS
from app.models.common.mixin_model import utcnow
from app.models.entities import Role, RolePermission
from app.repositories.role_repository import RoleRepository
from app.schemas.role import (
    RoleCreate,
    RoleOut,
    RolePermissionCreate,
    RolePermissionOut,
    RoleUpdate,
)
from app.services.access_service import CompanyContext, LastAdminGuard, PermissionDeniedError
from app.services.common import (
    audit_create,
    history_event,
    restore,
    soft_delete,
    touch,
)

PERMISSION = "roles.manage"


class RoleNotFoundError(Exception):
    """No existe, está dado de baja o es de otra empresa."""


class RoleCodeExistsError(Exception):
    """El código ya está usado en la empresa, incluso por un rol dado de baja."""


class RoleInUseError(Exception):
    """El rol está asignado a puestos: darlo de baja quitaría permisos sin aviso."""


class UnknownPermissionError(Exception):
    """El permiso no está en el catálogo o no admite ese scope."""


class GrantExistsError(Exception):
    """El rol ya tiene ese permiso con ese scope."""


class GrantNotFoundError(Exception):
    """La concesión no existe, ya fue retirada o es de otro rol."""


class RoleService:
    def __init__(self, session: Session):
        self.session = session
        self.repository = RoleRepository(session)

    # --- Lectura

    def list_all(
        self, ctx: CompanyContext, limit: int, offset: int, include_deleted: bool = False
    ) -> list[RoleOut]:
        with self.session.begin():
            roles = self.repository.list_by_company(ctx.company.id, limit, offset, include_deleted)
            return self.to_out_many(roles)

    def get(self, ctx: CompanyContext, role_id: str) -> RoleOut:
        with self.session.begin():
            role = self._get_or_404(ctx, role_id)
            return self.to_out_many([role])[0]

    # --- Roles

    def create(self, ctx: CompanyContext, data: RoleCreate) -> RoleOut:
        self._require_manage(ctx)
        now = utcnow()
        actor = ctx.user.id
        try:
            with self.session.begin():
                if self.repository.get_by_code(ctx.company.id, data.code) is not None:
                    raise RoleCodeExistsError()
                role = self.repository.add(
                    Role(
                        company_id=ctx.company.id,
                        code=data.code,
                        name=data.name,
                        **audit_create(actor, now),
                    )
                )
                self.repository.add_history(
                    history_event(
                        "role.created", role.id, ctx.company.id, actor, now,
                        before={},
                        after={"code": role.code, "name": role.name, "is_active": True},
                    )
                )
        except IntegrityError as exc:
            raise RoleCodeExistsError() from exc
        return RoleOut(**_role_fields(role), permissions=[])

    def update(self, ctx: CompanyContext, role_id: str, data: RoleUpdate) -> RoleOut:
        self._require_manage(ctx)
        now = utcnow()
        actor = ctx.user.id
        with self.session.begin():
            role = self._get_or_404(ctx, role_id)
            if role.name != data.name:
                before = {"name": role.name}
                role.name = data.name
                touch(role, actor, now)
                self.repository.add_history(
                    history_event(
                        "role.updated", role.id, ctx.company.id, actor, now,
                        before=before,
                        after={"name": role.name},
                    )
                )
            return self.to_out_many([role])[0]

    def delete(self, ctx: CompanyContext, role_id: str) -> None:
        self._require_manage(ctx)
        now = utcnow()
        actor = ctx.user.id
        with self.session.begin():
            role = self._get_or_404(ctx, role_id)
            if self.repository.count_position_links(role.id) > 0:
                raise RoleInUseError()
            before = {"is_active": role.is_active, "deleted_at": None}
            soft_delete(role, actor, now)
            self.repository.add_history(
                history_event(
                    "role.deleted", role.id, ctx.company.id, actor, now,
                    before=before,
                    after={"is_active": False, "deleted_at": now.isoformat()},
                )
            )

    def restore(self, ctx: CompanyContext, role_id: str) -> RoleOut:
        """Deshace una baja o suspensión. Vuelve con sus permisos; no está en
        ningún puesto (la baja exigía que no lo estuviera)."""
        self._require_manage(ctx)
        now = utcnow()
        actor = ctx.user.id
        with self.session.begin():
            role = self.repository.get_any(ctx.company.id, role_id)
            if role is None:
                raise RoleNotFoundError()
            if not (role.is_active and role.deleted_at is None):
                before = {"is_active": role.is_active, "deleted_at": _iso(role.deleted_at)}
                restore(role, actor, now)
                self.repository.add_history(
                    history_event(
                        "role.restored", role.id, ctx.company.id, actor, now,
                        before=before,
                        after={"is_active": True, "deleted_at": None},
                    )
                )
            return self.to_out_many([role])[0]

    # --- Permisos del rol

    def grant(self, ctx: CompanyContext, role_id: str, data: RolePermissionCreate) -> RoleOut:
        self._require_manage(ctx)
        if data.scope not in PERMISSIONS.get(data.permission, []):
            raise UnknownPermissionError()
        self._require_delegation(ctx, data.permission)
        now = utcnow()
        actor = ctx.user.id
        try:
            with self.session.begin():
                role = self._get_or_404(ctx, role_id)
                permission = self.repository.get_permission(data.permission)
                if permission is None:
                    # En el catálogo del código pero no cargado: falta ejecutar el seed.
                    raise UnknownPermissionError()

                grant = self.repository.find_grant(role.id, permission.id, data.scope)
                if grant is not None and grant.is_active and grant.deleted_at is None:
                    raise GrantExistsError()

                after = {"permission": data.permission, "scope": data.scope, "is_active": True}
                if grant is None:
                    grant = self.repository.add(
                        RolePermission(
                            role_id=role.id,
                            permission_id=permission.id,
                            scope=data.scope,
                            **audit_create(actor, now),
                        )
                    )
                    action, before = "role_permission.created", {}
                else:
                    # Se retiró antes: la unicidad es permanente, así que se
                    # restaura la misma fila con una acción explícita y su evento.
                    before = {"is_active": grant.is_active, "deleted_at": _iso(grant.deleted_at)}
                    restore(grant, actor, now)
                    action = "role_permission.restored"

                self.repository.add_history(
                    history_event(action, grant.id, ctx.company.id, actor, now, before=before, after=after)
                )
                return self.to_out_many([role])[0]
        except IntegrityError as exc:
            # Carrera: otra solicitud otorgó lo mismo a la vez.
            raise GrantExistsError() from exc

    def revoke(self, ctx: CompanyContext, role_id: str, grant_id: str) -> None:
        self._require_manage(ctx)
        now = utcnow()
        actor = ctx.user.id
        with self.session.begin():
            guard = LastAdminGuard(self.session, ctx.company.id)
            role = self._get_or_404(ctx, role_id)
            grant = self.repository.get_grant(role.id, grant_id)
            if grant is None:
                raise GrantNotFoundError()
            permission_code = self._permission_code(grant)
            soft_delete(grant, actor, now)
            self.repository.add_history(
                history_event(
                    "role_permission.deleted", grant.id, ctx.company.id, actor, now,
                    before={"permission": permission_code, "scope": grant.scope, "is_active": True},
                    after={"is_active": False, "deleted_at": now.isoformat()},
                )
            )
            guard.check()

    # --- Salida

    def to_out_many(self, roles: list[Role]) -> list[RoleOut]:
        """Arma las respuestas con una sola consulta de permisos para todos los roles.

        Muestra cada concesión vigente tal como está guardada. Una concesión
        cuyo scope ya no admite el catálogo no concede nada (AccessService la
        ignora); se ve aquí para poder retirarla.
        """
        grants_by_role: dict[str, list[RolePermissionOut]] = {}
        for grant, permission in self.repository.list_grants([r.id for r in roles]):
            grants_by_role.setdefault(grant.role_id, []).append(
                RolePermissionOut(id=grant.id, permission=permission.code, scope=grant.scope)
            )
        return [
            RoleOut(**_role_fields(role), permissions=grants_by_role.get(role.id, []))
            for role in roles
        ]

    # --- Internos

    def _get_or_404(self, ctx: CompanyContext, role_id: str) -> Role:
        role = self.repository.get(ctx.company.id, role_id)
        if role is None:
            raise RoleNotFoundError()
        return role

    def _permission_code(self, grant: RolePermission) -> str:
        return self.repository.get_permission_by_id(grant.permission_id).code

    @staticmethod
    def _require_manage(ctx: CompanyContext) -> None:
        if not ctx.can(PERMISSION):
            raise PermissionDeniedError()

    @staticmethod
    def _require_delegation(ctx: CompanyContext, permission: str) -> None:
        # Sin area_id, can() solo acepta alcance company (o master admin).
        if not ctx.can(permission):
            raise PermissionDeniedError()


def _role_fields(role: Role) -> dict:
    return {
        "id": role.id,
        "code": role.code,
        "name": role.name,
        "is_active": role.is_active,
        "deleted_at": role.deleted_at,
        "created_at": role.created_at,
        "updated_at": role.updated_at,
    }


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None
