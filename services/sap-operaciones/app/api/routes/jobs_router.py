"""Trabajos masivos y bases SAP: /sap-operaciones/...

Permisos (acumulativos, alcance company): view consulta; execute además crea,
ejecuta, cancela y reanuda trabajos y administra la lista de bases SAP. Ver
las credenciales guardadas: solo el administrador de plataforma.
"""

from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.api.dependencies import CompanyContext, require_company_permission, require_platform_admin_in_company
from app.core.config import settings
from app.core.db.connection import get_db
from app.core.permissions import CAN_EXECUTE, CAN_VIEW
from app.models.entities import Job
from app.schemas.jobs import (
    Credentials,
    CredentialsOut,
    DatabaseIn,
    DatabaseOut,
    DocumentActionPreviewIn,
    EventOut,
    ItemDetailOut,
    ItemPage,
    ItemStatus,
    JobKind,
    JobListItem,
    JobOut,
    JobPage,
    JobStatus,
    PreviewOut,
    ResumeIn,
    SettingsIn,
    SettingsOut,
)
from app.schemas.page import Page
from app.services import job_service
from app.services.inputs import MAX_FILE_BYTES
from app.services.csv_export import csv_response

router = APIRouter(tags=["sap"])


# Estados en español para la descarga (mismos textos que el front).
ITEM_STATUS_ES = {"pending": "Pendiente", "running": "En curso", "succeeded": "Correcto", "failed": "Error de SAP",
                  "uncertain": "Incierto", "cancelled": "Cancelado"}


def job_out(job: Job) -> JobOut:
    return JobOut.model_validate(job).model_copy(update={"has_credentials": bool(job.sap_password_encrypted)})


def preview_out(result: dict) -> PreviewOut:
    job = result["job"]
    return PreviewOut(job=job_out(job) if job else None, errors=result["errors"], duplicates=result["duplicates"])


# --- Vista previa (crea el trabajo en borrador)


@router.post("/jobs/document-actions/preview", response_model=PreviewOut, operation_id="previewDocumentAction")
def preview_document_action(
    data: DocumentActionPreviewIn,
    ctx: CompanyContext = Depends(require_company_permission(*CAN_EXECUTE)),
    db: Session = Depends(get_db),
):
    """Valida la lista de documentos. Sin errores, crea el trabajo en borrador
    (no se ejecuta nada hasta POST /jobs/{id}/enqueue)."""
    return preview_out(job_service.preview_document_action(
        db, ctx, company_db=data.company_db, entity=data.entity, action=data.action, documents=data.documents))


@router.post("/jobs/reconciliations/preview", response_model=PreviewOut, operation_id="previewReconciliation")
def preview_reconciliation(
    company_db: str = Form(min_length=1, max_length=100),
    # Obligatoria: el servidor está en UTC y "hoy" podría ser otro día que en Lima.
    recon_date: date = Form(description="Fecha de la conciliación (ReconDate), AAAA-MM-DD."),
    file: UploadFile = File(description=".xlsx con ReconNum, SrcObjAbs, SrcObjTyp, TransRowId, TransId, ShortName, ReconcileAmount."),
    ctx: CompanyContext = Depends(require_company_permission(*CAN_EXECUTE)),
    db: Session = Depends(get_db),
):
    """Lee el Excel y agrupa por ReconNum (cada grupo debe sumar 0). Sin errores,
    crea el trabajo en borrador: un ítem por ReconNum."""
    content = file.file.read(MAX_FILE_BYTES + 1)
    return preview_out(job_service.preview_reconciliation(
        db, ctx, company_db=company_db, recon_date=recon_date, content=content, filename=file.filename))


# --- Ciclo de vida


@router.post("/jobs/{job_id}/enqueue", response_model=JobOut, operation_id="enqueueJob")
def enqueue(
    job_id: str,
    data: Credentials,
    ctx: CompanyContext = Depends(require_company_permission(*CAN_EXECUTE)),
    db: Session = Depends(get_db),
):
    """Ejecuta un borrador con el usuario y la clave SAP del operador. Antes prueba
    el inicio de sesión en SAP (422 si SAP lo rechaza). Responde enseguida: el
    trabajo lo procesa el worker; su avance se consulta en GET /jobs/{id}."""
    return job_out(job_service.enqueue(db, ctx, job_id, data.sap_user.strip(), data.sap_password.get_secret_value()))


