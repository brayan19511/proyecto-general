from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import (
    Area,
    Assignment,
    ChangeHistory,
    Company,
    Membership,
    Position,
    PositionRole,
    Profile,
    Role,
    User,
)


def _usable(model) -> tuple:
    """Condiciones de un registro utilizable: habilitado y sin baja lógica."""
    return (model.is_active.is_(True), model.deleted_at.is_(None))


class UserRepository:
    def __init__(self, session: Session):
        # El service proporciona la sesión que compartirán sus operaciones.
        self.session = session

    def get_user_by_id(self, user_id: str) -> User | None:
        """Obtiene un usuario habilitado y sin baja lógica."""
        statement = select(User).where(
            User.id == user_id,
            User.is_active.is_(True),
            User.deleted_at.is_(None),
        )

        return self.session.scalar(statement)

    def get_user_by_email(self, email: str) -> User | None:
        """Busca un email ya normalizado, incluyendo cuentas dadas de baja."""
        statement = select(User).where(User.email == email)
        return self.session.scalar(statement)

    def add(self, user: User) -> User:
        """Añade un usuario preparado por el service, sin confirmar cambios."""
        self.session.add(user)
        self.session.flush()

        return user

    def add_profile(self, profile: Profile) -> Profile:
        """Añade un perfil de usuario preparado por el service, sin confirmar cambios."""
        self.session.add(profile)
        self.session.flush()
        return profile

    def add_history(self, event: ChangeHistory) -> None:
        """Añade un evento; se confirmará junto con el usuario."""
        self.session.add(event)

    # --- Consultas de /me. Solo devuelven registros utilizables: si un
    # eslabón (empresa, membresía, asignación, puesto, área, rol) está
    # inhabilitado o dado de baja, lo que depende de él no aparece.

    def get_profile(self, user_id: str) -> Profile | None:
        return self.session.scalar(
            select(Profile).where(Profile.user_id == user_id, *_usable(Profile))
        )

    def get_memberships(self, user_id: str) -> list[tuple[Membership, Company]]:
        statement = (
            select(Membership, Company)
            .join(Company, Company.id == Membership.company_id)
            .where(
                Membership.user_id == user_id,
                *_usable(Membership),
                *_usable(Company),
            )
            .order_by(Company.name)
        )
        return list(self.session.execute(statement).tuples())

    def get_positions(
        self, membership_ids: list[str]
    ) -> list[tuple[str, Position, Area]]:
        """Puestos asignados, como (membership_id, puesto, área)."""
        statement = (
            select(Assignment.membership_id, Position, Area)
            .join(Position, Position.id == Assignment.position_id)
            .join(Area, Area.id == Position.area_id)
            .where(
                Assignment.membership_id.in_(membership_ids),
                *_usable(Assignment),
                *_usable(Position),
                *_usable(Area),
            )
            .order_by(Position.name)
        )
        return list(self.session.execute(statement).tuples())

    def get_role_codes(self, position_ids: list[str]) -> list[tuple[str, str]]:
        """Roles heredados por cada puesto, como (position_id, código del rol)."""
        statement = (
            select(PositionRole.position_id, Role.code)
            .join(Role, Role.id == PositionRole.role_id)
            .where(
                PositionRole.position_id.in_(position_ids),
                *_usable(PositionRole),
                *_usable(Role),
            )
            .order_by(Role.code)
        )
        return list(self.session.execute(statement).tuples())
