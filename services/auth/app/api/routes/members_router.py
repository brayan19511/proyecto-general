from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import require_permission
from app.core.db.connection import get_db
from app.schemas.page import Page
from app.schemas.member import AssignmentCreate, MemberCreate, MemberOut, MemberStatusUpdate
from app.services.access_service import CompanyContext, LastAdminError, PermissionDeniedError
from app.services.member_service import (
    MANAGE,
    READ,
    AssignmentExistsError,
    AssignmentNotFoundError,
    MemberExistsError,
    MemberNotFoundError,
    MemberService,
    UserNotFoundError,
)
from app.services.position_service import PositionNotFoundError

# Todas las rutas exigen X-Company-Id: operan solo sobre la empresa activa.
router = APIRouter(prefix="/members", tags=["members"])

ERRORS = {
    MemberNotFoundError: (status.HTTP_404_NOT_FOUND, "Miembro no encontrado."),
    UserNotFoundError: (status.HTTP_404_NOT_FOUND, "No hay un usuario registrado y habilitado con ese email."),
    PositionNotFoundError: (status.HTTP_404_NOT_FOUND, "Puesto no encontrado."),
    AssignmentNotFoundError: (status.HTTP_404_NOT_FOUND, "El miembro no tiene ese puesto."),
    MemberExistsError: (status.HTTP_409_CONFLICT, "El usuario ya es miembro de la empresa."),
    AssignmentExistsError: (status.HTTP_409_CONFLICT, "El miembro ya tiene ese puesto."),
    PermissionDeniedError: (status.HTTP_403_FORBIDDEN, "No tienes permiso para esta operación."),
    LastAdminError: (status.HTTP_409_CONFLICT, "La empresa quedaría sin administradores; asigna otro antes."),
}
HANDLED = tuple(ERRORS)


def _http_error(exc: Exception) -> HTTPException:
    status_code, detail = ERRORS[type(exc)]
    return HTTPException(status_code=status_code, detail=detail)


@router.get("", response_model=list[MemberOut], operation_id="listMembers")
def list_members(
    page: Page = Depends(),
    ctx: CompanyContext = Depends(require_permission(READ)),
    db: Session = Depends(get_db),
):
    # Con alcance area solo aparecen los miembros de sus áreas y los que no tienen puesto.
    return MemberService(db).list_all(ctx, page.limit, page.offset)


@router.get("/{membership_id}", response_model=MemberOut, operation_id="getMember")
def get_member(
    membership_id: str,
    ctx: CompanyContext = Depends(require_permission(READ)),
    db: Session = Depends(get_db),
):
    try:
        return MemberService(db).get(ctx, membership_id)
    except HANDLED as exc:
        raise _http_error(exc) from exc


@router.post("", response_model=MemberOut, status_code=status.HTTP_201_CREATED, operation_id="addMember")
def add_member(
    data: MemberCreate,
    ctx: CompanyContext = Depends(require_permission(MANAGE)),
    db: Session = Depends(get_db),
):
    try:
        return MemberService(db).add(ctx, str(data.email))
    except HANDLED as exc:
        raise _http_error(exc) from exc


@router.patch("/{membership_id}", response_model=MemberOut, operation_id="setMemberStatus")
def set_member_status(
    membership_id: str,
    data: MemberStatusUpdate,
    ctx: CompanyContext = Depends(require_permission(MANAGE)),
    db: Session = Depends(get_db),
):
    # Suspender o reactivar: conserva sus puestos.
    try:
        return MemberService(db).set_status(ctx, membership_id, data.is_active)
    except HANDLED as exc:
        raise _http_error(exc) from exc


@router.delete(
    "/{membership_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    operation_id="removeMember",
)
def remove_member(
    membership_id: str,
    ctx: CompanyContext = Depends(require_permission(MANAGE)),
    db: Session = Depends(get_db),
):
    # Retira la membresía y todos sus puestos, cada uno con su historial.
    try:
        MemberService(db).remove(ctx, membership_id)
    except HANDLED as exc:
        raise _http_error(exc) from exc


@router.post(
    "/{membership_id}/positions",
    response_model=MemberOut,
    status_code=status.HTTP_201_CREATED,
    operation_id="assignPosition",
)
def assign_position(
    membership_id: str,
    data: AssignmentCreate,
    ctx: CompanyContext = Depends(require_permission(MANAGE)),
    db: Session = Depends(get_db),
):
    # memberships.manage en el área del puesto + delegación de sus permisos.
    try:
        return MemberService(db).assign(ctx, membership_id, data.position_id)
    except HANDLED as exc:
        raise _http_error(exc) from exc


@router.delete(
    "/{membership_id}/positions/{position_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    operation_id="unassignPosition",
)
def unassign_position(
    membership_id: str,
    position_id: str,
    ctx: CompanyContext = Depends(require_permission(MANAGE)),
    db: Session = Depends(get_db),
):
    try:
        MemberService(db).unassign(ctx, membership_id, position_id)
    except HANDLED as exc:
        raise _http_error(exc) from exc
