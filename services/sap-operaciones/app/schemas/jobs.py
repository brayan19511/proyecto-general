from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, SecretStr, field_validator

JobKind = Literal["document_action", "reconciliation"]
JobStatus = Literal["draft", "queued", "running", "completed", "completed_with_errors", "failed", "cancelled"]
ItemStatus = Literal["pending", "running", "succeeded", "failed", "uncertain", "cancelled"]


class DocumentActionPreviewIn(BaseModel):
    """Acción masiva sobre documentos: POST {entity}({DocEntry})/{action} por cada uno."""

    model_config = ConfigDict(extra="forbid")

    company_db: str = Field(min_length=1, max_length=100, description="Base SAP (CompanyDB), de la lista o escrita.")
    entity: str = Field(min_length=1, max_length=100, examples=["Invoices"])
    action: str = Field(min_length=1, max_length=100, examples=["Cancel"])
    documents: str = Field(min_length=1, max_length=2_000_000,
                           description="DocEntry separados por saltos de línea, comas o espacios.")


class Credentials(BaseModel):
    """Usuario y clave SAP del operador. La clave se guarda cifrada (nunca en logs)."""

    model_config = ConfigDict(extra="forbid")

    sap_user: str = Field(min_length=1, max_length=100)
    sap_password: SecretStr = Field(min_length=1, max_length=200)


class ResumeIn(BaseModel):
    """Reanudar: sin datos usa las credenciales guardadas; con ambos, las reemplaza."""

    model_config = ConfigDict(extra="forbid")

    sap_user: str | None = Field(default=None, max_length=100)
    sap_password: SecretStr | None = Field(default=None, max_length=200)


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    kind: JobKind
    company_db: str
    entity: str | None
    action: str | None
    parameters: dict
    status: JobStatus
    total_items: int
    succeeded_items: int
    failed_items: int
    uncertain_items: int
    cancelled_items: int
    error_message: str | None
    sap_user: str | None  # El usuario SAP no es secreto; la clave nunca se devuelve aquí.
    has_credentials: bool = False
    # Solo en GET /jobs/{id}: true si quien consulta puede ver la clave (administrador de plataforma).
    can_view_credentials: bool = False
    service_layer_url: str | None  # Con la que se ejecuta (fijada al encolar o reanudar).
    trace_id: str | None  # Solicitud que lo creó: buscarla en Monitoreo › Actividad y logs.
    created_by: str  # Actor (id interno) que lo creó.
    cancel_requested_at: datetime | None
    created_at: datetime
    queued_at: datetime | None
    started_at: datetime | None
    finished_at: datetime | None


class JobListItem(JobOut):
    created_by_user: str  # Id del usuario de auth que creó el trabajo.


class JobPage(BaseModel):
    total: int
    limit: int
    offset: int
    next_offset: int | None
    items: list[JobListItem]


class PreviewOut(BaseModel):
    """Vista previa: con errores, job es null y nada se guardó."""

    job: JobOut | None
    errors: list[dict]  # [{"row": n | null, "message": str}]
    duplicates: int  # Documentos repetidos que se omitieron.


class ItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    seq: int
    reference: str  # DocEntry o ReconNum.
    status: ItemStatus
    http_status: int | None
    sap_error: str | None
    started_at: datetime | None
    finished_at: datetime | None


class ItemDetailOut(ItemOut):
    """Ítem con lo que se envió a SAP y lo que respondió (acotado a 20 KB)."""

    request: dict | None  # {"method", "path", "body"}
    response: dict | None  # {"status", "body"}; null = sin respuesta (pendiente o incierto).


class ItemPage(BaseModel):
    total: int
    limit: int
    offset: int
    next_offset: int | None
    items: list[ItemOut]


class EventOut(BaseModel):
    action: str
    details: dict
    actor_kind: str  # user o system (el worker).
    actor: str  # Id de usuario de auth o nombre del proceso.
    created_at: datetime


class CredentialsOut(BaseModel):
    sap_user: str | None
    sap_password: str


class DatabaseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company_db: str = Field(min_length=1, max_length=100)
    label: str | None = Field(default=None, max_length=100)


class DatabaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    company_db: str
    label: str | None
    created_at: datetime


class SettingsIn(BaseModel):
    """URL del Service Layer de la empresa. null o vacío = usar la del despliegue."""

    model_config = ConfigDict(extra="forbid")

    service_layer_url: str | None = Field(default=None, max_length=300, examples=["https://10.0.0.14:50000/b1s/v1"])

    @field_validator("service_layer_url")
    @classmethod
    def valid_url(cls, value: str | None) -> str | None:
        value = (value or "").strip().rstrip("/")
        if not value:
            return None
        url = HttpUrl(value)  # Valida esquema, host y puerto.
        if url.scheme not in ("http", "https") or url.query or url.fragment or url.username:
            raise ValueError("Usa una URL http(s) sin usuario, parámetros ni fragmento.")
        return value


class SettingsOut(BaseModel):
    service_layer_url: str | None
    source: Literal["company", "default"]  # company = propia de la empresa; default = la del despliegue.
    verify_tls: bool  # SAP_VERIFY_TLS del despliegue (no editable aquí).
    updated_at: datetime | None
