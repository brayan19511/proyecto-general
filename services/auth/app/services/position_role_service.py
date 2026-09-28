"""Roles de cada puesto (puesto-rol).

Autorización (propuesta aceptada por el usuario):
  - Ver los roles de un puesto: cualquier miembro de la empresa.
  - Vincular un rol: positions.manage en el área del puesto + regla de
    delegación: quien actúa debe tener cada permiso del rol con el alcance que
    el rol otorga en esa área (ensure_can_delegate).
  - Desvincular: positions.manage en el área del puesto (quitar reduce privilegios).
"""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.common.mixin_model import utcnow
from app.models.entities import Position, PositionRole
from app.repositories.access_repository import AccessRepository
from app.repositories.position_repository import PositionRepository
from app.repositories.role_repository import RoleRepository
from app.schemas.position import PositionRoleOut
from app.services.access_service import (
    CompanyContext,
    LastAdminGuard,
    PermissionDeniedError,
    ensure_can_delegate,
)
from app.services.common import audit_create, history_event, restore, soft_delete
from app.services.position_service import PERMISSION, PositionNotFoundError
from app.services.role_service import RoleNotFoundError


class RoleAlreadyLinkedError(Exception):
    """El puesto ya tiene ese rol."""


class RoleNotLinkedError(Exception):
    """El puesto no tiene ese rol."""


class PositionRoleService:
    def __init__(self, session: Session):
        self.session = session
        self.positions = PositionRepository(session)
        self.roles = RoleRepository(session)
        self.access = AccessRepository(session)

    def list_roles(self, ctx: CompanyContext, position_id: str) -> list[PositionRoleOut]:
        with self.session.begin():
            position = self._get_position(ctx, position_id)
            links = self.positions.list_role_links(position.id)
        return [_to_out(link, role) for link, role in links]

    def add_role(self, ctx: CompanyContext, position_id: str, role_id: str) -> list[PositionRoleOut]:
        now = utcnow()
        actor = ctx.user.id
        try:
            with self.session.begin():
                position = self._get_position(ctx, position_id)
                self._require(ctx, position)
                role = self.roles.get(ctx.company.id, role_id)
                if role is None:
                    raise RoleNotFoundError()

                # Delegación: no se puede dar al puesto un rol con más poder del propio.
                ensure_can_delegate(ctx, self.access.get_role_grants(role.id), position.area_id)

                link = self.positions.find_role_link(position.id, role.id)
                if link is not None and link.is_active and link.deleted_at is None:
                    raise RoleAlreadyLinkedError()

                after = {"position_id": position.id, "role_id": role.id, "is_active": True}
                if link is None:
                    link = self.positions.add(
                        PositionRole(
                            company_id=ctx.company.id,
                            position_id=position.id,
                            role_id=role.id,
                            **audit_create(actor, now),
                        )
                    )
                    action, before = "position_role.created", {}
                else:
                    before = {"is_active": link.is_active, "deleted_at": _iso(link.deleted_at)}
                    restore(link, actor, now)
                    action = "position_role.restored"

                self.positions.add_history(
                    history_event(action, link.id, ctx.company.id, actor, now, before=before, after=after)
                )
                links = self.positions.list_role_links(position.id)
        except IntegrityError as exc:
            raise RoleAlreadyLinkedError() from exc
        return [_to_out(link, role) for link, role in links]

    def remove_role(self, ctx: CompanyContext, position_id: str, role_id: str) -> None:
        now = utcnow()
        actor = ctx.user.id
        with self.session.begin():
            guard = LastAdminGuard(self.session, ctx.company.id)
            position = self._get_position(ctx, position_id)
            self._require(ctx, position)
            link = self.positions.find_role_link(position.id, role_id)
            if link is None or link.deleted_at is not None:
                raise RoleNotLinkedError()
            soft_delete(link, actor, now)
            self.positions.add_history(
                history_event(
                    "position_role.deleted", link.id, ctx.company.id, actor, now,
                    before={"position_id": position.id, "role_id": role_id, "is_active": True},
                    after={"is_active": False, "deleted_at": now.isoformat()},
                )
            )
            guard.check()

    def _get_position(self, ctx: CompanyContext, position_id: str) -> Position:
        row = self.positions.get(ctx.company.id, position_id)
        if row is None:
            raise PositionNotFoundError()
        return row[0]

    @staticmethod
    def _require(ctx: CompanyContext, position: Position) -> None:
        if not ctx.can(PERMISSION, area_id=position.area_id):
            raise PermissionDeniedError()


def _to_out(link: PositionRole, role) -> PositionRoleOut:
    return PositionRoleOut(
        role_id=role.id,
        code=role.code,
        name=role.name,
        is_active=link.is_active and role.is_active,
    )


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None
