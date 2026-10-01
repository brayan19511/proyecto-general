"""Respuestas de /batches (docs/modelo-datos.md)."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel


class BatchFileOut(BaseModel):
    id: str
    sequence: int
    original_filename: str
    size_bytes: int
    parse_status: str  # parsed | error
    parse_error: str | None
    used_ocr: bool
    beneficiary_name: str | None
    beneficiary_tax_id: str | None
    account: str | None
    currency: str | None
    amount: str | None  # Texto con 2 decimales, sin redondeos de coma flotante.
    operation_date: date | None
    already_sent_in_batch_id: str | None  # Aviso: este pago ya se envió en ese lote.
    # Cómo se detectó: "file" = el mismo PDF; "data" = otro PDF con el mismo RUC/DNI,
    # cuenta, moneda, monto, fecha (y número de operación si ambos lo tienen).
    already_sent_match: Literal["file", "data"] | None


class GroupTotal(BaseModel):
    currency: str
    symbol: str
    total: str


class GroupPayment(BaseModel):
    file_id: str
    suggested_filename: str  # titular + fecha: nombre en el ZIP y en el correo.
    currency: str
    amount: str
    account: str | None
    reference: str | None
    process_date: str | None


class GroupOut(BaseModel):
    """Constancias de un mismo proveedor.

    status: READY · MISSING_PROVIDER (no está en el maestro) · MISSING_PAYMENT_EMAIL.
    En un borrador se calcula con el maestro actual; en un lote enviado es lo que
    se congeló al enviar.
    """

    status: str
    provider_id: str | None
    provider_name: str
    provider_tax_id: str | None
    pdf_holder: str | None  # Nombre o documento tal como aparece en la constancia.
    payment_emails: list[str]
    payment_count: int
    totals: list[GroupTotal]
    payments: list[GroupPayment]


class BatchCounts(BaseModel):
    files: int
    parsed: int
    errors: int
    groups: int
    missing_provider: int
    missing_email: int


class BatchSummaryOut(BaseModel):
    id: str
    reference: str | None
    status: str  # draft | sending | sent
    file_count: int
    notification_dispatch_id: str | None
    created_at: datetime
    sent_at: datetime | None


class BatchOut(BatchSummaryOut):
    """ready_to_send: sin archivos con error, con al menos un grupo y todos READY."""

    ready_to_send: bool
    counts: BatchCounts
    files: list[BatchFileOut]
    groups: list[GroupOut]
