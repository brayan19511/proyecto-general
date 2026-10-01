"""Respuestas de las consultas de mensajes, adjuntos e intentos (docs/api.md)."""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints


class ActionIn(BaseModel):
    """Cuerpo opcional de reprocesar y cancelar: el motivo queda en el historial."""

    model_config = ConfigDict(extra="forbid")

    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)] | None = None


class RequeuedOut(BaseModel):
    requeued: int  # Mensajes failed/uncertain que volvieron a pending.


class MessageSummaryOut(BaseModel):
    """Fila del listado de mensajes de un envío (sin cuerpo ni adjuntos)."""

    id: str
    sequence: int
    consumer_reference: str | None
    to: list[str]
    cc: list[str]
    bcc: list[str]
    subject: str
    status: str
    attempts_in_cycle: int
    last_attempt_at: datetime | None
    sent_at: datetime | None
    cancelled_at: datetime | None


class AttachmentOut(BaseModel):
    id: str
    sequence: int
    filename: str
    content_type: str
    size_bytes: int
    available: bool  # False: el contenido ya se purgó (descarga → 410).


class MessageTechnicalOut(BaseModel):
    """Solo con notifications.admin."""

    message_id_header: str
    size_bytes: int
    next_attempt_at: datetime | None
    locked_until: datetime | None


class MessageDetailOut(MessageSummaryOut):
    dispatch_id: str
    reply_to: str | None
    # HTML tal como se enviará: el front debe mostrarlo en un <iframe sandbox>.
    body_html: str | None
    body_text: str | None
    cancel_reason: str | None
    attachments: list[AttachmentOut]
    created_at: datetime
    technical: MessageTechnicalOut | None  # None sin notifications.admin.


class AttemptOut(BaseModel):
    """Intento de envío (solo notifications.admin)."""

    id: str
    attempt_number: int
    smtp_account_id: str | None
    smtp_account_name: str | None
    started_at: datetime
    finished_at: datetime
    outcome: str
    smtp_code: int | None
    error_kind: str | None
    smtp_response: str | None
