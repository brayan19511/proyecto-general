from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.entities import Area, ChangeHistory, Position


class AreaRepository:
    """Consultas de áreas. Todas reciben company_id: nunca se busca un área
    fuera de la empresa activa (aislamiento entre empresas)."""

    def __init__(self, session: Session):
        self.session = session

    def list_by_company(
        self, company_id: str, limit: int, offset: int, include_deleted: bool = False
    ) -> list[Area]:
        """Áreas activas o suspendidas; con include_deleted, también las dadas de baja."""
        statement = select(Area).where(Area.company_id == company_id)
        if not include_deleted:
            statement = statement.where(Area.deleted_at.is_(None))
        return list(self.session.scalars(statement.order_by(Area.name).limit(limit).offset(offset)))

    def get_any(self, company_id: str, area_id: str) -> Area | None:
        """Un área de esta empresa, incluso dada de baja (para restaurarla)."""
        return self.session.scalar(
            select(Area).where(Area.id == area_id, Area.company_id == company_id)
        )

    def get(self, company_id: str, area_id: str) -> Area | None:
        """Un área sin baja lógica de esta empresa. Un id de otra empresa da None."""
        return self.session.scalar(
            select(Area).where(
                Area.id == area_id,
                Area.company_id == company_id,
                Area.deleted_at.is_(None),
            )
        )

    def get_by_code(self, company_id: str, code: str) -> Area | None:
        """Incluye áreas dadas de baja: su código sigue reservado."""
        return self.session.scalar(
            select(Area).where(Area.company_id == company_id, Area.code == code)
        )

    def count_positions(self, area_id: str) -> int:
        """Puestos sin baja lógica del área, activos o suspendidos."""
        return self.session.scalar(
            select(func.count())
            .select_from(Position)
            .where(Position.area_id == area_id, Position.deleted_at.is_(None))
        )

    def add(self, area: Area) -> Area:
        self.session.add(area)
        self.session.flush()
        return area

    def add_history(self, event: ChangeHistory) -> None:
        self.session.add(event)
