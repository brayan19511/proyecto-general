from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.dependencies import ViewScope, require_view_scope
from app.core.db.connection import get_db
from app.schemas.ledger import LedgerLinesPage, LedgerSummaryRowOut
from app.services.ledger_query_service import LedgerFilters, LedgerQueryService, iter_csv, parse_account_list

# Líneas sincronizadas de la empresa (Bearer + X-Company-Id, o X-API-Key).
# Solo GET y parámetros en la URL: se pueden usar desde Excel / Power BI
# ("Obtener datos → Desde la web", header X-API-Key). Exige ledger.view (o
# superior). Con ledger.view de alcance area, solo las líneas de sus áreas
# (homologación de centros de costo).
router = APIRouter(prefix="/ledger", tags=["ledger"])


def filters(
    date_from: date = Query(examples=["2026-01-01"]),
    date_to: date = Query(examples=["2026-09-30"]),
    accounts: str | None = Query(default=None, description='Separadas por coma: "95*,701110002" (* = prefijo)'),
    codigo: str | None = Query(default=None, description="Categoría, por nombre"),
    subcodigo: str | None = Query(default=None, description="Subcategoría, por nombre"),
    cost_center_code: str | None = Query(default=None),
    unclassified: bool | None = Query(default=None, description="true = solo sin regla; false = solo clasificadas"),
    no_subcodigo: bool = Query(
        default=False, description="true = solo clasificadas en una categoría principal (sin subcategoría)"
    ),
    supplier: str | None = Query(default=None, max_length=255, description="Proveedor exacto, tal como viene de SAP"),
    no_supplier: bool = Query(default=False, description="true = solo líneas sin proveedor (vacío en SAP)"),
) -> LedgerFilters:
    return LedgerFilters(
        date_from=date_from, date_to=date_to, accounts=parse_account_list(accounts), codigo=codigo,
        subcodigo=subcodigo, cost_center_code=cost_center_code, unclassified=unclassified,
        no_subcodigo=no_subcodigo, supplier=supplier, no_supplier=no_supplier,
    )


@router.get("/lines", response_model=LedgerLinesPage, operation_id="listLedgerLines")
def list_lines(
    f: LedgerFilters = Depends(filters),
    limit: int = Query(default=1000, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
    scope: ViewScope = Depends(require_view_scope),
    db: Session = Depends(get_db),
):
    """Líneas clasificadas en orden contable, paginadas. Siguiente página: offset=next_offset."""
    return LedgerQueryService(db).lines(scope.ctx.company_id, f, area_ids=scope.area_ids, limit=limit, offset=offset)


@router.get("/lines.csv", operation_id="exportLedgerLinesCsv", response_class=StreamingResponse)
def export_lines_csv(
    f: LedgerFilters = Depends(filters),
    sep: Literal[",", ";"] = Query(default=",", description="Separador; ';' para Excel en español"),
    scope: ViewScope = Depends(require_view_scope),
    db: Session = Depends(get_db),
):
    """Todas las líneas del filtro en CSV, en streaming (sin paginar), para Excel o Power BI."""
    LedgerQueryService(db).validate(scope.ctx.company_id, f, area_ids=scope.area_ids)  # 422 antes de enviar.
    filename = f"libro_mayor_{f.date_from}_{f.date_to}.csv"
    return StreamingResponse(
        iter_csv(scope.ctx.company_id, f, sep, scope.area_ids),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/summary",
    response_model=list[LedgerSummaryRowOut],
    response_model_exclude_unset=True,  # sin by_supplier no aparece "supplier" (contrato anterior)
    operation_id="getLedgerSummary",
)
def get_summary(
    f: LedgerFilters = Depends(filters),
    by_supplier: bool = Query(default=False, description="true = agrupar también por proveedor (campo supplier)"),
    scope: ViewScope = Depends(require_view_scope),
    db: Session = Depends(get_db),
):
    """Por año, mes, codigo y subcodigo (y proveedor con by_supplier): cantidad e importes con signo."""
    return LedgerQueryService(db).summary(scope.ctx.company_id, f, area_ids=scope.area_ids, by_supplier=by_supplier)
