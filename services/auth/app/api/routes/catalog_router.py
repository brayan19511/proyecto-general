from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.db.connection import get_db
from app.schemas.identity import CountryOut, DocumentTypeOut
from app.services.identity_service import IdentityService

# Catálogos de solo lectura para cualquier usuario autenticado. Se cargan con
# el seed (data.py); no tienen CRUD.
router = APIRouter(prefix="/catalog", tags=["catalog"], dependencies=[Depends(get_current_user)])


@router.get("/countries", response_model=list[CountryOut], operation_id="listCountries")
def list_countries(db: Session = Depends(get_db)):
    return IdentityService(db).list_countries()


@router.get("/document-types", response_model=list[DocumentTypeOut], operation_id="listDocumentTypes")
def list_document_types(
    country: str | None = Query(default=None, min_length=2, max_length=2, description="País emisor, p. ej. PE."),
    db: Session = Depends(get_db),
):
    return IdentityService(db).list_document_types(country.upper() if country else None)
