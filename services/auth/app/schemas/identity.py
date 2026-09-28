from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class CountryOut(BaseModel):
    code: str
    name: str


class DocumentTypeOut(BaseModel):
    id: str
    issuing_country_code: str
    code: str
    name: str
    # national_identity, residence, passport u other.
    category: str


class DocumentCreate(BaseModel):
    """Registra o actualiza el documento propio de un tipo.

    El número se guarda como texto (conserva ceros iniciales) y se valida con el
    formato del tipo después de quitar espacios, puntos y guiones. Formato
    válido no significa identidad verificada.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    document_type_id: str = Field(min_length=1, max_length=36)
    document_number: str = Field(min_length=1, max_length=50)
    expires_at: date | None = None


class DocumentOut(BaseModel):
    id: str
    type: DocumentTypeOut
    document_number: str
    expires_at: date | None
