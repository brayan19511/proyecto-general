"""Cuerpos y respuestas de /providers. La empresa sale de X-Company-Id, nunca del body."""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

_SINGLE_LINE = r"^[^\x00-\x1f\x7f]*$"
TaxId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=30, pattern=_SINGLE_LINE)]
LegalName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255, pattern=_SINGLE_LINE)]
CommercialName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255, pattern=_SINGLE_LINE)]
Email = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=320)]

MAX_NAMES = 20
MAX_EMAILS = 20


class ProviderCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tax_id: TaxId = Field(examples=["20609307235"])
    legal_name: LegalName = Field(examples=["BUSINESS IT PERU SAC"])
    commercial_names: list[CommercialName] = Field(default_factory=list, max_length=MAX_NAMES)
    payment_emails: list[Email] = Field(default_factory=list, max_length=MAX_EMAILS)


class ProviderUpdate(BaseModel):
    """Solo cambian los campos enviados; ninguno admite null."""

    model_config = ConfigDict(extra="forbid")

    tax_id: TaxId | None = None
    legal_name: LegalName | None = None
    commercial_names: list[CommercialName] | None = Field(default=None, max_length=MAX_NAMES)
    payment_emails: list[Email] | None = Field(default=None, max_length=MAX_EMAILS)


class ProviderOut(BaseModel):
    id: str
    tax_id: str
    legal_name: str
    commercial_names: list[str]
    payment_emails: list[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None
