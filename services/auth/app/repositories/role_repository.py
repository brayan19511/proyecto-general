from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.entities import ChangeHistory, Permission, PositionRole, Role, RolePermission


class RoleRepository:
    """Consultas de roles y sus permisos. Los roles siempre se buscan dentro de
    company_id (aislamiento); los permisos son un catálogo global."""

    def __init__(self, session: Session):
        self.session = session

    def list_by_company(
        self, company_id: str, limit: int, offset: int, include_deleted: bool = False
    ) -> list[Role]:
        """Roles activos o suspendidos (con include_deleted, también dados de baja)."""
        statement = select(Role).where(Role.company_id == company_id)
        if not include_deleted:
            statement = statement.where(Role.deleted_at.is_(None))
        return list(self.session.scalars(statement.order_by(Role.name).limit(limit).offset(offset)))

    def get_any(self, company_id: str, role_id: str) -> Role | None:
        """Un rol de esta empresa, incluso dado de baja (para restaurarlo)."""
        return self.session.scalar(
            select(Role).where(Role.id == role_id, Role.company_id == company_id)
        )

    def get(self, company_id: str, role_id: str) -> Role | None:
        """Un rol sin baja lógica de esta empresa. Un id de otra empresa da None."""
        return self.session.scalar(
            select(Role).where(
                Role.id == role_id,
                Role.company_id == company_id,
                Role.deleted_at.is_(None),
            )
        )

    def get_by_code(self, company_id: str, code: str) -> Role | None:
        """Incluye roles dados de baja: su código sigue reservado."""
        return self.session.scalar(
            select(Role).where(Role.company_id == company_id, Role.code == code)
        )

    def list_grants(self, role_ids: list[str]) -> list[tuple[RolePermission, Permission]]:
        """Concesiones vigentes (sin baja) de varios roles, con su permiso."""
        statement = (
            select(RolePermission, Permission)
            .join(Permission, Permission.id == RolePermission.permission_id)
            .where(
                RolePermission.role_id.in_(role_ids),
                RolePermission.deleted_at.is_(None),
            )
            .order_by(Permission.code, RolePermission.scope)
        )
        return list(self.session.execute(statement).tuples())

    def get_grant(self, role_id: str, grant_id: str) -> RolePermission | None:
        """Una concesión vigente del rol."""
        return self.session.scalar(
            select(RolePermission).where(
                RolePermission.id == grant_id,
                RolePermission.role_id == role_id,
                RolePermission.deleted_at.is_(None),
            )
        )

    def find_grant(self, role_id: str, permission_id: str, scope: str) -> RolePermission | None:
        """La concesión exacta, incluso retirada: la unicidad de la tabla es
        permanente, así que volver a otorgarla significa restaurar esa fila."""
        return self.session.scalar(
            select(RolePermission).where(
                RolePermission.role_id == role_id,
                RolePermission.permission_id == permission_id,
                RolePermission.scope == scope,
            )
        )

    def get_permission(self, code: str) -> Permission | None:
        return self.session.scalar(
            select(Permission).where(
                Permission.code == code,
                Permission.is_active.is_(True),
                Permission.deleted_at.is_(None),
            )
        )

    def get_permission_by_id(self, permission_id: str) -> Permission:
        return self.session.get(Permission, permission_id)

    def count_position_links(self, role_id: str) -> int:
        """Puestos que heredan el rol (relaciones puesto-rol sin baja)."""
        return self.session.scalar(
            select(func.count())
            .select_from(PositionRole)
            .where(PositionRole.role_id == role_id, PositionRole.deleted_at.is_(None))
        )

    def add(self, entity):
        self.session.add(entity)
        self.session.flush()
        return entity

    def add_history(self, event: ChangeHistory) -> None:
        self.session.add(event)
