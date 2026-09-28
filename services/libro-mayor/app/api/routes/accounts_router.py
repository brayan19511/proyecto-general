from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import CompanyContext, require_company_permission
from app.core.db.connection import get_db
from app.core.permissions import ACCOUNTS_MANAGE
from app.schemas.accounts import AccountCreate, AccountOut, AccountUpdate, not_null_changes
from app.schemas.page import Page
from app.services.account_service import AccountService

# Cuentas SAP a sincronizar de la empresa activa (X-Company-Id).
# Exige ledger.accounts.manage con alcance company (o administrador de plataforma).
router = APIRouter(prefix="/accounts", tags=["accounts"])
can_manage = require_company_permission(ACCOUNTS_MANAGE)


@router.get("", response_model=list[AccountOut], operation_id="listAccounts")
def list_accounts(
    include_inactive: bool = False,
    page: Page = Depends(),
    ctx: CompanyContext = Depends(can_manage),
    db: Session = Depends(get_db),
):
    """Cuentas registradas, ordenadas por código. Por defecto solo las activas."""
    return AccountService(db).list(ctx.company_id, include_inactive=include_inactive, limit=page.limit, offset=page.offset)


@router.post("", response_model=AccountOut, status_code=status.HTTP_201_CREATED, operation_id="createAccount")
def create_account(body: AccountCreate, ctx: CompanyContext = Depends(can_manage), db: Session = Depends(get_db)):
    """409 si se superpone con otra cuenta activa o si la empresa no tiene compañía SAP."""
    return AccountService(db).create(
        company_id=ctx.company_id, user_id=ctx.user_id,
        code=body.code, match_mode=body.match_mode, name=body.name,
    )


@router.get("/{account_id}", response_model=AccountOut, operation_id="getAccount")
def get_account(account_id: str, ctx: CompanyContext = Depends(can_manage), db: Session = Depends(get_db)):
    """Una cuenta de la empresa, activa o dada de baja."""
    return AccountService(db).get(ctx.company_id, account_id)


@router.patch("/{account_id}", response_model=AccountOut, operation_id="updateAccount")
def update_account(
    account_id: str, body: AccountUpdate, ctx: CompanyContext = Depends(can_manage), db: Session = Depends(get_db)
):
    """Solo cambian los campos enviados. code/match_mode: 409 si la cuenta ya tiene líneas o una
    sincronización abierta (se da de baja y se registra otra); también 409 si se superpone."""
    return AccountService(db).update(
        company_id=ctx.company_id, user_id=ctx.user_id, account_id=account_id,
        changes=not_null_changes(body, "code", "match_mode"),
    )


@router.delete(
    "/{account_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response, operation_id="deleteAccount"
)
def delete_account(account_id: str, ctx: CompanyContext = Depends(can_manage), db: Session = Depends(get_db)):
    """Baja lógica: deja de sincronizarse; la fila, sus líneas y su historial se conservan."""
    AccountService(db).deactivate(company_id=ctx.company_id, user_id=ctx.user_id, account_id=account_id)