@router.post("/jobs/{job_id}/cancel", response_model=JobOut, operation_id="cancelJob")
def cancel(job_id: str, ctx: CompanyContext = Depends(require_company_permission(*CAN_EXECUTE)),
           db: Session = Depends(get_db)):
    """Lo ya enviado a SAP no se deshace; los pendientes se cancelan."""
    return job_out(job_service.cancel(db, ctx, job_id))


@router.post("/jobs/{job_id}/resume", response_model=JobOut, operation_id="resumeJob")
def resume(job_id: str, data: ResumeIn, ctx: CompanyContext = Depends(require_company_permission(*CAN_EXECUTE)),
           db: Session = Depends(get_db)):
    """Reanuda un trabajo detenido: sigue con los pendientes (los inciertos no se repiten)."""
    password = data.sap_password.get_secret_value() if data.sap_password else None
    return job_out(job_service.resume(db, ctx, job_id, (data.sap_user or "").strip() or None, password))


@router.get("/jobs/{job_id}/credentials", response_model=CredentialsOut, operation_id="revealJobCredentials")
def reveal_credentials(job_id: str, ctx: CompanyContext = Depends(require_company_permission(*CAN_VIEW)),
                       db: Session = Depends(get_db)):
    """Usuario y clave SAP guardados del trabajo: solo el administrador de plataforma
    (si no, 403). Queda en el historial (job.credentials_viewed)."""
    return job_service.reveal_credentials(db, ctx, job_id)


# --- Consultas


@router.get("/jobs", response_model=JobPage, operation_id="listJobs")
def list_jobs(
    status_filter: JobStatus | None = Query(default=None, alias="status"),
    kind: JobKind | None = None,
    page: Page = Depends(),
    ctx: CompanyContext = Depends(require_company_permission(*CAN_VIEW)),
    db: Session = Depends(get_db),
):
    rows, total = job_service.list_jobs(db, ctx, status=status_filter, kind=kind, limit=page.limit, offset=page.offset)
    items = [JobListItem(**job_out(r["job"]).model_dump(), created_by_user=r["created_by_user"]) for r in rows]
    return JobPage(total=total, limit=page.limit, offset=page.offset, next_offset=page.next_offset(total), items=items)


@router.get("/jobs/{job_id}", response_model=JobOut, operation_id="getJob")
def get_job(job_id: str, ctx: CompanyContext = Depends(require_company_permission(*CAN_VIEW)),
            db: Session = Depends(get_db)):
    """can_view_credentials indica si quien consulta puede ver la clave guardada."""
    job = job_service.get_job(db, ctx, job_id)
    return job_out(job).model_copy(update={"can_view_credentials": job_service.can_reveal(db, ctx, job)})


@router.get("/jobs/{job_id}/items", response_model=ItemPage, operation_id="listJobItems")
def list_items(
    job_id: str,
    status_filter: ItemStatus | None = Query(default=None, alias="status"),
    reference: str | None = Query(default=None, max_length=100, description="DocEntry o ReconNum exacto."),
    page: Page = Depends(),
    ctx: CompanyContext = Depends(require_company_permission(*CAN_VIEW)),
    db: Session = Depends(get_db),
):
    items, total = job_service.list_items(db, ctx, job_id, status=status_filter, reference=reference,
                                          limit=page.limit, offset=page.offset)
    return ItemPage(total=total, limit=page.limit, offset=page.offset, next_offset=page.next_offset(total), items=items)


@router.get("/jobs/{job_id}/items/export", operation_id="exportJobItems", response_class=Response,
            responses={200: {"content": {"text/csv": {}}}})
