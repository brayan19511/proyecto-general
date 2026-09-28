from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import Area, ChangeHistory, Company, Position, Role, User


class AdminRepository:
    """Consultas de las vistas del master admin: abarcan todas las empresas.

    company_id opcional: None lista todo; con valor, filtra por esa empresa.
    Excluyen registros dados de baja, igual que los listados por empresa.
    """

    def __init__(self, session: Session):
        self.session = session

    def list_companies(self, limit: int, offset: int) -> list[Company]:
        return list(
            self.session.scalars(
                select(Company)
                .where(Company.deleted_at.is_(None))
                .order_by(Company.name)
                .limit(limit)
                .offset(offset)
            )
        )

    def list_areas(self, company_id: str | None, limit: int, offset: int) -> list[tuple[Area, Company]]:
        statement = (
            select(Area, Company)
            .join(Company, Company.id == Area.company_id)
            .where(Area.deleted_at.is_(None), Company.deleted_at.is_(None))
            .order_by(Company.name, Area.name)
            .limit(limit)
            .offset(offset)
        )
        if company_id is not None:
            statement = statement.where(Area.company_id == company_id)
        return list(self.session.execute(statement).tuples())

    def list_positions(
        self, company_id: str | None, limit: int, offset: int
    ) -> list[tuple[Position, Area, Company]]:
        statement = (
            select(Position, Area, Company)
            .join(Area, Area.id == Position.area_id)
            .join(Company, Company.id == Position.company_id)
            .where(Position.deleted_at.is_(None), Company.deleted_at.is_(None))
            .order_by(Company.name, Area.name, Position.name)
            .limit(limit)
            .offset(offset)
        )
        if company_id is not None:
            statement = statement.where(Position.company_id == company_id)
        return list(self.session.execute(statement).tuples())

    def list_roles(self, company_id: str | None, limit: int, offset: int) -> list[tuple[Role, Company]]:
        statement = (
            select(Role, Company)
            .join(Company, Company.id == Role.company_id)
            .where(Role.deleted_at.is_(None), Company.deleted_at.is_(None))
            .order_by(Company.name, Role.name)
            .limit(limit)
            .offset(offset)
        )
        if company_id is not None:
            statement = statement.where(Role.company_id == company_id)
        return list(self.session.execute(statement).tuples())

    def get_company(self, company_id: str) -> Company | None:
        """Empresa sin baja lógica, activa o suspendida."""
        return self.session.scalar(
            select(Company).where(Company.id == company_id, Company.deleted_at.is_(None))
        )

    def get_company_by_code(self, code: str) -> Company | None:
        """Incluye empresas dadas de baja: su código sigue reservado."""
        return self.session.scalar(select(Company).where(Company.code == code))

    def list_users(self, email: str | None, limit: int, offset: int) -> list[User]:
        """Usuarios sin baja lógica. email filtra por coincidencia parcial."""
        statement = (
            select(User).where(User.deleted_at.is_(None)).order_by(User.email).limit(limit).offset(offset)
        )
        if email:
            statement = statement.where(User.email.contains(email.strip().lower(), autoescape=True))
        return list(self.session.scalars(statement))

    def get_user(self, user_id: str) -> User | None:
        return self.session.scalar(
            select(User).where(User.id == user_id, User.deleted_at.is_(None))
        )

    def list_history(
        self,
        company_id: str | None,
        resource_id: str | None,
        actor_id: str | None,
        action: str | None,
        limit: int,
        offset: int = 0,
    ) -> list[tuple[ChangeHistory, str | None]]:
        """Eventos más recientes primero, con el email del actor si lo hay.
        action filtra por prefijo: "membership." trae todas las de membresías."""
        statement = (
            select(ChangeHistory, User.email)
            .outerjoin(User, User.id == ChangeHistory.created_by)
            .order_by(ChangeHistory.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if company_id is not None:
            statement = statement.where(ChangeHistory.company_id == company_id)
        if resource_id is not None:
            statement = statement.where(ChangeHistory.resource_id == resource_id)
        if actor_id is not None:
            statement = statement.where(ChangeHistory.created_by == actor_id)
        if action:
            statement = statement.where(ChangeHistory.action.startswith(action, autoescape=True))
        return list(self.session.execute(statement).tuples())

    def add(self, entity):
        self.session.add(entity)
        self.session.flush()
        return entity

    def add_history(self, event: ChangeHistory) -> None:
        self.session.add(event)
