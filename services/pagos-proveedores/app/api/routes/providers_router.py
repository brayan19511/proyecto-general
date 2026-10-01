from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import CompanyContext, require_permission
from app.core.db.connection import get_db
from app.core.permissions import CAN_MANAGE_PROVIDERS, CAN_VIEW
from app.schemas.page import Page, PageOut
from app.schemas.providers import ProviderCreate, ProviderOut, ProviderUpdate
from app.services.errors import InvalidDataError
from app.services.provider_service import ProviderService, to_out

# Maestro de proveedores de la empresa activa (X-Company-Id).
# Ver: payments.view (o superior). Crear, editar, dar de baja y restaurar:
# payments.providers.manage o payments.admin.
router = APIRouter(prefix="/providers", tags=["providers"])
can_view = require_permission(*CAN_VIEW)
can_manage = require_permission(*CAN_MANAGE_PROVIDERS)


@router.get("", response_model=PageOut[ProviderOut], operation_id="listProviders")
def list_providers(
    search: str | None = None,
    include_inactive: bool = False,
    page: Page = Depends(),
    ctx: CompanyContext = Depends(can_view),
    db: Session = Depends(get_db),
):
    """Por razón social. search busca en RUC/DNI y razón social. Por defecto solo activos."""
    providers, total = ProviderService(db).list(
        ctx.company_id, search=search, include_inactive=include_inactive, limit=page.limit, offset=page.offset
    )
    return PageOut[ProviderOut](items=[to_out(p) for p in providers], total=total)


@router.post("", response_model=ProviderOut, status_code=status.HTTP_201_CREATED, operation_id="createProvider")
def create_provider(body: ProviderCreate, ctx: CompanyContext = Depends(can_manage), db: Session = Depends(get_db)):
    """409 si el RUC/DNI o un nombre ya lo usa otro proveedor activo."""
    provider = ProviderService(db).create(company_id=ctx.company_id, user_id=ctx.user_id, data=body.model_dump())
    return to_out(provider)


@router.get("/{provider_id}", response_model=ProviderOut, operation_id="getProvider")
def get_provider(provider_id: str, ctx: CompanyContext = Depends(can_view), db: Session = Depends(get_db)):
    """Un proveedor de la empresa, activo o dado de baja."""
    return to_out(ProviderService(db).get(ctx.company_id, provider_id))


@router.patch("/{provider_id}", response_model=ProviderOut, operation_id="updateProvider")
def update_provider(
    provider_id: str, body: ProviderUpdate, ctx: CompanyContext = Depends(can_manage), db: Session = Depends(get_db)
):
    """Solo cambian los campos enviados. Las listas se reemplazan completas."""
    changes = body.model_dump(exclude_unset=True)
    nulls = [name for name, value in changes.items() if value is None]
    if nulls:
        raise InvalidDataError(f"No pueden ser null: {', '.join(nulls)}.")
    provider = ProviderService(db).update(
        company_id=ctx.company_id, user_id=ctx.user_id, provider_id=provider_id, changes=changes
    )
    return to_out(provider)


@router.delete(
    "/{provider_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response, operation_id="deleteProvider"
)
def delete_provider(provider_id: str, ctx: CompanyContext = Depends(can_manage), db: Session = Depends(get_db)):
    """Baja lógica: deja de identificarse en lotes nuevos; la fila y su historial se conservan."""
    ProviderService(db).deactivate(company_id=ctx.company_id, user_id=ctx.user_id, provider_id=provider_id)


@router.post("/{provider_id}/restore", response_model=ProviderOut, operation_id="restoreProvider")
def restore_provider(provider_id: str, ctx: CompanyContext = Depends(can_manage), db: Session = Depends(get_db)):
    """409 si otro proveedor activo ya usa su RUC/DNI o uno de sus nombres."""
    provider = ProviderService(db).restore(company_id=ctx.company_id, user_id=ctx.user_id, provider_id=provider_id)
    return to_out(provider)
