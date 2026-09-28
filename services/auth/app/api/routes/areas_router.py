from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_company_context, require_permission
from app.core.db.connection import get_db
from app.schemas.area import AreaCreate, AreaOut, AreaUpdate
from app.schemas.page import Page
from app.services.access_service import CompanyContext, PermissionDeniedError
from app.services.area_service import (
    PERMISSION,
    AreaCodeExistsError,
    AreaInUseError,
    AreaNotFoundError,
    AreaService,
)

# Todas las rutas exigen X-Company-Id: operan solo sobre la empresa activa.
router = APIRouter(prefix="/areas", tags=["areas"])

# Traducción de errores del service a HTTP, en un solo lugar.
ERRORS = {
    AreaNotFoundError: (status.HTTP_404_NOT_FOUND, "Área no encontrada."),
    AreaCodeExistsError: (status.HTTP_409_CONFLICT, "Ya existe un área con ese código en la empresa."),
    AreaInUseError: (status.HTTP_409_CONFLICT, "El área tiene puestos; dalos de baja o muévelos primero."),
    PermissionDeniedError: (status.HTTP_403_FORBIDDEN, "No tienes permiso para esta operación."),
}
HANDLED = tuple(ERRORS)


def _http_error(exc: Exception) -> HTTPException:
    status_code, detail = ERRORS[type(exc)]
    return HTTPException(status_code=status_code, detail=detail)


@router.get("", response_model=list[AreaOut], operation_id="listAreas")
def list_areas(
    page: Page = Depends(),
    include_deleted: bool = Query(default=False, description="Incluye las dadas de baja (para restaurarlas)."),
    ctx: CompanyContext = Depends(get_company_context),
    db: Session = Depends(get_db),
):
    return AreaService(db).list_all(ctx, page.limit, page.offset, include_deleted)


@router.get("/{area_id}", response_model=AreaOut, operation_id="getArea")
def get_area(
    area_id: str,
    ctx: CompanyContext = Depends(get_company_context),
    db: Session = Depends(get_db),
):
    try:
        return AreaService(db).get(ctx, area_id)
    except HANDLED as exc:
        raise _http_error(exc) from exc


@router.post(
    "",
    response_model=AreaOut,
    status_code=status.HTTP_201_CREATED,
    operation_id="createArea",
)
def create_area(
    data: AreaCreate,
    ctx: CompanyContext = Depends(require_permission(PERMISSION)),
    db: Session = Depends(get_db),
):
    try:
        return AreaService(db).create(ctx, data)
    except HANDLED as exc:
        raise _http_error(exc) from exc


@router.patch("/{area_id}", response_model=AreaOut, operation_id="updateArea")
def update_area(
    area_id: str,
    data: AreaUpdate,
    ctx: CompanyContext = Depends(require_permission(PERMISSION)),
    db: Session = Depends(get_db),
):
    try:
        return AreaService(db).update(ctx, area_id, data)
    except HANDLED as exc:
        raise _http_error(exc) from exc


@router.delete(
    "/{area_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    operation_id="deleteArea",
)
def delete_area(
    area_id: str,
    ctx: CompanyContext = Depends(require_permission(PERMISSION)),
    db: Session = Depends(get_db),
):
    # Baja lógica: is_active=false, deleted_at y deleted_by. La fila se conserva.
    try:
        AreaService(db).delete(ctx, area_id)
    except HANDLED as exc:
        raise _http_error(exc) from exc


@router.post("/{area_id}/restore", response_model=AreaOut, operation_id="restoreArea")
def restore_area(
    area_id: str,
    ctx: CompanyContext = Depends(require_permission(PERMISSION)),
    db: Session = Depends(get_db),
):
    """Reactiva un área dada de baja o suspendida (areas.manage, alcance company)."""
    try:
        return AreaService(db).restore(ctx, area_id)
    except HANDLED as exc:
        raise _http_error(exc) from exc
