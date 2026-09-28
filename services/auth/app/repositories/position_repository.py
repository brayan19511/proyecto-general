from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.entities import Area, Assignment, ChangeHistory, Position, PositionRole, Role


class PositionRepository:
    """Consultas de puestos. Todas reciben company_id (aislamiento entre empresas).

    Devuelven el puesto junto con su área, porque la respuesta la incluye y
    los permisos de alcance area dependen de ella.
    """

    def __init__(self, session: Session):
        self.session = session

    def list_by_company(
        self, company_id: str, limit: int, offset: int, include_deleted: bool = False
    ) -> list[tuple[Position, Area]]:
        """Puestos activos o suspendidos (con include_deleted, también dados de baja)."""
        statement = (
            select(Position, Area)
            .join(Area, Area.id == Position.area_id)
            .where(Position.company_id == company_id)
        )
        if not include_deleted:
            statement = statement.where(Position.deleted_at.is_(None))
        statement = statement.order_by(Area.name, Position.name).limit(limit).offset(offset)
        return list(self.session.execute(statement).tuples())

    def get_any(self, company_id: str, position_id: str) -> tuple[Position, Area] | None:
        """Un puesto de esta empresa, incluso dado de baja (para restaurarlo)."""
        statement = (
            select(Position, Area)
            .join(Area, Area.id == Position.area_id)
            .where(Position.id == position_id, Position.company_id == company_id)
        )
        return self.session.execute(statement).tuples().first()

    def get(self, company_id: str, position_id: str) -> tuple[Position, Area] | None:
        """Un puesto sin baja lógica de esta empresa. Un id de otra empresa da None."""
        statement = (
            select(Position, Area)
            .join(Area, Area.id == Position.area_id)
            .where(
                Position.id == position_id,
                Position.company_id == company_id,
                Position.deleted_at.is_(None),
            )
        )
        return self.session.execute(statement).tuples().first()

    def get_by_code(self, company_id: str, code: str) -> Position | None:
        """Incluye puestos dados de baja: su código sigue reservado."""
        return self.session.scalar(
            select(Position).where(
                Position.company_id == company_id, Position.code == code
            )
        )

    def count_assignments(self, position_id: str) -> int:
        """Personas asignadas al puesto (asignaciones sin baja lógica)."""
        return self.session.scalar(
            select(func.count())
            .select_from(Assignment)
            .where(
                Assignment.position_id == position_id,
                Assignment.deleted_at.is_(None),
            )
        )

    def list_role_links(self, position_id: str) -> list[tuple[PositionRole, Role]]:
        """Roles vinculados al puesto (vínculos sin baja lógica)."""
        statement = (
            select(PositionRole, Role)
            .join(Role, Role.id == PositionRole.role_id)
            .where(
                PositionRole.position_id == position_id,
                PositionRole.deleted_at.is_(None),
            )
            .order_by(Role.name)
        )
        return list(self.session.execute(statement).tuples())

    def find_role_link(self, position_id: str, role_id: str) -> PositionRole | None:
        """El vínculo exacto, incluso dado de baja: la unicidad es permanente,
        así que volver a vincular significa restaurar esa fila."""
        return self.session.scalar(
            select(PositionRole).where(
                PositionRole.position_id == position_id,
                PositionRole.role_id == role_id,
            )
        )

    def add(self, entity):
        self.session.add(entity)
        self.session.flush()
        return entity

    def add_history(self, event: ChangeHistory) -> None:
        self.session.add(event)
