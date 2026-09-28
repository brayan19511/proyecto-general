from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser, require_platform_admin
from app.core.db.connection import get_db
from app.schemas.admin import (
    AdminAreaOut,
    AdminCompanyOut,
    AdminPositionOut,
    AdminRoleOut,
    AdminUserDetailOut,
    AdminUserOut,
    CompanyCreate,
    CompanyUpdate,
    HistoryEventOut,
)
from app.schemas.me import RevokedSessionsOut
from app.schemas.page import Page
from app.schemas.user import PasswordReset
from app.services import password_service
from app.services.admin_service import (
    AdminService,
    CompanyCodeExistsError,
    CompanyNotFoundError,
    UserNotFoundError,
)

# Solo master admin. Sin X-Company-Id: trabajan sobre toda la plataforma.
router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_platform_admin)],
)

CompanyFilter = Query(default=None, description="Opcional: limita el listado a una empresa.")

ERRORS = {
    CompanyNotFoundError: (status.HTTP_404_NOT_FOUND, "Empresa no encontrada."),
    UserNotFoundError: (status.HTTP_404_NOT_FOUND, "Usuario no encontrado."),
    CompanyCodeExistsError: (status.HTTP_409_CONFLICT, "Ya existe una empresa con ese código."),
}
HANDLED = tuple(ERRORS)


def _http_error(exc: Exception) -> HTTPException:
    status_code, detail = ERRORS[type(exc)]
    return HTTPException(status_code=status_code, detail=detail)


# --- Vistas generales (solo lectura)


@router.get("/companies", response_model=list[AdminCompanyOut], operation_id="adminListCompanies")
def list_companies(page: Page = Depends(), db: Session = Depends(get_db)):
    return AdminService(db).list_companies(page.limit, page.offset)


@router.get("/areas", response_model=list[AdminAreaOut], operation_id="adminListAreas")
def list_areas(company_id: str | None = CompanyFilter, page: Page = Depends(), db: Session = Depends(get_db)):
    return AdminService(db).list_areas(company_id, page.limit, page.offset)


@router.get("/positions", response_model=list[AdminPositionOut], operation_id="adminListPositions")
def list_positions(company_id: str | None = CompanyFilter, page: Page = Depends(), db: Session = Depends(get_db)):
    return AdminService(db).list_positions(company_id, page.limit, page.offset)


@router.get("/roles", response_model=list[AdminRoleOut], operation_id="adminListRoles")
def list_roles(company_id: str | None = CompanyFilter, page: Page = Depends(), db: Session = Depends(get_db)):
    return AdminService(db).list_roles(company_id, page.limit, page.offset)


@router.get("/users", response_model=list[AdminUserOut], operation_id="adminListUsers")
def list_users(
    email: str | None = Query(default=None, max_length=254, description="Coincidencia parcial."),
    page: Page = Depends(),
    db: Session = Depends(get_db),
):
    return AdminService(db).list_users(email, page.limit, page.offset)


@router.get("/history", response_model=list[HistoryEventOut], operation_id="adminListHistory")
def list_history(
    company_id: str | None = CompanyFilter,
    resource_id: str | None = Query(default=None, description="Historial de un recurso concreto."),
    actor_id: str | None = Query(default=None, description="Cambios hechos por un usuario."),
    action: str | None = Query(default=None, max_length=100, description='Prefijo, p. ej. "membership."'),
    page: Page = Depends(),
    db: Session = Depends(get_db),
):
    """Historial de negocio (solo lectura; los eventos no se modifican)."""
    return AdminService(db).list_history(company_id, resource_id, actor_id, action, page.limit, page.offset)


@router.get("/users/{user_id}", response_model=AdminUserDetailOut, operation_id="adminGetUser")
def get_user(user_id: str, db: Session = Depends(get_db)):
    """Perfil completo de un usuario: cuenta, datos personales, documentos,
    empresas y sesiones activas. Solo master admin."""
    try:
        return AdminService(db).get_user_detail(user_id)
    except HANDLED as exc:
        raise _http_error(exc) from exc


# --- Empresas


@router.post(
    "/companies",
    response_model=AdminCompanyOut,
    status_code=status.HTTP_201_CREATED,
    operation_id="adminCreateCompany",
)
def create_company(
    data: CompanyCreate,
    current: CurrentUser = Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    try:
        return AdminService(db).create_company(current.user, data)
    except HANDLED as exc:
        raise _http_error(exc) from exc


@router.patch(
    "/companies/{company_id}",
    response_model=AdminCompanyOut,
    operation_id="adminUpdateCompany",
)
def update_company(
    company_id: str,
    data: CompanyUpdate,
    current: CurrentUser = Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    try:
        return AdminService(db).update_company(current.user, company_id, data)
    except HANDLED as exc:
        raise _http_error(exc) from exc


@router.post(
    "/companies/{company_id}/deactivate",
    response_model=AdminCompanyOut,
    operation_id="adminDeactivateCompany",
)
def deactivate_company(
    company_id: str,
    current: CurrentUser = Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    # No elimina: congela la empresa. Miembros, puestos y roles se conservan.
    try:
        return AdminService(db).set_company_status(current.user, company_id, is_active=False)
    except HANDLED as exc:
        raise _http_error(exc) from exc


@router.post(
    "/companies/{company_id}/activate",
    response_model=AdminCompanyOut,
    operation_id="adminActivateCompany",
)
def activate_company(
    company_id: str,
    current: CurrentUser = Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    try:
        return AdminService(db).set_company_status(current.user, company_id, is_active=True)
    except HANDLED as exc:
        raise _http_error(exc) from exc


# --- Usuarios


@router.post(
    "/users/{user_id}/revoke-sessions",
    response_model=RevokedSessionsOut,
    operation_id="adminRevokeUserSessions",
)
def revoke_user_sessions(
    user_id: str,
    current: CurrentUser = Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    try:
        return RevokedSessionsOut(revoked=AdminService(db).revoke_user_sessions(current.user, user_id))
    except HANDLED as exc:
        raise _http_error(exc) from exc


@router.post(
    "/users/{user_id}/password",
    response_model=RevokedSessionsOut,
    operation_id="adminResetUserPassword",
)
def reset_user_password(
    user_id: str,
    data: PasswordReset,
    current: CurrentUser = Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    """Asigna una contraseña nueva (recuperación asistida) y cierra todas sus sesiones.
    Comunica la contraseña al usuario por un canal seguro fuera de la API."""
    try:
        revoked = password_service.PasswordService(db).reset_by_admin(
            current.user, user_id, data.new_password.get_secret_value()
        )
    except password_service.UserNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado.") from exc
    return RevokedSessionsOut(revoked=revoked)
