from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser, get_current_user
from app.core.db.connection import get_db
from app.schemas.identity import DocumentCreate, DocumentOut
from app.schemas.me import MyProfileOut, ProfileOut, ProfileUpdate
from app.services.identity_service import (
    DocumentExistsError,
    DocumentNotFoundError,
    DocumentTypeNotFoundError,
    IdentityService,
    InvalidDocumentNumberError,
    InvalidExpirationError,
)
from app.services.profile_service import InvalidProfileError, ProfileService

# Perfil propio: datos personales y documentos. Bajo /me porque cada usuario
# gestiona solo el suyo (quedan /auth/me/profile y /auth/me/documents).
# El master admin ve el de cualquiera en GET /auth/admin/users/{id}.
router = APIRouter(prefix="/me", tags=["profile"])

ERRORS = {
    InvalidProfileError: None,  # Mensaje propio en exc.detail.
    DocumentTypeNotFoundError: (status.HTTP_404_NOT_FOUND, "Tipo de documento no encontrado."),
    DocumentNotFoundError: (status.HTTP_404_NOT_FOUND, "Documento no encontrado."),
    DocumentExistsError: (status.HTTP_409_CONFLICT, "Ya tienes un documento de ese tipo; elimínalo para registrar otro."),
    InvalidDocumentNumberError: (status.HTTP_422_UNPROCESSABLE_CONTENT, "El número no tiene el formato de ese tipo de documento."),
    InvalidExpirationError: (status.HTTP_422_UNPROCESSABLE_CONTENT, "La fecha de vencimiento ya pasó."),
}
HANDLED = tuple(ERRORS)


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, InvalidProfileError):
        return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=exc.detail)
    status_code, detail = ERRORS[type(exc)]
    return HTTPException(status_code=status_code, detail=detail)


# --- Datos personales (uno por cuenta: sin crear ni eliminar)


@router.get("/profile", response_model=MyProfileOut, operation_id="getMyProfile")
def get_my_profile(current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    """Datos personales y documentos vigentes del usuario."""
    return ProfileService(db).get_mine(current.user)


@router.patch("/profile", response_model=ProfileOut, operation_id="updateMyProfile")
def update_my_profile(
    data: ProfileUpdate,
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Solo cambia los campos enviados; null borra un valor."""
    try:
        return ProfileService(db).update(current.user, data)
    except HANDLED as exc:
        raise _http_error(exc) from exc


# --- Documentos de identidad propios


@router.get("/documents", response_model=list[DocumentOut], operation_id="listMyDocuments")
def list_my_documents(current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return IdentityService(db).list_documents(current.user)


@router.post(
    "/documents",
    response_model=DocumentOut,
    status_code=status.HTTP_201_CREATED,
    operation_id="addMyDocument",
)
def add_my_document(
    data: DocumentCreate,
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return IdentityService(db).add_document(current.user, data)
    except HANDLED as exc:
        raise _http_error(exc) from exc


@router.delete(
    "/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    operation_id="deleteMyDocument",
)
def delete_my_document(
    document_id: str,
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        IdentityService(db).delete_document(current.user, document_id)
    except HANDLED as exc:
        raise _http_error(exc) from exc
