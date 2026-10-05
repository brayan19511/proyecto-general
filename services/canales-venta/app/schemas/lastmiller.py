from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.lastmiller.channels import Country, Provider


class ChannelOut(BaseModel):
    country: Country
    provider: Provider
    name: str
    has_promotions: bool = Field(description="El canal maneja promociones (hoy solo PedidosYa Perú).")


class SkuOut(BaseModel):
    sku: str
    external_id: str | None = Field(description="Id del SKU en Rappi o PedidosYa.")
    is_active: bool
    has_promotion: bool | None = Field(description="null en canales sin promociones.")
    # Fechas tal como las guarda Ofisis (datetime de SQL Server): hora del
    # servidor de Ofisis, sin zona horaria. No son UTC.
    created_at: datetime | None
    updated_at: datetime | None


class SkuPage(BaseModel):
    """Una página de SKU. next_offset null = no hay más."""

    total: int
    limit: int
    offset: int
    next_offset: int | None
    items: list[SkuOut]


class SkuCreate(BaseModel):
    """Alta de un SKU. El id externo no se envía: es el mismo sku (acuerdo del usuario, 2026-10-04)."""

    model_config = ConfigDict(extra="forbid")

    sku: str = Field(min_length=1, max_length=255)
    is_active: bool = True

    @field_validator("sku")
    @classmethod
    def strip_sku(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("El SKU no puede estar vacío.")
        return value


class SkuUpdate(BaseModel):
    """Lo único editable de un SKU es su estado on/off."""

    model_config = ConfigDict(extra="forbid")

    is_active: bool


ImportKind = Literal["sku_full", "sku_partial", "promotions"]


class ImportSummaryOut(BaseModel):
    """Una carga masiva, sin el detalle del plan (listados)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    kind: ImportKind
    create_missing: bool
    filename: str
    status: str  # previewed, invalid, applying, applied, failed, interrupted, cancelled
    total_changes: int
    applied_changes: int
    error_message: str | None
    created_at: datetime
    applied_at: datetime | None


class ImportOut(ImportSummaryOut):
    """Carga con su vista previa completa.

    plan (SKU): rows, create [{sku, active}], activate, deactivate,
    deactivate_unlisted (solo carga completa), missing, unchanged.
    plan (promociones): rows, add, remove, missing (bloquea), inactive (aviso), unchanged.
    errors: problemas del archivo [{row, message}]; con errores no se aplica.
    """

    errors: list[dict]
    plan: dict
    can_apply: bool


class ImportPage(BaseModel):
    total: int
    limit: int
    offset: int
    next_offset: int | None
    items: list[ImportSummaryOut]


class EventOut(BaseModel):
    id: str
    sku: str
    action: str  # sku.created, sku.activated, sku.deactivated, sku.deleted, promotion.added, promotion.removed
    before: dict
    after: dict
    import_id: str | None  # Carga que lo produjo; null = cambio individual.
    user_id: str  # Usuario de auth que hizo el cambio.
    created_at: datetime


class EventPage(BaseModel):
    total: int
    limit: int
    offset: int
    next_offset: int | None
    items: list[EventOut]
