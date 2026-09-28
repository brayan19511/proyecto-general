from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_company_context, require_permission
from app.core.db.connection import get_db
from app.schemas.page import Page
from app.schemas.role import RoleCreate, RoleOut, RolePermissionCreate, RoleUpdate
from app.services.access_service import CompanyContext, LastAdminError, PermissionDeniedError
from app.services.role_service import (
    PERMISSION,
    GrantExistsError,
    GrantNotFoundError,
    RoleCodeExistsError,
    RoleInUseError,
    RoleNotFoundError,
    RoleService,
    UnknownPermissionError,
)

# Todas las rutas exigen X-Company-Id: operan solo sobre la empresa activa.
router = APIRouter(prefix="/roles", tags=["roles"])

ERRORS = {
    RoleNotFoundError: (status.HTTP_404_NOT_FOUND, "Rol no encontrado."),
    GrantNotFoundError: (status.HTTP_404_NOT_FOUND, "El rol no tiene esa concesión."),
    RoleCodeExistsError: (status.HTTP_409_CONFLICT, "Ya existe un rol con ese código en la empresa."),
    RoleInUseError: (status.HTTP_409_CONFLICT, "El rol está asignado a puestos; retíralo de ellos primero."),
    GrantExistsError: (status.HTTP_409_CONFLICT, "El rol ya tiene ese permiso con ese alcance."),
    UnknownPermissionError: (status.HTTP_422_UNPROCESSABLE_CONTENT, "Permiso desconocido o alcance no admitido."),
    PermissionDeniedError: (status.HTTP_403_FORBIDDEN, "No tienes permiso para esta operación."),
    LastAdminError: (status.HTTP_409_CONFLICT, "La empresa quedaría sin administradores; asigna otro antes."),
}
HANDLED = tuple(ERRORS)


def _http_error(exc: Exception) -> HTTPException:
    status_code, detail = ERRORS[type(exc)]
    return HTTPException(status_code=status_code, detail=detail)


@router.get("", response_model=list[RoleOut], operation_id="listRoles")
def list_roles(
    page: Page = Depends(),
    include_deleted: bool = Query(default=False, description="Incluye los dados de baja (para restaurarlos)."),
    ctx: CompanyContext = Depends(get_company_context),
    db: Session = Depends(get_db),
):
    return RoleService(db).list_all(ctx, page.limit, page.offset, include_deleted)


@router.get("/{role_id}", response_model=RoleOut, operation_id="getRole")
def get_role(
    role_id: str,
    ctx: CompanyContext = Depends(get_company_context),
    db: Session = Depends(get_db),
):
    try:
        return RoleService(db).get(ctx, role_id)
    except HANDLED as exc:
        raise _http_error(exc) from exc


@router.post("", response_model=RoleOut, status_code=status.HTTP_201_CREATED, operation_id="createRole")
def create_role(
    data: RoleCreate,
    ctx: CompanyContext = Depends(require_permission(PERMISSION)),
    db: Session = Depends(get_db),
):
    try:
        return RoleService(db).create(ctx, data)
    except HANDLED as exc:
        raise _http_error(exc) from exc


@router.patch("/{role_id}", response_model=RoleOut, operation_id="updateRole")
def update_role(
    role_id: str,
    data: RoleUpdate,
    ctx: CompanyContext = Depends(require_permission(PERMISSION)),
    db: Session = Depends(get_db),
):
    try:
        return RoleService(db).update(ctx, role_id, data)
    except HANDLED as exc:
        raise _http_error(exc) from exc


@router.delete(
    "/{role_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    operation_id="deleteRole",
)
def delete_role(
    role_id: str,
    ctx: CompanyContext = Depends(require_permission(PERMISSION)),
    db: Session = Depends(get_db),
):
    try:
        RoleService(db).delete(ctx, role_id)
    except HANDLED as exc:
        raise _http_error(exc) from exc


@router.post("/{role_id}/restore", response_model=RoleOut, operation_id="restoreRole")
def restore_role(
    role_id: str,
    ctx: CompanyContext = Depends(require_permission(PERMISSION)),
    db: Session = Depends(get_db),
):
    """Reactiva un rol dado de baja o suspendido (roles.manage)."""
    try:
        return RoleService(db).restore(ctx, role_id)
    except HANDLED as exc:
        raise _http_error(exc) from exc


@router.post(
    "/{role_id}/permissions",
    response_model=RoleOut,
    status_code=status.HTTP_201_CREATED,
    operation_id="grantRolePermission",
)
def grant_permission(
    role_id: str,
    data: RolePermissionCreate,
    ctx: CompanyContext = Depends(require_permission(PERMISSION)),
    db: Session = Depends(get_db),
):
    # Regla de delegación: quien otorga debe tener ese permiso con alcance company.
    try:
        return RoleService(db).grant(ctx, role_id, data)
    except HANDLED as exc:
        raise _http_error(exc) from exc


@router.delete(
    "/{role_id}/permissions/{grant_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    operation_id="revokeRolePermission",
)
def revoke_permission(
    role_id: str,
    grant_id: str,
    ctx: CompanyContext = Depends(require_permission(PERMISSION)),
    db: Session = Depends(get_db),
):
    # Baja lógica de la concesión; tiene efecto inmediato en los permisos.
    # Quitar no exige delegación: reduce privilegios.
    try:
        RoleService(db).revoke(ctx, role_id, grant_id)
    except HANDLED as exc:
        raise _http_error(exc) from exc
