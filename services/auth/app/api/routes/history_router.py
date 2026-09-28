from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies import require_permission
from app.core.db.connection import get_db
from app.schemas.admin import HistoryEventOut
from app.schemas.page import Page
from app.services.access_service import CompanyContext
from app.services.admin_service import AdminService

# Historial de la empresa activa (X-Company-Id) para quien tenga history.read
# (solo alcance company: p. ej. el rol ADMIN_EMPRESA). El master usa /admin/history.
router = APIRouter(prefix="/history", tags=["history"])


@router.get("", response_model=list[HistoryEventOut], operation_id="listCompanyHistory")
def list_company_history(
    resource_id: str | None = Query(default=None, description="Historial de un recurso concreto."),
    actor_id: str | None = Query(default=None, description="Cambios hechos por un usuario."),
    action: str | None = Query(default=None, max_length=100, description='Prefijo, p. ej. "membership."'),
    page: Page = Depends(),
    ctx: CompanyContext = Depends(require_permission("history.read")),
    db: Session = Depends(get_db),
):
    # La empresa sale del contexto validado: nunca ve eventos de otra empresa
    # ni los globales (usuarios, perfiles, sesiones), que no tienen company_id.
    return AdminService(db).list_history(
        ctx.company.id, resource_id, actor_id, action, page.limit, page.offset
    )
