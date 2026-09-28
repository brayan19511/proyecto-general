"""Miembros de la empresa activa (membresías) y sus puestos (asignaciones).

Autorización:
  - Ver miembros: users.read.
      company → todos los miembros.
      area    → los que tienen un puesto en sus áreas, y los que aún no tienen
                ningún puesto (para poder asignarlos).
  - Agregar, suspender, reactivar o retirar miembros: memberships.manage con
    alcance company. Una membresía sola no concede permisos, pero da acceso
    a la empresa.
  - Asignar un puesto: memberships.manage en el área del puesto + delegación
    de los permisos que otorga el puesto (ensure_can_delegate).
  - Quitar un puesto: memberships.manage en el área del puesto.

Reglas:
  - Solo se agrega a un usuario ya registrado y habilitado, por su email exacto.
  - Suspender (is_active=false): pierde el acceso de inmediato y conserva sus
    puestos; al reactivarlo vuelve tal como estaba.
  - Retirar (DELETE): en una sola operación da de baja la membresía y todos
    sus puestos, cada uno con su evento. Si vuelve, entra sin puestos: no
    recupera privilegios en silencio. Es una acción explícita del admin, no
    una cascada automática.
  - Volver a agregar o reasignar algo retirado restaura la misma fila
    (unicidad permanente) con su evento de historial.
"""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.common.mixin_model import utcnow
from app.models.entities import Assignment, Membership, Position, User
from app.repositories.access_repository import AccessRepository
from app.repositories.member_repository import MemberRepository
from app.repositories.position_repository import PositionRepository
from app.repositories.user_repository import UserRepository
from app.schemas.common import Ref
from app.schemas.member import MemberOut, MemberPositionOut
from app.services.access_service import (
    CompanyContext,
    LastAdminGuard,
    PermissionDeniedError,
    ensure_can_delegate,
)
from app.services.auth_service import user_can_login
from app.services.common import audit_create, history_event, restore, soft_delete, touch
from app.services.position_service import PositionNotFoundError

MANAGE = "memberships.manage"
READ = "users.read"


class MemberNotFoundError(Exception):
    """No es miembro, está dado de baja, es de otra empresa o no es visible."""


class UserNotFoundError(Exception):
    """No hay un usuario registrado y habilitado con ese email."""


class MemberExistsError(Exception):
    """Ya es miembro de la empresa."""


class AssignmentExistsError(Exception):
    """El miembro ya tiene ese puesto."""


class AssignmentNotFoundError(Exception):
    """El miembro no tiene ese puesto."""


