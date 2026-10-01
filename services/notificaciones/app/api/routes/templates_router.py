from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import Access, require_company_permission
from app.core.db.connection import get_db
from app.core.permissions import CAN_ADMIN
from app.schemas.page import Page, PageOut
from app.schemas.templates import (
    TEMPLATE_NOT_NULL_FIELDS,
    PreviewIn,
    PreviewOut,
    TemplateCreate,
    TemplateOut,
    TemplateUpdate,
)
from app.services.errors import InvalidDataError
from app.services.template_service import TemplateService, to_out

# Plantillas de la empresa activa (X-Company-Id). Todas las rutas exigen
# notifications.admin con alcance company.
router = APIRouter(prefix="/templates", tags=["templates"])
can_admin = require_company_permission(*CAN_ADMIN)


@router.get("", response_model=PageOut[TemplateOut], operation_id="listTemplates")
def list_templates(
    include_inactive: bool = False,
    page: Page = Depends(),
    access: Access = Depends(can_admin),
    db: Session = Depends(get_db),
):
    """Por código. Por defecto solo las activas."""
    templates, total = TemplateService(db).list(
        access.ctx.company_id, include_inactive=include_inactive, limit=page.limit, offset=page.offset
    )
    return PageOut[TemplateOut](items=[to_out(t) for t in templates], total=total)


@router.post("", response_model=TemplateOut, status_code=status.HTTP_201_CREATED, operation_id="createTemplate")
def create_template(body: TemplateCreate, access: Access = Depends(can_admin), db: Session = Depends(get_db)):
    """422 template_error si una plantilla no se puede interpretar; 409 si el código ya lo usa otra activa."""
    template = TemplateService(db).create(
        company_id=access.ctx.company_id, user_id=access.ctx.user_id, data=body.model_dump()
    )
    return to_out(template)


@router.get("/{template_id}", response_model=TemplateOut, operation_id="getTemplate")
def get_template(template_id: str, access: Access = Depends(can_admin), db: Session = Depends(get_db)):
    return to_out(TemplateService(db).get(access.ctx.company_id, template_id))


@router.patch("/{template_id}", response_model=TemplateOut, operation_id="updateTemplate")
def update_template(
    template_id: str, body: TemplateUpdate, access: Access = Depends(can_admin), db: Session = Depends(get_db)
):
    """Solo cambian los campos enviados. Cambiar la plantilla no afecta lo ya enviado."""
    changes = body.model_dump(exclude_unset=True)
    nulls = [name for name in TEMPLATE_NOT_NULL_FIELDS if name in changes and changes[name] is None]
    if nulls:
        raise InvalidDataError(f"No pueden ser null: {', '.join(nulls)}.")
    template = TemplateService(db).update(
        company_id=access.ctx.company_id, user_id=access.ctx.user_id, template_id=template_id, changes=changes
    )
    return to_out(template)


@router.delete(
    "/{template_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response, operation_id="deleteTemplate"
)
def delete_template(template_id: str, access: Access = Depends(can_admin), db: Session = Depends(get_db)):
    """Baja lógica: no se puede usar en envíos nuevos; lo ya enviado y su historial se conservan."""
    TemplateService(db).deactivate(company_id=access.ctx.company_id, user_id=access.ctx.user_id, template_id=template_id)


@router.post("/{template_id}/restore", response_model=TemplateOut, operation_id="restoreTemplate")
def restore_template(template_id: str, access: Access = Depends(can_admin), db: Session = Depends(get_db)):
    """409 si otra plantilla activa ya usa su código."""
    template = TemplateService(db).restore(
        company_id=access.ctx.company_id, user_id=access.ctx.user_id, template_id=template_id
    )
    return to_out(template)


@router.post("/{template_id}/preview", response_model=PreviewOut, operation_id="previewTemplate")
def preview_template(
    template_id: str, body: PreviewIn, access: Access = Depends(can_admin), db: Session = Depends(get_db)
):
    """Arma asunto y cuerpo con parámetros de ejemplo, sin guardar ni enviar.
    422 template_parameter_missing si falta un parámetro que la plantilla usa."""
    return TemplateService(db).preview(access.ctx.company_id, template_id, body.parameters)
