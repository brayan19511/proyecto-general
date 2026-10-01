"""Cuerpos y respuestas de /dispatches (docs/api.md).

POST /dispatches es multipart: la parte "payload" es este JSON (DispatchPayload)
y cada adjunto es una parte de archivo cuyo nombre ("f1", "f2"…) se referencia
desde messages[].attachments. La empresa y el solicitante salen de auth, nunca
del body.
"""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

MAX_MESSAGES = 500  # Acuerdo: máximo por envío.

_SINGLE_LINE = r"^[^\x00-\x1f\x7f]*$"
Reference = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100, pattern=_SINGLE_LINE)]
Consumer = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[a-z0-9][a-z0-9_.-]{0,49}$")]
Address = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=320)]
PartName = Annotated[str, StringConstraints(min_length=1, max_length=100)]


TemplateCode = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[a-z0-9][a-z0-9_.-]{0,99}$")]


class MessageIn(BaseModel):
    """Contenido armado (subject + body) O plantilla (template_code + parameters), no ambos.

    Con plantilla, to puede ir vacío si la plantilla trae destinatarios fijos.
    """

    model_config = ConfigDict(extra="forbid")

    consumer_reference: Reference | None = None  # P. ej. código del proveedor.
    to: list[Address] = Field(default_factory=list)
    cc: list[Address] = Field(default_factory=list)
    bcc: list[Address] = Field(default_factory=list)
    reply_to: Address | None = None
    subject: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=998)] | None = None
    body_html: str | None = Field(default=None, min_length=1)
    body_text: str | None = Field(default=None, min_length=1)
    template_code: TemplateCode | None = None
    parameters: dict | None = None  # Datos para la plantilla; no se guardan.
    attachments: list[PartName] = Field(default_factory=list)  # Nombres de partes del multipart.

    @property
    def has_content(self) -> bool:
        return self.subject is not None or self.body_html is not None or self.body_text is not None

    @model_validator(mode="after")
    def _content_or_template(self):
        if not self.has_content:
            return self  # Usa una plantilla (la suya o la del envío: lo revisa DispatchPayload).
        if self.template_code is not None:
            raise ValueError("con template_code no se envían subject, body_html ni body_text")
        if self.parameters is not None:
            raise ValueError("parameters solo se usa con una plantilla")
        if self.subject is None:
            raise ValueError("sin plantilla, cada mensaje necesita subject")
        if self.body_html is None and self.body_text is None:
            raise ValueError("sin plantilla, cada mensaje necesita body_html o body_text")
        return self


class DispatchPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    consumer: Consumer | None = None  # Informativo, p. ej. "payment_provider".
    consumer_reference: Reference | None = None  # P. ej. id del lote del consumidor.
    # Plantilla por defecto para los mensajes que no traen la suya (acuerdo 4 del paso 2).
    template_code: TemplateCode | None = None
    messages: list[MessageIn] = Field(min_length=1, max_length=MAX_MESSAGES)

    @model_validator(mode="after")
    def _resolve_templates(self):
        for index, message in enumerate(self.messages):
            if message.template_code is None and not message.has_content:
                if self.template_code is None:
                    raise ValueError(
                        f"messages[{index}]: necesita subject y body, o una plantilla (aquí o en el envío)"
                    )
            if self.template_code is not None and message.template_code is None and message.has_content:
                raise ValueError(
                    f"messages[{index}]: el envío usa la plantilla {self.template_code}; "
                    "no se mezcla con subject/body (indica otro template_code en el mensaje si hace falta)"
                )
        return self

    def template_for(self, message: MessageIn) -> str | None:
        """Plantilla efectiva del mensaje: la suya o la del envío."""
        if message.has_content:
            return None
        return message.template_code or self.template_code


DispatchStatus = Literal["pending", "in_progress", "completed", "completed_with_errors"]


class DispatchCounts(BaseModel):
    total: int = 0
    pending: int = 0
    sending: int = 0
    retrying: int = 0
    sent: int = 0
    failed: int = 0
    uncertain: int = 0
    cancelled: int = 0


class DispatchOut(BaseModel):
    """Estado y progreso calculados en el momento a partir de sus mensajes."""

    id: str
    kind: str
    consumer: str | None
    consumer_reference: str | None
    status: DispatchStatus
    counts: DispatchCounts
    requested_by_user_id: str | None  # Usuario de auth que lo solicitó (None si lo creó un proceso).
    requested_by_email: str | None  # Su correo según auth al crear el envío (None si lo creó un proceso).
    created_at: datetime
