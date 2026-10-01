"""Cuerpos y respuestas de /templates. La empresa sale de X-Company-Id, nunca del body."""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

_SINGLE_LINE = r"^[^\x00-\x1f\x7f]*$"
Code = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[a-z0-9][a-z0-9_.-]{0,99}$")]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150, pattern=_SINGLE_LINE)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]
SubjectTemplate = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=998, pattern=_SINGLE_LINE)
]
Body = Annotated[str, StringConstraints(min_length=1)]
Address = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=320)]


class TemplateCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: Code = Field(examples=["payment_provider_summary"])
    name: Name = Field(examples=["Constancia de pago a proveedores"])
    description: Description | None = None
    subject_template: SubjectTemplate = Field(examples=["CONSTANCIA DE PAGO {{ proveedor }} || RASH PERU"])
    body_html_template: Body | None = None
    body_text_template: Body | None = None
    to: list[Address] = Field(default_factory=list)  # Destinatarios fijos.
    cc: list[Address] = Field(default_factory=list)
    bcc: list[Address] = Field(default_factory=list)
    reply_to: Address | None = None


class TemplateUpdate(BaseModel):
    """Solo cambian los campos enviados. description, body_html_template,
    body_text_template y reply_to admiten null; el resto no."""

    model_config = ConfigDict(extra="forbid")

    code: Code | None = None
    name: Name | None = None
    description: Description | None = None
    subject_template: SubjectTemplate | None = None
    body_html_template: Body | None = None
    body_text_template: Body | None = None
    to: list[Address] | None = None
    cc: list[Address] | None = None
    bcc: list[Address] | None = None
    reply_to: Address | None = None


TEMPLATE_NOT_NULL_FIELDS = ("code", "name", "subject_template", "to", "cc", "bcc")


class TemplateOut(BaseModel):
    id: str
    code: str
    name: str
    description: str | None
    subject_template: str
    body_html_template: str | None
    body_text_template: str | None
    to: list[str]
    cc: list[str]
    bcc: list[str]
    reply_to: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


class PreviewIn(BaseModel):
    """Parámetros de ejemplo para armar la plantilla sin enviar nada."""

    model_config = ConfigDict(extra="forbid")

    parameters: dict = Field(default_factory=dict)


class PreviewOut(BaseModel):
    subject: str
    # HTML armado: el front debe mostrarlo en un <iframe sandbox>, como los mensajes.
    body_html: str | None
    body_text: str | None
