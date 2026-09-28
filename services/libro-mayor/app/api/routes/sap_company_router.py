from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import CompanyContext, require_platform_admin_in_company
from app.core.db.connection import get_db
from app.schemas.accounts import SapCompanyCreate, SapCompanyOut, SapCompanyUpdate, not_null_changes
from app.services.sap_company_service import SapCompanyService

# Compañía SAP de la empresa activa (X-Company-Id). Solo el administrador de
# plataforma: decide de qué base SAP se leen los datos de una empresa.
router = APIRouter(prefix="/admin/sap-company", tags=["admin"])


@router.get("", response_model=SapCompanyOut, operation_id="getSapCompany")
def get_sap_company(ctx: CompanyContext = Depends(require_platform_admin_in_company), db: Session = Depends(get_db)):
    return SapCompanyService(db).get(ctx.company_id)


@router.post("", response_model=SapCompanyOut, status_code=status.HTTP_201_CREATED, operation_id="createSapCompany")
def create_sap_company(
    body: SapCompanyCreate,
    ctx: CompanyContext = Depends(require_platform_admin_in_company),
    db: Session = Depends(get_db),
):
    """Una por empresa: 409 si ya hay una activa (editarla con PATCH)."""
    return SapCompanyService(db).create(
        company_id=ctx.company_id, user_id=ctx.user_id,
        sap_schema=body.sap_schema, source_view=body.source_view, sync_start_date=body.sync_start_date,
    )


@router.patch("", response_model=SapCompanyOut, operation_id="updateSapCompany")
def update_sap_company(
    body: SapCompanyUpdate,
    ctx: CompanyContext = Depends(require_platform_admin_in_company),
    db: Session = Depends(get_db),
):
    """Solo cambian los campos enviados. sap_schema: 409 si la empresa ya tiene líneas sincronizadas."""
    return SapCompanyService(db).update(
        company_id=ctx.company_id, user_id=ctx.user_id,
        changes=not_null_changes(body, "sap_schema", "source_view", "sync_start_date"),
    )


@router.delete("", status_code=status.HTTP_204_NO_CONTENT, response_class=Response, operation_id="deleteSapCompany")
def delete_sap_company(ctx: CompanyContext = Depends(require_platform_admin_in_company), db: Session = Depends(get_db)):
    SapCompanyService(db).deactivate(company_id=ctx.company_id, user_id=ctx.user_id)
