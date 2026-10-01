from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import Access, require_company_permission
from app.core.db.connection import get_db
from app.core.permissions import CAN_ADMIN
from app.schemas.page import Page, PageOut
from app.schemas.smtp_accounts import (
    NOT_NULL_FIELDS,
    SmtpAccountCreate,
    SmtpAccountOut,
    SmtpAccountTestOut,
    SmtpAccountUpdate,
)
from app.services.errors import InvalidDataError
from app.services.smtp_account_service import SmtpAccountService, to_out

# Cuentas SMTP de la empresa activa (X-Company-Id). Todas las rutas exigen
# notifications.admin con alcance company.
router = APIRouter(prefix="/smtp-accounts", tags=["smtp-accounts"])
can_admin = require_company_permission(*CAN_ADMIN)


@router.get("", response_model=PageOut[SmtpAccountOut], operation_id="listSmtpAccounts")
def list_smtp_accounts(
    include_inactive: bool = False,
    page: Page = Depends(),
    access: Access = Depends(can_admin),
    db: Session = Depends(get_db),
):
    """En orden de uso: priority y, a igual prioridad, la más antigua. Por defecto solo activas."""
    accounts, total = SmtpAccountService(db).list(
        access.ctx.company_id, include_inactive=include_inactive, limit=page.limit, offset=page.offset
    )
    return PageOut[SmtpAccountOut](items=[to_out(a) for a in accounts], total=total)


@router.post("", response_model=SmtpAccountOut, status_code=status.HTTP_201_CREATED, operation_id="createSmtpAccount")
def create_smtp_account(body: SmtpAccountCreate, access: Access = Depends(can_admin), db: Session = Depends(get_db)):
    """422 si username y password no van juntos; 409 si el nombre ya lo usa otra cuenta activa."""
    account = SmtpAccountService(db).create(
        company_id=access.ctx.company_id, user_id=access.ctx.user_id, data=body.model_dump()
    )
    return to_out(account)


@router.get("/{account_id}", response_model=SmtpAccountOut, operation_id="getSmtpAccount")
def get_smtp_account(account_id: str, access: Access = Depends(can_admin), db: Session = Depends(get_db)):
    """Una cuenta de la empresa, activa o dada de baja."""
    return to_out(SmtpAccountService(db).get(access.ctx.company_id, account_id))


@router.patch("/{account_id}", response_model=SmtpAccountOut, operation_id="updateSmtpAccount")
def update_smtp_account(
    account_id: str, body: SmtpAccountUpdate, access: Access = Depends(can_admin), db: Session = Depends(get_db)
):
    """Solo cambian los campos enviados. password: texto la reemplaza, null la borra; si no se envía, no cambia."""
    changes = body.model_dump(exclude_unset=True)
    nulls = [name for name in NOT_NULL_FIELDS if name in changes and changes[name] is None]
    if nulls:
        raise InvalidDataError(f"No pueden ser null: {', '.join(nulls)}.")
    account = SmtpAccountService(db).update(
        company_id=access.ctx.company_id, user_id=access.ctx.user_id, account_id=account_id, changes=changes
    )
    return to_out(account)


@router.delete(
    "/{account_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response, operation_id="deleteSmtpAccount"
)
def delete_smtp_account(account_id: str, access: Access = Depends(can_admin), db: Session = Depends(get_db)):
    """Baja lógica: deja de usarse para enviar; la fila y su historial se conservan."""
    SmtpAccountService(db).deactivate(company_id=access.ctx.company_id, user_id=access.ctx.user_id, account_id=account_id)


@router.post("/{account_id}/restore", response_model=SmtpAccountOut, operation_id="restoreSmtpAccount")
def restore_smtp_account(account_id: str, access: Access = Depends(can_admin), db: Session = Depends(get_db)):
    """Reactiva una cuenta dada de baja. 409 si otra cuenta activa ya usa su nombre."""
    account = SmtpAccountService(db).restore(
        company_id=access.ctx.company_id, user_id=access.ctx.user_id, account_id=account_id
    )
    return to_out(account)


@router.post("/{account_id}/test", response_model=SmtpAccountTestOut, operation_id="testSmtpAccount")
def test_smtp_account(account_id: str, access: Access = Depends(can_admin), db: Session = Depends(get_db)):
    """Conecta, cifra y autentica con una cuenta activa SIN enviar correo.

    Responde 200 aunque la prueba falle: ok=false y la categoría del error, sin el
    texto del servidor. Puede tardar hasta timeout_seconds de la cuenta.
    """
    error_kind = SmtpAccountService(db).test(access.ctx.company_id, account_id)
    return SmtpAccountTestOut(ok=error_kind is None, error_kind=error_kind)
