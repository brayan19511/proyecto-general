"""Configuración por empresa: plantilla por defecto de los lotes.

No se comprueba aquí que la plantilla exista en notificaciones (sería otra
llamada y otro servicio): si no existe, el envío la rechaza (422) y el lote
vuelve a borrador. El front ofrece solo las plantillas activas.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.common.mixin_model import utcnow
from app.models.entities import CompanySettings
from app.schemas.settings import SettingsOut
from app.services.actors import user_actor_id
from app.services.history import record_change


class SettingsService:
    def __init__(self, db: Session):
        self.db = db

    def _find(self, company_id: str) -> CompanySettings | None:
        return self.db.scalar(
            select(CompanySettings).where(CompanySettings.company_id == company_id, CompanySettings.is_active.is_(True))
        )

    def default_template(self, company_id: str) -> str:
        """Plantilla de la empresa o la del servicio. Llamar dentro de una transacción."""
        row = self._find(company_id)
        return (row.default_template_code if row else None) or settings.DEFAULT_TEMPLATE_CODE

    def get(self, company_id: str) -> SettingsOut:
        with self.db.begin():
            return _out(self._find(company_id))

    def update(self, company_id: str, user_id: str, default_template_code: str | None) -> SettingsOut:
        with self.db.begin():
            actor_id = user_actor_id(self.db, user_id)
            now = utcnow()
            row = self._find(company_id)
            before = {"default_template_code": row.default_template_code} if row else {}
            if row is None:
                row = CompanySettings(company_id=company_id, created_at=now, created_by=actor_id)
                self.db.add(row)
            row.default_template_code = default_template_code
            row.updated_at, row.updated_by = now, actor_id
            self.db.flush()
            record_change(
                self.db, action="settings.update", resource_type="company_settings", resource_id=row.id,
                company_id=company_id, actor_id=actor_id, now=now, before=before,
                after={"default_template_code": default_template_code},
            )
            return _out(row)


def _out(row: CompanySettings | None) -> SettingsOut:
    chosen = row.default_template_code if row else None
    return SettingsOut(
        default_template_code=chosen,
        effective_template_code=chosen or settings.DEFAULT_TEMPLATE_CODE,
        service_template_code=settings.DEFAULT_TEMPLATE_CODE,
    )
