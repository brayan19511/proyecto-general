from typing import Literal

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.dependencies import CompanyContext, require_company_permission
from app.core.db.connection import get_db
from app.core.permissions import SYNC
from app.schemas.page import Page
from app.schemas.sync_runs import SyncRunCreate, SyncRunOut
from app.services.sync_service import SyncService

# Sincronizaciones de la empresa activa (X-Company-Id). Exige ledger.sync con
# alcance company (o administrador de plataforma). La solicitud solo registra
# la ejecución: la procesa el worker (python -m app.worker). El final de la
# respuesta HTTP no es el final del trabajo: consultar GET /sync-runs/{id}.
router = APIRouter(prefix="/sync-runs", tags=["sync"])
can_sync = require_company_permission(SYNC)


@router.post("", response_model=SyncRunOut, status_code=status.HTTP_202_ACCEPTED, operation_id="createSyncRun")
def create_sync_run(body: SyncRunCreate, ctx: CompanyContext = Depends(can_sync), db: Session = Depends(get_db)):
    """202 con la ejecución en estado pending. 409 si la cuenta ya tiene una abierta, si la
    empresa no tiene compañía SAP o si SAP no está configurado; 422 si el rango no es válido."""
    return SyncService(db).request(
        company_id=ctx.company_id, user_id=ctx.user_id,
        account_id=body.account_id, date_from=body.date_from, date_to=body.date_to,
    )


@router.get("", response_model=list[SyncRunOut], operation_id="listSyncRuns")
def list_sync_runs(
    account_id: str | None = None,
    status: Literal["pending", "running", "succeeded", "failed"] | None = None,
    page: Page = Depends(),
    ctx: CompanyContext = Depends(can_sync),
    db: Session = Depends(get_db),
):
    """Ejecuciones, más recientes primero."""
    return SyncService(db).list(ctx.company_id, account_id=account_id, status=status, limit=page.limit, offset=page.offset)


@router.get("/{run_id}", response_model=SyncRunOut, operation_id="getSyncRun")
def get_sync_run(run_id: str, ctx: CompanyContext = Depends(can_sync), db: Session = Depends(get_db)):
    """Estado y avance (days_done / days_total, filas leídas, nuevas y actualizadas)."""
    return SyncService(db).get(ctx.company_id, run_id)
