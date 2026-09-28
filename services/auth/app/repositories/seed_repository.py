from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import (
    Area,
    Assignment,
    ChangeHistory,
    Company,
    Country,
    IdentityDocumentType,
    Membership,
    Permission,
    Position,
    PositionRole,
    Role,
    RolePermission,
)


class SeedRepository:
    """Consultas del seed.

    A propósito NO filtran is_active ni deleted_at: un registro dado de baja
    existe, y el seed no debe duplicarlo ni reactivarlo.
    """

    def __init__(self, session: Session):
        self.session = session

    def get_company_by_code(self, code: str) -> Company | None:
        return self.session.scalar(select(Company).where(Company.code == code))

    def get_area(self, company_id: str, code: str) -> Area | None:
        return self.session.scalar(
            select(Area).where(Area.company_id == company_id, Area.code == code)
        )

    def get_position(self, company_id: str, code: str) -> Position | None:
        return self.session.scalar(
            select(Position).where(
                Position.company_id == company_id, Position.code == code
            )
        )

    def get_role(self, company_id: str, code: str) -> Role | None:
        return self.session.scalar(
            select(Role).where(Role.company_id == company_id, Role.code == code)
        )

    def get_country(self, code: str) -> Country | None:
        return self.session.scalar(select(Country).where(Country.code == code))

    def get_document_type(self, country_code: str, code: str) -> IdentityDocumentType | None:
        return self.session.scalar(
            select(IdentityDocumentType).where(
                IdentityDocumentType.issuing_country_code == country_code,
                IdentityDocumentType.code == code,
            )
        )

    def get_permission(self, code: str) -> Permission | None:
        return self.session.scalar(select(Permission).where(Permission.code == code))

    def get_role_permission(
        self, role_id: str, permission_id: str, scope: str
    ) -> RolePermission | None:
        return self.session.scalar(
            select(RolePermission).where(
                RolePermission.role_id == role_id,
                RolePermission.permission_id == permission_id,
                RolePermission.scope == scope,
            )
        )

    def get_position_role(self, position_id: str, role_id: str) -> PositionRole | None:
        return self.session.scalar(
            select(PositionRole).where(
                PositionRole.position_id == position_id,
                PositionRole.role_id == role_id,
            )
        )

    def get_membership(self, user_id: str, company_id: str) -> Membership | None:
        return self.session.scalar(
            select(Membership).where(
                Membership.user_id == user_id, Membership.company_id == company_id
            )
        )

    def get_assignment(self, membership_id: str, position_id: str) -> Assignment | None:
        return self.session.scalar(
            select(Assignment).where(
                Assignment.membership_id == membership_id,
                Assignment.position_id == position_id,
            )
        )

    def add(self, entity):
        """Añade una entidad preparada por el service; el flush genera su id."""
        self.session.add(entity)
        self.session.flush()
        return entity

    def add_history(self, event: ChangeHistory) -> None:
        self.session.add(event)
