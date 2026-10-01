from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.dependencies import CompanyContext, require_platform_admin_in_company
from app.core.db.connection import get_db
from app.services.seed_service import SeedService

# Carga inicial de la empresa de X-Company-Id (app/seeds/data.py). Solo existe
# con SEED_ENABLED=true (main.py) y solo la ejecuta el administrador de
# plataforma con su sesión (como libro-mayor; sin token de bootstrap).
router = APIRouter(prefix="/admin/seed", tags=["admin"])


class SeedTemplatesResult(BaseModel):
    created: list[str]
    existing: list[str]  # Ya existían activas: no se modifican.
    kept_deactivated: list[str]  # Dadas de baja: el seed no las reactiva.


class SeedResult(BaseModel):
    templates: SeedTemplatesResult


@router.post("", response_model=SeedResult, operation_id="runSeed")
def run_seed(ctx: CompanyContext = Depends(require_platform_admin_in_company), db: Session = Depends(get_db)):
    """Idempotente: repetirla no duplica, no modifica ni reactiva nada."""
    return SeedService(db).run(company_id=ctx.company_id, company_code=ctx.company_code, user_id=ctx.user_id)
