from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.entities import (
    Area,
    Assignment,
    Company,
    Membership,
    Permission,
    Position,
    PositionRole,
    Role,
    RolePermission,
    User,
)


def _usable(model) -> tuple:
    """Condiciones de un registro utilizable: habilitado y sin baja lógica."""
    return (model.is_active.is_(True), model.deleted_at.is_(None))


class AccessRepository:
    """Consultas para resolver la empresa activa y los permisos del usuario."""

    def __init__(self, session: Session):
        self.session = session

    def get_active_company(self, company_id: str) -> Company | None:
        return self.session.scalar(
            select(Company).where(Company.id == company_id, *_usable(Company))
        )

    def get_active_membership(self, user_id: str, company_id: str) -> Membership | None:
        return self.session.scalar(
            select(Membership).where(
                Membership.user_id == user_id,
                Membership.company_id == company_id,
                *_usable(Membership),
            )
        )

    def get_grants(self, membership_id: str) -> list[tuple[str, str, str]]:
        """Permisos heredados por la membresía, como (permiso, scope, area_id).

        Recorre la cadena completa y exige que cada eslabón sea utilizable:
        membresía → asignación → puesto → área → puesto-rol → rol
        → rol-permiso → permiso. Si uno está inhabilitado, no concede nada.
        area_id es el área del puesto: define el alcance de un scope "area".
        """
        statement = (
            select(Permission.code, RolePermission.scope, Position.area_id)
            .select_from(Assignment)
            .join(Position, Position.id == Assignment.position_id)
            .join(Area, Area.id == Position.area_id)
            .join(PositionRole, PositionRole.position_id == Position.id)
            .join(Role, Role.id == PositionRole.role_id)
            .join(RolePermission, RolePermission.role_id == Role.id)
            .join(Permission, Permission.id == RolePermission.permission_id)
            .where(
                Assignment.membership_id == membership_id,
                *_usable(Assignment),
                *_usable(Position),
                *_usable(Area),
                *_usable(PositionRole),
                *_usable(Role),
                *_usable(RolePermission),
                *_usable(Permission),
            )
        )
        return list(self.session.execute(statement).tuples())

    def lock_company(self, company_id: str) -> Company | None:
        """Bloquea la empresa: dos operaciones que podrían dejarla sin admin
        (por ejemplo, dos admins quitándose el puesto a la vez) se ejecutan en fila."""
        return self.session.scalar(
            select(Company)
            .where(Company.id == company_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    def count_company_admins(self, company_id: str, permission: str) -> int:
        """Usuarios activos con `permission` de alcance company por una cadena
        completamente utilizable (membresía → puesto → área → rol → permiso)."""
        statement = (
            select(func.count(func.distinct(Membership.user_id)))
            .select_from(Membership)
            .join(User, User.id == Membership.user_id)
            .join(Assignment, Assignment.membership_id == Membership.id)
            .join(Position, Position.id == Assignment.position_id)
            .join(Area, Area.id == Position.area_id)
            .join(PositionRole, PositionRole.position_id == Position.id)
            .join(Role, Role.id == PositionRole.role_id)
            .join(RolePermission, RolePermission.role_id == Role.id)
            .join(Permission, Permission.id == RolePermission.permission_id)
            .where(
                Membership.company_id == company_id,
                Permission.code == permission,
                RolePermission.scope == "company",
                *_usable(Membership),
                *_usable(User),
                *_usable(Assignment),
                *_usable(Position),
                *_usable(Area),
                *_usable(PositionRole),
                *_usable(Role),
                *_usable(RolePermission),
                *_usable(Permission),
            )
        )
        return self.session.scalar(statement)

    def get_role_grants(self, role_id: str) -> list[tuple[str, str]]:
        """Permisos vigentes que concede un rol, como (permiso, scope)."""
        statement = (
            select(Permission.code, RolePermission.scope)
            .join(Permission, Permission.id == RolePermission.permission_id)
            .where(
                RolePermission.role_id == role_id,
                *_usable(RolePermission),
                *_usable(Permission),
            )
        )
        return list(self.session.execute(statement).tuples())

    def get_position_grants(self, position_id: str) -> list[tuple[str, str]]:
        """Permisos vigentes que concede un puesto a través de sus roles."""
        statement = (
            select(Permission.code, RolePermission.scope)
            .select_from(PositionRole)
            .join(Role, Role.id == PositionRole.role_id)
            .join(RolePermission, RolePermission.role_id == Role.id)
            .join(Permission, Permission.id == RolePermission.permission_id)
            .where(
                PositionRole.position_id == position_id,
                *_usable(PositionRole),
                *_usable(Role),
                *_usable(RolePermission),
                *_usable(Permission),
            )
        )
        return list(self.session.execute(statement).tuples())

    def get_all_permission_codes(self) -> list[str]:
        """Catálogo activo completo: lo que tiene el master admin."""
        return list(
            self.session.scalars(
                select(Permission.code).where(*_usable(Permission)).order_by(Permission.code)
            )
        )
