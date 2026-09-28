"""Operaciones del master admin (is_platform_admin) sobre toda la plataforma.

- Vistas generales de solo lectura: un llamado por tipo de recurso, de todas
  las empresas o de una, para no consultar empresa por empresa.
- Empresas: crear, renombrar, desactivar y reactivar. No es un permiso de
  empresa: crear una empresa no ocurre dentro de una empresa. No se eliminan:
  desactivar congela todo (nadie opera en ella) y reactivar lo devuelve tal
  como estaba, sin tocar miembros, puestos ni roles.
- Usuarios: listarlos y cerrar todas sus sesiones (cuenta comprometida).

La estructura interna de cada empresa (áreas, puestos, roles, miembros) se
modifica por las rutas empresariales con X-Company-Id, donde el master admin
tiene todos los permisos: así reglas e historial están en un solo lugar.
"""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.common.mixin_model import utcnow
from app.models.entities import Company, User
from app.repositories.admin_repository import AdminRepository
from app.schemas.admin import (
    AdminAreaOut,
    AdminCompanyOut,
    AdminPositionOut,
    AdminRoleOut,
    AdminUserDetailOut,
    AdminUserOut,
    CompanyCreate,
    HistoryEventOut,
    CompanyUpdate,
)
from app.schemas.common import Ref
from app.repositories.auth_repository import AuthRepository
from app.services.auth_service import AuthService
from app.services.profile_service import ProfileService
from app.services.user_service import UserService
from app.services.common import audit_create, history_event, touch
from app.services.position_service import to_out as position_to_out
from app.services.role_service import RoleService


class CompanyNotFoundError(Exception):
    """No existe o está dada de baja."""


class CompanyCodeExistsError(Exception):
    """El código ya está usado, incluso por una empresa dada de baja."""


class UserNotFoundError(Exception):
    """No existe o está dado de baja."""


def _ref(entity) -> Ref:
    return Ref(id=entity.id, code=entity.code, name=entity.name)


def _company_out(company: Company) -> AdminCompanyOut:
    return AdminCompanyOut(
        id=company.id,
        code=company.code,
        name=company.name,
        is_active=company.is_active,
        created_at=company.created_at,
    )


