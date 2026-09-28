"""CRUD de puestos de la empresa activa. Primer recurso con alcance de área.

Autorización:
  - Ver puestos: cualquier miembro de la empresa (o el master admin), igual
    que las áreas: es estructura de la organización.
  - Crear, renombrar y dar de baja: positions.manage en el área del puesto
    (alcance area) o en toda la empresa (alcance company).
  - Mover a otra área: solo alcance company (decisión del usuario).
  - Dar de baja un puesto con personas asignadas: 409 (decisión del usuario).
"""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.common.mixin_model import utcnow
from app.models.entities import Area, Position
from app.repositories.area_repository import AreaRepository
from app.repositories.position_repository import PositionRepository
from app.schemas.common import Ref
from app.schemas.position import PositionCreate, PositionOut, PositionUpdate
from app.services.access_service import CompanyContext, PermissionDeniedError
from app.services.area_service import AreaNotFoundError
from app.services.common import audit_create, history_event, restore, soft_delete, touch

PERMISSION = "positions.manage"


class PositionNotFoundError(Exception):
    """No existe, está dado de baja o es de otra empresa."""


class PositionCodeExistsError(Exception):
    """El código ya está usado en la empresa, incluso por un puesto dado de baja."""


class PositionAreaDeletedError(Exception):
    """El área del puesto está dada de baja: hay que restaurarla antes."""


class PositionInUseError(Exception):
    """El puesto tiene personas asignadas: darlo de baja les quitaría el acceso."""


def to_out(position: Position, area: Area) -> PositionOut:
    return PositionOut(
        id=position.id,
        code=position.code,
        name=position.name,
        is_active=position.is_active,
        deleted_at=position.deleted_at,
        area=Ref(id=area.id, code=area.code, name=area.name),
        created_at=position.created_at,
        updated_at=position.updated_at,
    )


class PositionService:
    def __init__(self, session: Session):
        self.session = session
        self.repository = PositionRepository(session)
        self.areas = AreaRepository(session)

    def list_all(
        self, ctx: CompanyContext, limit: int, offset: int, include_deleted: bool = False
    ) -> list[PositionOut]:
        with self.session.begin():
            rows = self.repository.list_by_company(ctx.company.id, limit, offset, include_deleted)
        return [to_out(position, area) for position, area in rows]

    def get(self, ctx: CompanyContext, position_id: str) -> PositionOut:
        with self.session.begin():
            position, area = self._get_or_404(ctx, position_id)
        return to_out(position, area)

    def create(self, ctx: CompanyContext, data: PositionCreate) -> PositionOut:
        now = utcnow()
        actor = ctx.user.id
        try:
            with self.session.begin():
                area = self._get_area_or_404(ctx, data.area_id)
                # Alcance area: solo en su propia área. Alcance company: en cualquiera.
                self._require(ctx, area_id=area.id)
                if self.repository.get_by_code(ctx.company.id, data.code) is not None:
                    raise PositionCodeExistsError()
                position = self.repository.add(
                    Position(
                        company_id=ctx.company.id,
                        area_id=area.id,
                        code=data.code,
                        name=data.name,
                        **audit_create(actor, now),
                    )
                )
                self.repository.add_history(
                    history_event(
                        "position.created", position.id, ctx.company.id, actor, now,
                        before={},
                        after={
                            "code": position.code,
                            "name": position.name,
                            "area_id": area.id,
                            "is_active": True,
                        },
                    )
                )
        except IntegrityError as exc:
            # Carrera: otra solicitud creó el mismo código entre la consulta y el INSERT.
            raise PositionCodeExistsError() from exc
        return to_out(position, area)

    def update(
        self, ctx: CompanyContext, position_id: str, data: PositionUpdate
    ) -> PositionOut:
        now = utcnow()
        actor = ctx.user.id
        with self.session.begin():
            position, area = self._get_or_404(ctx, position_id)
            # Hay que poder gestionar el puesto donde está hoy.
            self._require(ctx, area_id=position.area_id)

            before: dict = {}
            after: dict = {}

            if data.area_id is not None and data.area_id != position.area_id:
                # Mover exige alcance company: sin area_id, can() solo acepta ese alcance.
                self._require(ctx)
                area = self._get_area_or_404(ctx, data.area_id)
                before["area_id"], after["area_id"] = position.area_id, area.id
                position.area_id = area.id

            if data.name is not None and data.name != position.name:
                before["name"], after["name"] = position.name, data.name
                position.name = data.name

            if after:  # Sin cambios reales: no se escribe ni se genera historial.
                touch(position, actor, now)
                self.repository.add_history(
                    history_event(
                        "position.updated", position.id, ctx.company.id, actor, now,
                        before=before,
                        after=after,
                    )
                )
        return to_out(position, area)

    def delete(self, ctx: CompanyContext, position_id: str) -> None:
        now = utcnow()
        actor = ctx.user.id
        with self.session.begin():
            position, _ = self._get_or_404(ctx, position_id)
            self._require(ctx, area_id=position.area_id)
            if self.repository.count_assignments(position.id) > 0:
                raise PositionInUseError()
            before = {"is_active": position.is_active, "deleted_at": None}
            soft_delete(position, actor, now)
            self.repository.add_history(
                history_event(
                    "position.deleted", position.id, ctx.company.id, actor, now,
                    before=before,
                    after={"is_active": False, "deleted_at": now.isoformat()},
                )
            )

    def restore(self, ctx: CompanyContext, position_id: str) -> PositionOut:
        """Deshace una baja o suspensión. Vuelve con sus roles (los vínculos no se
        dieron de baja) pero sin personas: la baja exigía que no tuviera ninguna."""
        now = utcnow()
        actor = ctx.user.id
        with self.session.begin():
            row = self.repository.get_any(ctx.company.id, position_id)
            if row is None:
                raise PositionNotFoundError()
            position, area = row
            self._require(ctx, area_id=position.area_id)
            if area.deleted_at is not None:
                raise PositionAreaDeletedError()
            if not (position.is_active and position.deleted_at is None):
                before = {"is_active": position.is_active, "deleted_at": _iso(position.deleted_at)}
                restore(position, actor, now)
                self.repository.add_history(
                    history_event(
                        "position.restored", position.id, ctx.company.id, actor, now,
                        before=before,
                        after={"is_active": True, "deleted_at": None},
                    )
                )
        return to_out(position, area)

    def _get_or_404(self, ctx: CompanyContext, position_id: str) -> tuple[Position, Area]:
        row = self.repository.get(ctx.company.id, position_id)
        if row is None:
            raise PositionNotFoundError()
        return row

    def _get_area_or_404(self, ctx: CompanyContext, area_id: str) -> Area:
        # AreaRepository.get filtra por empresa: un área de otra empresa da None.
        area = self.areas.get(ctx.company.id, area_id)
        if area is None:
            raise AreaNotFoundError()
        return area

    @staticmethod
    def _require(ctx: CompanyContext, area_id: str | None = None) -> None:
        if not ctx.can(PERMISSION, area_id=area_id):
            raise PermissionDeniedError()


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None