def export_items(job_id: str, ctx: CompanyContext = Depends(require_company_permission(*CAN_VIEW)),
                 db: Session = Depends(get_db)):
    """CSV con todos los ítems del trabajo (estado y respuesta de SAP). Cada fila repite
    trabajo, base y operación para poder juntar varios archivos. Fechas en la hora
    local de EXPORT_UTC_OFFSET_HOURS. La cabecera completa está en GET /jobs/{id}."""
    job = job_service.get_job(db, ctx, job_id)
    items = job_service.all_items(db, ctx, job_id)
    operation = f"{job.entity}/{job.action}" if job.kind == "document_action" else f"Conciliación {job.parameters.get('filename', '')}".strip()
    rows = (
        [job.id, job.company_db, operation, i.seq, i.reference, ITEM_STATUS_ES.get(i.status, i.status), i.http_status,
         i.sap_error, local_time(i.started_at), local_time(i.finished_at)]
        for i in items
    )
    zone = f"UTC{settings.EXPORT_UTC_OFFSET_HOURS:+d}"
    return csv_response(f"sap-trabajo-{job.id[:8]}.csv", [
        "Trabajo", "Base SAP", "Operación", "#", "Referencia", "Estado", "HTTP", "Respuesta de SAP",
        f"Inicio ({zone})", f"Fin ({zone})",
    ], rows)


def local_time(value: datetime | None) -> datetime | None:
    """UTC → hora local con desfase fijo (sin base de zonas horarias: decisión del usuario)."""
    if value is None:
        return None
    return (value.astimezone(timezone.utc) + timedelta(hours=settings.EXPORT_UTC_OFFSET_HOURS)).replace(tzinfo=None)


@router.get("/jobs/{job_id}/items/{seq}", response_model=ItemDetailOut, operation_id="getJobItem")
def get_item(job_id: str, seq: int, ctx: CompanyContext = Depends(require_company_permission(*CAN_VIEW)),
             db: Session = Depends(get_db)):
    """Un ítem con el JSON enviado a SAP y la respuesta recibida."""
    return job_service.get_item(db, ctx, job_id, seq)


@router.get("/jobs/{job_id}/events", response_model=list[EventOut], operation_id="listJobEvents")
def list_events(job_id: str, ctx: CompanyContext = Depends(require_company_permission(*CAN_VIEW)),
                db: Session = Depends(get_db)):
    return job_service.list_events(db, ctx, job_id)


# --- Configuración SAP de la empresa


@router.get("/settings", response_model=SettingsOut, operation_id="getSapSettings")
def get_settings(ctx: CompanyContext = Depends(require_company_permission(*CAN_VIEW)), db: Session = Depends(get_db)):
    """URL del Service Layer vigente para la empresa (propia o la del despliegue)."""
    return job_service.get_settings(db, ctx)


@router.patch("/settings", response_model=SettingsOut, operation_id="updateSapSettings")
def update_settings(data: SettingsIn, ctx: CompanyContext = Depends(require_platform_admin_in_company),
                    db: Session = Depends(get_db)):
    """Solo administrador de plataforma: las claves SAP de los operadores viajan a
    esta URL. Afecta a los trabajos que se encolen o reanuden desde ahora."""
    return job_service.update_settings(db, ctx, data.service_layer_url)


# --- Bases SAP sugeridas


@router.get("/databases", response_model=list[DatabaseOut], operation_id="listSapDatabases")
def list_databases(ctx: CompanyContext = Depends(require_company_permission(*CAN_VIEW)), db: Session = Depends(get_db)):
    return job_service.list_databases(db, ctx)


@router.post("/databases", response_model=DatabaseOut, status_code=status.HTTP_201_CREATED, operation_id="createSapDatabase")
def create_database(data: DatabaseIn, ctx: CompanyContext = Depends(require_company_permission(*CAN_EXECUTE)),
                    db: Session = Depends(get_db)):
    return job_service.create_database(db, ctx, data.company_db, data.label)


@router.delete("/databases/{database_id}", status_code=status.HTTP_204_NO_CONTENT, operation_id="deleteSapDatabase")
def delete_database(database_id: str, ctx: CompanyContext = Depends(require_company_permission(*CAN_EXECUTE)),
                    db: Session = Depends(get_db)):
    """Baja lógica: deja de sugerirse; los trabajos que la usaron no cambian."""
    job_service.delete_database(db, ctx, database_id)
