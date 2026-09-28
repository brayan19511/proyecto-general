from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_company_context, require_permission
from app.core.db.connection import get_db
from app.schemas.page import Page
from app.schemas.position import (
    PositionCreate,
    PositionOut,
    PositionRoleCreate,
    PositionRoleOut,
    PositionUpdate,
)
from app.services.access_service import CompanyContext, LastAdminError, PermissionDeniedError
from app.services.area_service import AreaNotFoundError
from app.services.position_role_service import (
    PositionRoleService,
    RoleAlreadyLinkedError,
    RoleNotLinkedError,
)
from app.services.role_service import RoleNotFoundError
from app.services.position_service import (
    PERMISSION,
    PositionAreaDeletedError,
    PositionCodeExistsError,
    PositionInUseError,
    PositionNotFoundError,
    PositionService,
)

# Todas las rutas exigen X-Company-Id: operan solo sobre la empresa activa.
router = APIRouter(prefix="/positions", tags=["positions"])

ERRORS = {
    PositionNotFoundError: (status.HTTP_404_NOT_FOUND, "Puesto no encontrado."),
    AreaNotFoundError: (status.HTTP_404_NOT_FOUND, "Área no encontrada."),
    RoleNotFoundError: (status.HTTP_404_NOT_FOUND, "Rol no encontrado."),
    RoleNotLinkedError: (status.HTTP_404_NOT_FOUND, "El puesto no tiene ese rol."),
    RoleAlreadyLinkedError: (status.HTTP_409_CONFLICT, "El puesto ya tiene ese rol."),
    PositionCodeExistsError: (status.HTTP_409_CONFLICT, "Ya existe un puesto con ese código en la empresa."),
    PositionAreaDeletedError: (status.HTTP_409_CONFLICT, "El área del puesto está dada de baja; restáurala primero."),
    PositionInUseError: (status.HTTP_409_CONFLICT, "El puesto tiene personas asignadas; retíralas primero."),
    PermissionDeniedError: (status.HTTP_403_FORBIDDEN, "No tienes permiso para esta operación."),
    LastAdminError: (status.HTTP_409_CONFLICT, "La empresa quedaría sin administradores; asigna otro antes."),
}
HANDLED = tuple(ERRORS)


def _http_error(exc: Exception) -> HTTPException:
    status_code, detail = ERRORS[type(exc)]
    return HTTPException(status_code=status_code, detail=detail)


@router.get("", response_model=list[PositionOut], operation_id="listPositions")
def list_positions(
    page: Page = Depends(),
    include_deleted: bool = Query(default=False, description="Incluye los dados de baja (para restaurarlos)."),
    ctx: CompanyContext = Depends(get_company_context),
    db: Session = Depends(get_db),
):
    return PositionService(db).list_all(ctx, page.limit, page.offset, include_deleted)


@router.get("/{position_id}", response_model=PositionOut, operation_id="getPosition")
def get_position(
    position_id: str,
    ctx: CompanyContext = Depends(get_company_context),
    db: Session = Depends(get_db),
):
    try:
        return PositionService(db).get(ctx, position_id)
    except HANDLED as exc:
        raise _http_error(exc) from exc


@router.post(
    "",
    response_model=PositionOut,
    status_code=status.HTTP_201_CREATED,
    operation_id="createPosition",
)
def create_position(
    data: PositionCreate,
    ctx: CompanyContext = Depends(require_permission(PERMISSION)),
    db: Session = Depends(get_db),
):
    try:
        return PositionService(db).create(ctx, data)
    except HANDLED as exc:
        raise _http_error(exc) from exc


@router.patch("/{position_id}", response_model=PositionOut, operation_id="updatePosition")
def update_position(
    position_id: str,
    data: PositionUpdate,
    ctx: CompanyContext = Depends(require_permission(PERMISSION)),
    db: Session = Depends(get_db),
):
    try:
        return PositionService(db).update(ctx, position_id, data)
    except HANDLED as exc:
        raise _http_error(exc) from exc


@router.delete(
    "/{position_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    operation_id="deletePosition",
)
def delete_position(
    position_id: str,
    ctx: CompanyContext = Depends(require_permission(PERMISSION)),
    db: Session = Depends(get_db),
):
    # Baja lógica: is_active=false, deleted_at y deleted_by. La fila se conserva.
    try:
        PositionService(db).delete(ctx, position_id)
    except HANDLED as exc:
        raise _http_error(exc) from exc


@router.post("/{position_id}/restore", response_model=PositionOut, operation_id="restorePosition")
def restore_position(
    position_id: str,
    ctx: CompanyContext = Depends(require_permission(PERMISSION)),
    db: Session = Depends(get_db),
):
    """Reactiva un puesto dado de baja o suspendido (positions.manage en su área)."""
    try:
        return PositionService(db).restore(ctx, position_id)
    except HANDLED as exc:
        raise _http_error(exc) from exc


# --- Roles del puesto (puesto-rol)


@router.get(
    "/{position_id}/roles",
    response_model=list[PositionRoleOut],
    operation_id="listPositionRoles",
)
def list_position_roles(
    position_id: str,
    ctx: CompanyContext = Depends(get_company_context),
    db: Session = Depends(get_db),
):
    try:
        return PositionRoleService(db).list_roles(ctx, position_id)
    except HANDLED as exc:
        raise _http_error(exc) from exc


@router.post(
    "/{position_id}/roles",
    response_model=list[PositionRoleOut],
    status_code=status.HTTP_201_CREATED,
    operation_id="addPositionRole",
)
def add_position_role(
    position_id: str,
    data: PositionRoleCreate,
    ctx: CompanyContext = Depends(require_permission(PERMISSION)),
    db: Session = Depends(get_db),
):
    # positions.manage en el área del puesto + delegación de los permisos del rol.
    try:
        return PositionRoleService(db).add_role(ctx, position_id, data.role_id)
    except HANDLED as exc:
        raise _http_error(exc) from exc


@router.delete(
    "/{position_id}/roles/{role_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    operation_id="removePositionRole",
)
def remove_position_role(
    position_id: str,
    role_id: str,
    ctx: CompanyContext = Depends(require_permission(PERMISSION)),
    db: Session = Depends(get_db),
):
    try:
        PositionRoleService(db).remove_role(ctx, position_id, role_id)
    except HANDLED as exc:
        raise _http_error(exc) from exc
