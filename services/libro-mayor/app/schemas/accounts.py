from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.services.errors import InvalidDataError


class AccountCreate(BaseModel):
    """Alta de una cuenta a sincronizar. La empresa sale de X-Company-Id, no del body."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    code: str = Field(min_length=1, max_length=20, examples=["979005400", "95"])
    match_mode: Literal["exact", "prefix"]
    name: str | None = Field(default=None, max_length=150, examples=["UTILES DE ESCRITORIO"])


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    code: str
    match_mode: str
    name: str | None
    is_active: bool
    created_at: datetime
    deleted_at: datetime | None


class SapCompanyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    sap_schema: str = Field(min_length=1, max_length=128, examples=["SBO_RASH_PRODUCCION"])
    source_view: str = Field(min_length=1, max_length=128, examples=["VW_LIBRO_MAYOR_PERSONALIZADO_2"])
    sync_start_date: date = Field(examples=["2026-01-01"])


class SapCompanyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    company_id: str
    sap_schema: str
    source_view: str
    sync_start_date: date
    created_at: datetime


class AccountUpdate(BaseModel):
    """Solo los campos enviados cambian. code/match_mode solo sin líneas sincronizadas (si no, 409)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    code: str | None = Field(default=None, min_length=1, max_length=20)
    match_mode: Literal["exact", "prefix"] | None = None
    name: str | None = Field(default=None, max_length=150)  # null borra el nombre.


class SapCompanyUpdate(BaseModel):
    """Solo los campos enviados cambian. sap_schema solo sin líneas sincronizadas (si no, 409)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    sap_schema: str | None = Field(default=None, min_length=1, max_length=128)
    source_view: str | None = Field(default=None, min_length=1, max_length=128)
    sync_start_date: date | None = None


def not_null_changes(body: BaseModel, *fields: str) -> dict:
    """Campos enviados; rechaza null en los que no lo admiten."""
    changes = body.model_dump(exclude_unset=True)
    nulls = [name for name in fields if name in changes and changes[name] is None]
    if nulls:
        raise InvalidDataError(f"No pueden ser null: {', '.join(nulls)}.")
    return changes