class AdminService:
    def __init__(self, session: Session):
        self.session = session
        self.repository = AdminRepository(session)

    # --- Vistas generales

    def list_companies(self, limit: int, offset: int) -> list[AdminCompanyOut]:
        with self.session.begin():
            companies = self.repository.list_companies(limit, offset)
        return [_company_out(c) for c in companies]

    def list_areas(self, company_id: str | None, limit: int, offset: int) -> list[AdminAreaOut]:
        with self.session.begin():
            rows = self.repository.list_areas(company_id, limit, offset)
        return [
            AdminAreaOut(
                id=area.id,
                code=area.code,
                name=area.name,
                is_active=area.is_active,
                company=_ref(company),
            )
            for area, company in rows
        ]

    def list_positions(self, company_id: str | None, limit: int, offset: int) -> list[AdminPositionOut]:
        with self.session.begin():
            rows = self.repository.list_positions(company_id, limit, offset)
        return [
            AdminPositionOut(**position_to_out(position, area).model_dump(), company=_ref(company))
            for position, area, company in rows
        ]

    def list_roles(self, company_id: str | None, limit: int, offset: int) -> list[AdminRoleOut]:
        with self.session.begin():
            rows = self.repository.list_roles(company_id, limit, offset)
            # Una sola consulta de permisos para todos los roles del listado.
            outs = RoleService(self.session).to_out_many([role for role, _ in rows])
        return [
            AdminRoleOut(**out.model_dump(), company=_ref(company))
            for out, (_, company) in zip(outs, rows)
        ]

    def list_users(self, email: str | None, limit: int, offset: int) -> list[AdminUserOut]:
        with self.session.begin():
            users = self.repository.list_users(email, limit, offset)
        return [
            AdminUserOut(
                id=u.id,
                email=u.email,
                is_active=u.is_active,
                is_platform_admin=u.is_platform_admin,
                created_at=u.created_at,
            )
            for u in users
        ]

    def list_history(
        self,
        company_id: str | None,
        resource_id: str | None,
        actor_id: str | None,
        action: str | None,
        limit: int,
        offset: int = 0,
    ) -> list[HistoryEventOut]:
        """También lo usa GET /history (admin de empresa) con company_id fijo."""
        with self.session.begin():
            rows = self.repository.list_history(company_id, resource_id, actor_id, action, limit, offset)
        return [
            HistoryEventOut(
                id=event.id,
                action=event.action,
                resource_id=event.resource_id,
                company_id=event.company_id,
                actor_id=event.created_by,
                actor_email=actor_email,
                before=event.before,
                after=event.after,
                created_at=event.created_at,
            )
            for event, actor_email in rows
        ]

    def get_user_detail(self, user_id: str) -> AdminUserDetailOut:
        """Cuenta, perfil, documentos, empresas y sesiones de un usuario.
        Incluye cuentas inhabilitadas o dadas de baja (el master ve todo).
        La consulta queda registrada en los logs (audit.logs: quién y cuándo)."""
        with self.session.begin():
            user = self.session.get(User, user_id)
            if user is None:
                raise UserNotFoundError()
            profile, documents = ProfileService(self.session).load(user.id)
            memberships = UserService(self.session).memberships_of(user.id)
            active_sessions = len(AuthRepository(self.session).list_active_sessions(user.id, utcnow()))
        return AdminUserDetailOut(
            id=user.id,
            email=user.email,
            is_active=user.is_active,
            deleted_at=user.deleted_at,
            is_platform_admin=user.is_platform_admin,
            max_sessions=user.max_sessions,
            created_at=user.created_at,
            updated_at=user.updated_at,
            profile=profile,
            documents=documents,
            memberships=memberships,
            active_sessions=active_sessions,
        )

    # --- Empresas

    def create_company(self, actor: User, data: CompanyCreate) -> AdminCompanyOut:
        now = utcnow()
        try:
            with self.session.begin():
                if self.repository.get_company_by_code(data.code) is not None:
                    raise CompanyCodeExistsError()
                company = self.repository.add(
                    Company(code=data.code, name=data.name, **audit_create(actor.id, now))
                )
                self.repository.add_history(
                    history_event(
                        "company.created", company.id, company.id, actor.id, now,
                        before={},
                        after={"code": company.code, "name": company.name, "is_active": True},
                    )
                )
        except IntegrityError as exc:
            raise CompanyCodeExistsError() from exc
        return _company_out(company)

    def update_company(self, actor: User, company_id: str, data: CompanyUpdate) -> AdminCompanyOut:
        now = utcnow()
        with self.session.begin():
            company = self._get_company(company_id)
            if company.name != data.name:
                before = {"name": company.name}
                company.name = data.name
                touch(company, actor.id, now)
                self.repository.add_history(
                    history_event(
                        "company.updated", company.id, company.id, actor.id, now,
                        before=before,
                        after={"name": company.name},
                    )
                )
        return _company_out(company)

    def set_company_status(self, actor: User, company_id: str, is_active: bool) -> AdminCompanyOut:
        """Desactiva o reactiva. Desactivada, X-Company-Id la rechaza para todos
        (incluido el master) y desaparece de /me; sus datos se conservan."""
        now = utcnow()
        with self.session.begin():
            company = self._get_company(company_id)
            if company.is_active != is_active:
                company.is_active = is_active
                touch(company, actor.id, now)
                self.repository.add_history(
                    history_event(
                        "company.activated" if is_active else "company.deactivated",
                        company.id, company.id, actor.id, now,
                        before={"is_active": not is_active},
                        after={"is_active": is_active},
                    )
                )
        return _company_out(company)

    # --- Usuarios

    def revoke_user_sessions(self, actor: User, user_id: str) -> int:
        """Cierra todas las sesiones de un usuario (por ejemplo, cuenta comprometida).
        El historial registra al master admin como actor."""
        with self.session.begin():
            if self.repository.get_user(user_id) is None:
                raise UserNotFoundError()
        return AuthService(self.session).revoke_user_sessions(
            user_id, actor_id=actor.id, reason="admin_revoked"
        )

    def _get_company(self, company_id: str) -> Company:
        company = self.repository.get_company(company_id)
        if company is None:
            raise CompanyNotFoundError()
        return company
