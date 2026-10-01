from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class SyncRunCreate(BaseModel):
    """Sincronizar una cuenta registrada en un rango de fechas de contabilización (inclusivo)."""

    model_config = ConfigDict(extra="forbid")

    account_id: str = Field(min_length=1, max_length=36)
    date_from: date = Field(examples=["2026-09-01"])
    date_to: date = Field(examples=["2026-09-30"])


class SyncRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    account_id: str
    kind: str  # sync (manual) | initial | delta (horario)
    origin: str  # manual | schedule
    status: str  # pending | running | succeeded | failed
    date_from: date
    date_to: date
    days_total: int
    days_done: int
    rows_read: int
    rows_inserted: int
    rows_updated: int
    safe_error: str | None
    created_at: datetime
    started_at: datetime | None
    heartbeat_at: datetime | None
    finished_at: datetime | None
    schedule_slot: datetime | None  # Turno del horario (UTC); null en las manuales.


class SyncStatusOut(BaseModel):
    """Estado por cuenta activa. consecutive_failures > 0: algo falla desde la última carga correcta."""

    account_id: str
    code: str
    match_mode: str
    name: str | None
    watermark: date | None  # Día SAP desde el que leerá el próximo delta; null = aún sin carga inicial.
    last_success_at: datetime | None
    hours_since_success: float | None
    consecutive_failures: int
    last_run_id: str | None
    last_run_kind: str | None
    last_run_status: str | None
    last_error: str | None
