"""CRUD de áreas de la empresa activa.

Autorización (decisión del usuario):
  - Ver áreas: cualquier miembro de la empresa (o el master admin).
  - Crear, renombrar y dar de baja: areas.manage con alcance company.
    Los admins de área gestionan lo que hay dentro de su área, no el área.
"""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.common.mixin_model import utcnow
from app.models.entities import Area
from app.repositories.area_repository import AreaRepository
from app.schemas.area import AreaCreate, AreaUpdate
from app.services.access_service import CompanyContext, PermissionDeniedError
from app.services.common import audit_create, history_event, restore, soft_delete, touch

PERMISSION = "areas.manage"


class AreaNotFoundError(Exception):
    """No existe, está dada de baja o es de otra empresa."""


class AreaCodeExistsError(Exception):
    """El código ya está usado en la empresa, incluso por un área dada de baja."""


class AreaInUseError(Exception):
    """El área tiene puestos: darla de baja les quitaría el acceso sin avisar."""


class AreaService:
    def __init__(self, session: Session):
        self.session = session
        self.repository = AreaRepository(session)

    def list_all(
        self, ctx: CompanyContext, limit: int, offset: int, include_deleted: bool = False
    ) -> list[Area]:
        with self.session.begin():
            return self.repository.list_by_company(ctx.company.id, limit, offset, include_deleted)

    def get(self, ctx: CompanyContext, area_id: str) -> Area:
        with self.session.begin():
            return self._get_or_404(ctx, area_id)

    def create(self, ctx: CompanyContext, data: AreaCreate) -> Area:
        self._require_company_scope(ctx)
        now = utcnow()
        actor = ctx.user.id
        try:
            with self.session.begin():
                if self.repository.get_by_code(ctx.company.id, data.code) is not None:
                    raise AreaCodeExistsError()
                area = self.repository.add(
                    Area(
                        company_id=ctx.company.id,
                        code=data.code,
                        name=data.name,
                        **audit_create(actor, now),
                    )
                )
                self.repository.add_history(
                    history_event(
                        "area.created", area.id, ctx.company.id, actor, now,
                        before={},
                        after={"code": area.code, "name": area.name, "is_active": True},
                    )
                )
        except IntegrityError as exc:
            # Carrera: otra solicitud creó el mismo código entre la consulta y el INSERT.
            raise AreaCodeExistsError() from exc
        return area

    def update(self, ctx: CompanyContext, area_id: str, data: AreaUpdate) -> Area:
        self._require_company_scope(ctx)
        now = utcnow()
        actor = ctx.user.id
        with self.session.begin():
            area = self._get_or_404(ctx, area_id)
            if area.name == data.name:
                return area  # Sin cambios: no se escribe ni se genera historial.
            before = {"name": area.name}
            area.name = data.name
            touch(area, actor, now)
            self.repository.add_history(
                history_event(
                    "area.updated", area.id, ctx.company.id, actor, now,
                    before=before,
                    after={"name": area.name},
                )
            )
        return area

    def delete(self, ctx: CompanyContext, area_id: str) -> None:
        self._require_company_scope(ctx)
        now = utcnow()
        actor = ctx.user.id
        with self.session.begin():
            area = self._get_or_404(ctx, area_id)
            if self.repository.count_positions(area.id) > 0:
                raise AreaInUseError()
            before = {"is_active": area.is_active, "deleted_at": None}
            soft_delete(area, actor, now)
            self.repository.add_history(
                history_event(
                    "area.deleted", area.id, ctx.company.id, actor, now,
                    before=before,
                    after={"is_active": False, "deleted_at": now.isoformat()},
                )
            )

    def restore(self, ctx: CompanyContext, area_id: str) -> Area:
        """Deshace una baja o suspensión con una acción explícita y su evento."""
        self._require_company_scope(ctx)
        now = utcnow()
        actor = ctx.user.id
        with self.session.begin():
            area = self.repository.get_any(ctx.company.id, area_id)
            if area is None:
                raise AreaNotFoundError()
            if area.is_active and area.deleted_at is None:
                return area  # Ya está activa: nada que restaurar.
            before = {"is_active": area.is_active, "deleted_at": _iso(area.deleted_at)}
            restore(area, actor, now)
            self.repository.add_history(
                history_event(
                    "area.restored", area.id, ctx.company.id, actor, now,
                    before=before,
                    after={"is_active": True, "deleted_at": None},
                )
            )
        return area

    def _get_or_404(self, ctx: CompanyContext, area_id: str) -> Area:
        area = self.repository.get(ctx.company.id, area_id)
        if area is None:
            raise AreaNotFoundError()
        return area

    @staticmethod
    def _require_company_scope(ctx: CompanyContext) -> None:
        # Sin area_id: solo alcanza el alcance company (o el master admin).
        if not ctx.can(PERMISSION):
            raise PermissionDeniedError()


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None