class MemberService:
    def __init__(self, session: Session):
        self.session = session
        self.repository = MemberRepository(session)
        self.users = UserRepository(session)
        self.positions = PositionRepository(session)
        self.access = AccessRepository(session)

    # --- Lectura

    def list_all(self, ctx: CompanyContext, limit: int, offset: int) -> list[MemberOut]:
        with self.session.begin():
            members = self.repository.list_members(ctx.company.id)
            outs = self._to_out_many(members)
        # La visibilidad por área se decide en Python, así que se pagina después
        # de filtrar. Suficiente para empresas de cientos o miles de miembros.
        visible = [out for out in outs if self._visible(ctx, out)]
        return visible[offset : offset + limit]

    def get(self, ctx: CompanyContext, membership_id: str) -> MemberOut:
        with self.session.begin():
            out = self._get_out(ctx, membership_id)
        if not self._visible(ctx, out):
            raise MemberNotFoundError()  # Invisible = inexistente para quien pregunta.
        return out

    # --- Membresías

    def add(self, ctx: CompanyContext, email: str) -> MemberOut:
        self._require_company(ctx)
        now = utcnow()
        actor = ctx.user.id
        email = email.strip().lower()  # Misma normalización que el registro.
        try:
            with self.session.begin():
                user = self.users.get_user_by_email(email)
                if user is None or not user_can_login(user):
                    raise UserNotFoundError()

                membership = self.repository.find_membership(user.id, ctx.company.id)
                if membership is not None and membership.deleted_at is None:
                    raise MemberExistsError()

                after = {"user_id": user.id, "is_active": True}
                if membership is None:
                    membership = self.repository.add(
                        Membership(user_id=user.id, company_id=ctx.company.id, **audit_create(actor, now))
                    )
                    action, before = "membership.created", {}
                else:
                    before = {"is_active": False, "deleted_at": membership.deleted_at.isoformat()}
                    restore(membership, actor, now)
                    action = "membership.restored"

                self.repository.add_history(
                    history_event(action, membership.id, ctx.company.id, actor, now, before=before, after=after)
                )
                out = self._to_out_many([(membership, user)])[0]
        except IntegrityError as exc:
            raise MemberExistsError() from exc
        return out

    def set_status(self, ctx: CompanyContext, membership_id: str, is_active: bool) -> MemberOut:
        """Suspende o reactiva. Los puestos no se tocan."""
        self._require_company(ctx)
        now = utcnow()
        actor = ctx.user.id
        with self.session.begin():
            guard = LastAdminGuard(self.session, ctx.company.id)
            membership, _ = self._get_row(ctx, membership_id)
            if membership.is_active != is_active:
                membership.is_active = is_active
                touch(membership, actor, now)
                self.repository.add_history(
                    history_event(
                        "membership.reactivated" if is_active else "membership.suspended",
                        membership.id, ctx.company.id, actor, now,
                        before={"is_active": not is_active},
                        after={"is_active": is_active},
                    )
                )
            guard.check()  # No se puede suspender al último admin de la empresa.
            return self._get_out(ctx, membership.id)

    def remove(self, ctx: CompanyContext, membership_id: str) -> None:
        """Retira al miembro y todos sus puestos en una sola transacción."""
        self._require_company(ctx)
        now = utcnow()
        actor = ctx.user.id
        with self.session.begin():
            guard = LastAdminGuard(self.session, ctx.company.id)
            membership, _ = self._get_row(ctx, membership_id)
            for assignment in self.repository.list_assignments(membership.id):
                soft_delete(assignment, actor, now)
                self.repository.add_history(
                    history_event(
                        "assignment.deleted", assignment.id, ctx.company.id, actor, now,
                        before={
                            "membership_id": membership.id,
                            "position_id": assignment.position_id,
                            "is_active": True,
                        },
                        after={
                            "is_active": False,
                            "deleted_at": now.isoformat(),
                            "reason": "membership_removed",
                        },
                    )
                )
            before = {"is_active": membership.is_active, "deleted_at": None}
            soft_delete(membership, actor, now)
            self.repository.add_history(
                history_event(
                    "membership.deleted", membership.id, ctx.company.id, actor, now,
                    before=before,
                    after={"is_active": False, "deleted_at": now.isoformat()},
                )
            )
            guard.check()

    # --- Asignaciones

    def assign(self, ctx: CompanyContext, membership_id: str, position_id: str) -> MemberOut:
        now = utcnow()
        actor = ctx.user.id
        try:
            with self.session.begin():
                membership, _ = self._get_row(ctx, membership_id)
                position = self._get_position(ctx, position_id)
                if not ctx.can(MANAGE, area_id=position.area_id):
                    raise PermissionDeniedError()
                # Delegación: el puesto no puede otorgar más de lo que tiene quien asigna.
                ensure_can_delegate(ctx, self.access.get_position_grants(position.id), position.area_id)

                assignment = self.repository.find_assignment(membership.id, position.id)
                if assignment is not None and assignment.deleted_at is None:
                    raise AssignmentExistsError()

                after = {"membership_id": membership.id, "position_id": position.id, "is_active": True}
                if assignment is None:
                    assignment = self.repository.add(
                        Assignment(
                            company_id=ctx.company.id,
                            membership_id=membership.id,
                            position_id=position.id,
                            **audit_create(actor, now),
                        )
                    )
                    action, before = "assignment.created", {}
                else:
                    before = {"is_active": False, "deleted_at": assignment.deleted_at.isoformat()}
                    restore(assignment, actor, now)
                    action = "assignment.restored"

                self.repository.add_history(
                    history_event(action, assignment.id, ctx.company.id, actor, now, before=before, after=after)
                )
                out = self._get_out(ctx, membership.id)
        except IntegrityError as exc:
            raise AssignmentExistsError() from exc
        return out

    def unassign(self, ctx: CompanyContext, membership_id: str, position_id: str) -> None:
        now = utcnow()
        actor = ctx.user.id
        with self.session.begin():
            guard = LastAdminGuard(self.session, ctx.company.id)
            membership, _ = self._get_row(ctx, membership_id)
            position = self._get_position(ctx, position_id)
            if not ctx.can(MANAGE, area_id=position.area_id):
                raise PermissionDeniedError()
            assignment = self.repository.find_assignment(membership.id, position.id)
            if assignment is None or assignment.deleted_at is not None:
                raise AssignmentNotFoundError()
            soft_delete(assignment, actor, now)
            self.repository.add_history(
                history_event(
                    "assignment.deleted", assignment.id, ctx.company.id, actor, now,
                    before={"membership_id": membership.id, "position_id": position.id, "is_active": True},
                    after={"is_active": False, "deleted_at": now.isoformat()},
                )
            )
            guard.check()

    # --- Internos

    def _get_row(self, ctx: CompanyContext, membership_id: str) -> tuple[Membership, User]:
        row = self.repository.get_member(ctx.company.id, membership_id)
        if row is None:
            raise MemberNotFoundError()
        return row

    def _get_out(self, ctx: CompanyContext, membership_id: str) -> MemberOut:
        return self._to_out_many([self._get_row(ctx, membership_id)])[0]

    def _get_position(self, ctx: CompanyContext, position_id: str) -> Position:
        row = self.positions.get(ctx.company.id, position_id)
        if row is None:
            raise PositionNotFoundError()
        return row[0]

    def _to_out_many(self, members: list[tuple[Membership, User]]) -> list[MemberOut]:
        """Tres consultas para todo el listado: miembros, puestos y perfiles."""
        positions = self.repository.list_positions([m.id for m, _ in members])
        profiles = self.repository.get_profiles([u.id for _, u in members])

        by_membership: dict[str, list[MemberPositionOut]] = {}
        for membership_id, position, area in positions:
            by_membership.setdefault(membership_id, []).append(
                MemberPositionOut(
                    id=position.id,
                    code=position.code,
                    name=position.name,
                    area=Ref(id=area.id, code=area.code, name=area.name),
                )
            )

        outs = []
        for membership, user in members:
            profile = profiles.get(user.id)
            outs.append(
                MemberOut(
                    id=membership.id,
                    user_id=user.id,
                    email=user.email,
                    first_names=profile.first_names if profile else None,
                    last_names=profile.last_names if profile else None,
                    is_active=membership.is_active,
                    positions=by_membership.get(membership.id, []),
                    created_at=membership.created_at,
                )
            )
        return outs

    @staticmethod
    def _visible(ctx: CompanyContext, member: MemberOut) -> bool:
        if ctx.can(READ):  # Alcance company o master admin.
            return True
        if not member.positions:
            return ctx.has_any(READ)  # Sin puesto: visible para asignarlo.
        return any(ctx.can(READ, area_id=p.area.id) for p in member.positions)

    @staticmethod
    def _require_company(ctx: CompanyContext) -> None:
        if not ctx.can(MANAGE):
            raise PermissionDeniedError()
