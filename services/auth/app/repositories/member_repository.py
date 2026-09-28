from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import (
    Area,
    Assignment,
    ChangeHistory,
    Membership,
    Position,
    Profile,
    User,
)


class MemberRepository:
    """Membresías (miembros de la empresa) y sus asignaciones a puestos.

    Las membresías siempre se buscan dentro de company_id (aislamiento).
    """

    def __init__(self, session: Session):
        self.session = session

    def list_members(self, company_id: str) -> list[tuple[Membership, User]]:
        """Membresías sin baja lógica, activas o suspendidas."""
        statement = (
            select(Membership, User)
            .join(User, User.id == Membership.user_id)
            .where(Membership.company_id == company_id, Membership.deleted_at.is_(None))
            .order_by(User.email)
        )
        return list(self.session.execute(statement).tuples())

    def get_member(self, company_id: str, membership_id: str) -> tuple[Membership, User] | None:
        statement = (
            select(Membership, User)
            .join(User, User.id == Membership.user_id)
            .where(
                Membership.id == membership_id,
                Membership.company_id == company_id,
                Membership.deleted_at.is_(None),
            )
        )
        return self.session.execute(statement).tuples().first()

    def find_membership(self, user_id: str, company_id: str) -> Membership | None:
        """Incluye membresías dadas de baja: la unicidad (usuario, empresa) es permanente."""
        return self.session.scalar(
            select(Membership).where(
                Membership.user_id == user_id, Membership.company_id == company_id
            )
        )

    def list_positions(
        self, membership_ids: list[str]
    ) -> list[tuple[str, Position, Area]]:
        """Puestos asignados (asignaciones sin baja), como (membership_id, puesto, área)."""
        statement = (
            select(Assignment.membership_id, Position, Area)
            .join(Position, Position.id == Assignment.position_id)
            .join(Area, Area.id == Position.area_id)
            .where(
                Assignment.membership_id.in_(membership_ids),
                Assignment.deleted_at.is_(None),
                Position.deleted_at.is_(None),
            )
            .order_by(Position.name)
        )
        return list(self.session.execute(statement).tuples())

    def get_profiles(self, user_ids: list[str]) -> dict[str, Profile]:
        profiles = self.session.scalars(select(Profile).where(Profile.user_id.in_(user_ids)))
        return {profile.user_id: profile for profile in profiles}

    def find_assignment(self, membership_id: str, position_id: str) -> Assignment | None:
        """Incluye asignaciones dadas de baja: la unicidad es permanente."""
        return self.session.scalar(
            select(Assignment).where(
                Assignment.membership_id == membership_id,
                Assignment.position_id == position_id,
            )
        )

    def list_assignments(self, membership_id: str) -> list[Assignment]:
        """Asignaciones sin baja lógica del miembro (activas o suspendidas)."""
        return list(
            self.session.scalars(
                select(Assignment).where(
                    Assignment.membership_id == membership_id,
                    Assignment.deleted_at.is_(None),
                )
            )
        )

    def add(self, entity):
        self.session.add(entity)
        self.session.flush()
        return entity

    def add_history(self, event: ChangeHistory) -> None:
        self.session.add(event)
