from datetime import datetime

from pydantic import BaseModel, ConfigDict


class LogOut(BaseModel):
    """Cabecera: resumen de una solicitud."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    trace_id: str
    parent_operation_id: str | None
    method: str
    path: str
    status_code: int | None
    outcome: str | None  # success, warning, error; null = sin cerrar.
    ip_address: str | None
    user_agent: str | None
    user_id: str | None
    company_id: str | None
    started_at: datetime
    finished_at: datetime | None
    duration_ms: float | None


class LogDetailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    level: str
    kind: str
    message: str | None
    data: dict | None
    created_at: datetime


class LogStepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    step_id: str
    name: str
    phase: str
    message: str | None
    duration_ms: float | None
    created_at: datetime


class LogFullOut(LogOut):
    details: list[LogDetailOut]
    steps: list[LogStepOut]
