from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DocumentTypeOut(BaseModel):
    code: str
    label: str
    partner: Literal["customer", "supplier", "none"]  # Rótulo de CardCode/CardName; none = sin búsqueda por socio.
    criteria: list[str]  # Búsquedas exactas admitidas: doc_entry, doc_num, num_at_card, folio.


class DocumentOut(BaseModel):
    type_code: str
    doc_entry: int
    doc_num: int | None
    num_at_card: str | None
    folio: str | None
    card_code: str | None
    card_name: str | None
    doc_date: date | None
    has_attachments: bool


class DocumentSearchOut(BaseModel):
    """Una página de resultados. next_offset null = no hay más."""

    limit: int
    offset: int
    next_offset: int | None
    items: list[DocumentOut]


class AttachmentOut(BaseModel):
    line: int  # Identifica el anexo al pedir la descarga.
    file_name: str
    attached_on: date | None


DownloadMode = Literal["single", "sequential", "zip"]


class DownloadFileIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type_code: str = Field(max_length=10)
    doc_entry: int = Field(ge=1)
    line: int = Field(ge=1)


class DownloadIn(BaseModel):
    """Archivos a descargar. Nombres y DocNum los toma el servidor de SAP, no del body."""

    model_config = ConfigDict(extra="forbid")

    company_db: str = Field(min_length=1, max_length=100)
    mode: DownloadMode
    files: list[DownloadFileIn] = Field(min_length=1, max_length=50)


class DownloadFileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    seq: int  # Se usa en GET /documents/downloads/{id}/files/{seq}.
    type_code: str
    doc_entry: int
    doc_num: int | None
    line: int
    file_name: str
    status: Literal["pending", "delivered", "failed"]
    delivered_at: datetime | None
    error: str | None


class DownloadOut(BaseModel):
    id: str
    company_db: str
    mode: DownloadMode
    file_count: int
    user_id: str  # Usuario de auth que descargó.
    trace_id: str | None
    created_at: datetime
    files: list[DownloadFileOut]


class DownloadListItem(BaseModel):
    id: str
    company_db: str
    mode: DownloadMode
    file_count: int
    delivered_count: int
    user_id: str
    created_at: datetime


class DownloadPage(BaseModel):
    total: int
    limit: int
    offset: int
    next_offset: int | None
    items: list[DownloadListItem]
