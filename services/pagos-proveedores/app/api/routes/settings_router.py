from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import CompanyContext, require_permission
from app.core.db.connection import get_db
from app.core.permissions import ADMIN, CAN_VIEW
from app.schemas.settings import SettingsOut, SettingsUpdate
from app.services.settings_service import SettingsService

# Configuración de la empresa activa. Ver: payments.view (o superior), para
# saber qué plantilla se usará. Cambiar: solo payments.admin.
router = APIRouter(prefix="/settings", tags=["settings"])
can_view = require_permission(*CAN_VIEW)
can_admin = require_permission(ADMIN)


@router.get("", response_model=SettingsOut, operation_id="getSettings")
def get_settings(ctx: CompanyContext = Depends(can_view), db: Session = Depends(get_db)):
    """Plantilla por defecto de los lotes: la elegida por la empresa o la del servicio."""
    return SettingsService(db).get(ctx.company_id)


@router.patch("", response_model=SettingsOut, operation_id="updateSettings")
def update_settings(body: SettingsUpdate, ctx: CompanyContext = Depends(can_admin), db: Session = Depends(get_db)):
    """Elige la plantilla por defecto (null = la del servicio). Queda en el historial."""
    return SettingsService(db).update(ctx.company_id, ctx.user_id, body.default_template_code)
