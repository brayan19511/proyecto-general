from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import ViewScope, require_view_scope
from app.core.db.connection import get_db
from app.schemas.live_queries import LiveQueryRequest, LiveQueryResult
from app.services.live_query_service import LiveQueryService

# Consulta en vivo a SAP de la empresa activa (X-Company-Id): extrae, clasifica
# y responde en la misma solicitud; no guarda nada. Exige ledger.view (o
# superior) con alcance company (o administrador de plataforma).
router = APIRouter(prefix="/live-queries", tags=["live"])


@router.post("", response_model=LiveQueryResult, operation_id="runLiveQuery")
def run_live_query(body: LiveQueryRequest, scope: ViewScope = Depends(require_view_scope), db: Session = Depends(get_db)):
    """Consulta SAP por tramos (mes o día) en paralelo, clasifica y responde.

    view: lines (solo líneas, default), summary (solo resumen) o full (ambos).

    422: cuenta o rango inválidos, o más de LIVE_QUERY_MAX_LINES líneas (usar
    view=summary). 409: falta SAP o compañía SAP. 502: SAP falló. 504: superó
    LIVE_QUERY_TIMEOUT_SECONDS.
    """
    return LiveQueryService(db).run(
        company_id=scope.ctx.company_id, accounts=body.accounts, date_from=body.date_from, date_to=body.date_to,
        split=body.split, view=body.view, area_ids=scope.area_ids,
    )
