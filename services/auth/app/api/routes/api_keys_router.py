from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_user_company_context
from app.core.db.connection import get_db
from app.schemas.api_key import ApiKeyCreate, ApiKeyCreated, ApiKeyOut
from app.services.access_service import CompanyContext, PermissionDeniedError
from app.services.api_key_service import (
    ApiKeyLimitError,
    ApiKeyNotFoundError,
    ApiKeyService,
    InvalidExpirationError,
    InvalidScopeError,
    MembershipRequiredError,
)

# API keys propias en la empresa activa. Solo con login (Bearer): una API key
# no puede crear ni revocar keys.
router = APIRouter(prefix="/api-keys", tags=["api-keys"])

ERRORS = {
    ApiKeyNotFoundError: (status.HTTP_404_NOT_FOUND, "API key no encontrada."),
    ApiKeyLimitError: (status.HTTP_409_CONFLICT, "Alcanzaste el máximo de API keys vigentes; revoca una."),
    MembershipRequiredError: (status.HTTP_409_CONFLICT, "Solo un miembro de la empresa puede crear API keys en ella."),
    InvalidScopeError: (status.HTTP_422_UNPROCESSABLE_CONTENT, "Scope desconocido."),
    InvalidExpirationError: (status.HTTP_422_UNPROCESSABLE_CONTENT, "La fecha de vencimiento ya pasó."),
    PermissionDeniedError: (status.HTTP_403_FORBIDDEN, "No puedes dar a la key un permiso que no tienes."),
}
HANDLED = tuple(ERRORS)


def _http_error(exc: Exception) -> HTTPException:
    status_code, detail = ERRORS[type(exc)]
    return HTTPException(status_code=status_code, detail=detail)


@router.get("", response_model=list[ApiKeyOut], operation_id="listMyApiKeys")
def list_my_api_keys(
    ctx: CompanyContext = Depends(get_user_company_context),
    db: Session = Depends(get_db),
):
    return ApiKeyService(db).list_own(ctx)


@router.post("", response_model=ApiKeyCreated, status_code=status.HTTP_201_CREATED, operation_id="createApiKey")
def create_api_key(
    data: ApiKeyCreate,
    ctx: CompanyContext = Depends(get_user_company_context),
    db: Session = Depends(get_db),
):
    """Devuelve el secreto en `key` una sola vez. Úsalo en el header X-API-Key."""
    try:
        return ApiKeyService(db).create(ctx, data)
    except HANDLED as exc:
        raise _http_error(exc) from exc


@router.delete(
    "/{key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    operation_id="revokeApiKey",
)
def revoke_api_key(
    key_id: str,
    ctx: CompanyContext = Depends(get_user_company_context),
    db: Session = Depends(get_db),
):
    # Irreversible: para reemplazarla se crea otra.
    try:
        ApiKeyService(db).revoke(ctx, key_id)
    except HANDLED as exc:
        raise _http_error(exc) from exc
