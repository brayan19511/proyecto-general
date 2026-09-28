from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from platform_audit import queries
from sqlalchemy.orm import Session

from app.api.dependencies import require_platform_admin
from app.core.config import settings
from app.core.db.connection import get_db
from app.schemas.logs import LogDetailOut, LogFullOut, LogOut, LogStepOut
from app.schemas.page import Page

# Logs técnicos de auth (schema audit), solo para el master admin. Solo las
# filas de este servicio: la vista entre servicios irá por APIs internas.
router = APIRouter(
    prefix="/admin/logs",
    tags=["admin"],
    dependencies=[Depends(require_platform_admin)],
)


@router.get("", response_model=list[LogOut], operation_id="adminListLogs")
def list_logs(
    trace_id: str | None = Query(default=None),
    user_id: str | None = Query(default=None),
    outcome: Literal["success", "warning", "error"] | None = Query(default=None),
    path_prefix: str | None = Query(default=None, max_length=300, description='p. ej. "/auth/"'),
    page: Page = Depends(),
    db: Session = Depends(get_db),
):
    with db.begin():
        return queries.list_logs(
            db, settings.SERVICE_NAME,
            trace_id=trace_id, user_id=user_id, outcome=outcome, path_prefix=path_prefix,
            limit=page.limit, offset=page.offset,
        )


@router.get("/{log_id}", response_model=LogFullOut, operation_id="adminGetLog")
def get_log(log_id: str, db: Session = Depends(get_db)):
    """Cabecera con sus detalles (request, response, errores, mensajes) y pasos."""
    with db.begin():
        row = queries.get_log(db, settings.SERVICE_NAME, log_id)
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Log no encontrado.")
        log, details, steps = row
        return LogFullOut(
            **LogOut.model_validate(log).model_dump(),
            details=[LogDetailOut.model_validate(d) for d in details],
            steps=[LogStepOut.model_validate(s) for s in steps],
        )
