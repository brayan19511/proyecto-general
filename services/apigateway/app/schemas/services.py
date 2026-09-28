from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ServiceStateOut(BaseModel):
    service: str
    # Estado efectivo: lo que la central aplica ahora mismo en esta réplica.
    enabled: bool
    enabled_by_config: bool
    # False: solo se cambia por configuración (<SERVICIO>_ENABLED).
    panel_managed: bool
    # Estado guardado desde la administración; null = sin cambios (vale la configuración).
    db_enabled: bool | None
    reason: str | None
    updated_at: datetime | None
    updated_by: str | None


class ServiceStateUpdate(BaseModel):
    """Solo estos campos: actor y fechas los asigna el servidor."""

    model_config = ConfigDict(extra="forbid")

    is_enabled: bool
    reason: str | None = Field(default=None, max_length=300)


class HistoryEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    action: str
    resource_type: str
    resource_id: str
    trace_id: str | None
    before: dict
    after: dict
    created_at: datetime
    created_by: str | None


class IpBlockCreate(BaseModel):
    """Solo estos campos: actor y fechas de auditoría los asigna el servidor."""

    model_config = ConfigDict(extra="forbid")

    # IP ("203.0.113.7") o rango CIDR ("203.0.113.0/24"). Se guarda normalizado.
    network: str = Field(max_length=50)
    reason: str | None = Field(default=None, max_length=300)
    # null = sin vencimiento. Debe incluir zona horaria y ser futura.
    expires_at: datetime | None = None


class IpBlockOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    network: str
    reason: str | None
    expires_at: datetime | None
    is_active: bool
    created_at: datetime
    created_by: str | None
    deleted_at: datetime | None
    deleted_by: str | None
