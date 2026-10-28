"""Tablas de sap-operaciones (schema sap_operaciones en la base de la plataforma).

SAP no se lee ni se escribe por base de datos: solo por el Service Layer. Aquí
vive lo que el servicio necesita recordar: quién hizo cada cosa, las bases SAP
sugeridas por empresa, los trabajos masivos con sus ítems y su historial.
"""

from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    event,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.models.common.mixin_model import AuditMixin


class Base(DeclarativeBase):
    """Base de los modelos del servicio. Todas sus tablas van en el schema sap_operaciones.

    Declararlo no lo crea en la base: lo crea migrations/env.py antes de migrar.
    """

    metadata = MetaData(schema="sap_operaciones")


class Actor(AuditMixin, Base):
    """Quién realizó una acción (mismo diseño que libro-mayor y canales-venta).

    user: subject_ref = id del usuario validado por auth (sin FK a auth).
    Un actor se atribuye a sí mismo: id y created_by son el mismo valor.
    """

    __tablename__ = "actors"
    __table_args__ = (
        UniqueConstraint("kind", "subject_ref"),
        CheckConstraint("kind IN ('user', 'system', 'service')", name="ck_actors_kind"),
    )

    kind: Mapped[str] = mapped_column(String(10))
    subject_ref: Mapped[str] = mapped_column(String(100))
    label: Mapped[str | None] = mapped_column(String(100))


def unique_active(name: str, *columns: str) -> Index:
    """Unicidad solo entre filas activas: una baja lógica no bloquea volver a
    registrar el mismo valor. Índice filtrado en PostgreSQL y SQL Server."""
    return Index(name, *columns, unique=True, postgresql_where=text("is_active"), mssql_where=text("is_active = 1"))


class SapDatabase(AuditMixin, Base):
    """Base SAP (CompanyDB) sugerida para una empresa de la plataforma.

    Es una lista de ayuda: el operador también puede escribir otra base
    (decisión del usuario, 2026-10-04). company_id es el id de la empresa en
    auth (sin FK). DELETE = baja lógica.
    """

    __tablename__ = "sap_databases"
    __table_args__ = (unique_active("uq_sap_databases_company_db_active", "company_id", "company_db"),)

    company_id: Mapped[str] = mapped_column(String(36))
    company_db: Mapped[str] = mapped_column(String(100))
    label: Mapped[str | None] = mapped_column(String(100))


class SapSettings(AuditMixin, Base):
    """Configuración SAP de una empresa: la URL de su Service Layer.

    Editable solo por el administrador de plataforma (decisión del usuario,
    2026-10-04): las claves SAP de los operadores se envían a esta URL, así que
    cambiarla equivale a decidir a dónde viajan. Sin fila, se usa
    SAP_SERVICE_LAYER_URL del despliegue. Un cambio es otro evento en
    change_history; la fila anterior queda dada de baja.
    """

    __tablename__ = "sap_settings"
    __table_args__ = (unique_active("uq_sap_settings_company_active", "company_id"),)

    company_id: Mapped[str] = mapped_column(String(36))
    service_layer_url: Mapped[str] = mapped_column(String(300))


JOB_KINDS = ("document_action", "reconciliation")
# draft: vista previa, aún sin credenciales; queued: esperando al worker;
# running: en proceso; completed / completed_with_errors / failed / cancelled: terminó.
# failed = se detuvo (SAP no responde, credenciales inválidas): se puede reanudar.
JOB_STATUSES = ("draft", "queued", "running", "completed", "completed_with_errors", "failed", "cancelled")
ITEM_STATUSES = ("pending", "running", "succeeded", "failed", "uncertain", "cancelled")


class Job(AuditMixin, Base):
    """Un trabajo masivo contra SAP: una lista de ítems que el worker ejecuta de a uno.

    - document_action: POST {entity}({DocEntry})/{action} por cada documento.
    - reconciliation: POST InternalReconciliations por cada ReconNum del Excel.

    Credenciales: sap_user en claro (no es secreto); la clave, cifrada en
    sap_password_encrypted y conservada (decisión del usuario, 2026-10-04).
    Solo el administrador de plataforma la ve descifrada (con evento).
    Bloqueo del worker: locked_by / locked_until (se renueva por ítem).
    """

    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint(f"kind IN {JOB_KINDS}", name="ck_jobs_kind"),
        CheckConstraint(f"status IN {JOB_STATUSES}", name="ck_jobs_status"),
        Index("ix_jobs_company_created", "company_id", "created_at"),
        Index("ix_jobs_status", "status"),
    )

    company_id: Mapped[str] = mapped_column(String(36))
    kind: Mapped[str] = mapped_column(String(20))
    company_db: Mapped[str] = mapped_column(String(100))
    entity: Mapped[str | None] = mapped_column(String(100))  # Solo document_action.
    action: Mapped[str | None] = mapped_column(String(100))  # Solo document_action.
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)  # p. ej. recon_date, filename, sha256.
    status: Mapped[str] = mapped_column(String(25))
    total_items: Mapped[int] = mapped_column(Integer, default=0)
    succeeded_items: Mapped[int] = mapped_column(Integer, default=0)
    failed_items: Mapped[int] = mapped_column(Integer, default=0)
    uncertain_items: Mapped[int] = mapped_column(Integer, default=0)
    cancelled_items: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(String(500))  # Por qué se detuvo (seguro de mostrar).
    sap_user: Mapped[str | None] = mapped_column(String(100))
    sap_password_encrypted: Mapped[str | None] = mapped_column(Text)
    # Quién ingresó las credenciales guardadas (al encolar o al reanudar con nuevas).
    # Dato de auditoría: la clave solo la ve el administrador de plataforma.
    credentials_by: Mapped[str | None] = mapped_column(ForeignKey("actors.id"))
    # Service Layer con que se ejecuta, fijado al encolar o reanudar: un cambio
    # posterior de la configuración no desvía este trabajo (ni sus credenciales).
    service_layer_url: Mapped[str | None] = mapped_column(String(300))
    cancel_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_by: Mapped[str | None] = mapped_column(String(100))
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    trace_id: Mapped[str | None] = mapped_column(String(36))  # Solicitud que lo creó (audit.logs).


class JobItem(AuditMixin, Base):
    """Un ítem del trabajo: una llamada al Service Layer.

    reference: DocEntry (acciones) o ReconNum (conciliaciones). payload: cuerpo
    del POST (conciliaciones). Antes de llamar a SAP se guarda "running": si el
    worker cae a mitad, el ítem queda "uncertain" y no se repite solo (pudo
    haberse aplicado en SAP). sap_error: código y mensaje de SAP, saneados.
    """

    __tablename__ = "job_items"
    __table_args__ = (
        CheckConstraint(f"status IN {ITEM_STATUSES}", name="ck_job_items_status"),
        UniqueConstraint("job_id", "seq"),
        Index("ix_job_items_job_status", "job_id", "status"),
    )

    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"))
    seq: Mapped[int] = mapped_column(Integer)
    reference: Mapped[str] = mapped_column(String(100))
    payload: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20))
    http_status: Mapped[int | None] = mapped_column(Integer)
    sap_error: Mapped[str | None] = mapped_column(String(1000))
    # Lo que se envió ({"method", "path", "body"}) y lo que respondió SAP
    # ({"status", "body"}, acotado a 20 KB), para revisar cada ítem. Sin credenciales:
    # la sesión va en una cookie que no se guarda.
    request: Mapped[dict | None] = mapped_column(JSON)
    response: Mapped[dict | None] = mapped_column(JSON)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class JobEvent(AuditMixin, Base):
    """Historial de negocio de los trabajos, de solo anexado.

    action: job.created, job.queued, job.cancel_requested, job.resumed,
    job.finished, job.credentials_viewed (quién vio la clave guardada).
    details: valores permitidos (nunca la clave). created_by = actor;
    job.finished lo registra el worker con el actor que encoló el trabajo.
    """

    __tablename__ = "job_events"
    __table_args__ = (Index("ix_job_events_job", "job_id", "created_at"),)

    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"))
    company_id: Mapped[str] = mapped_column(String(36))
    action: Mapped[str] = mapped_column(String(40))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    trace_id: Mapped[str | None] = mapped_column(String(36))


class ChangeHistory(AuditMixin, Base):
    """Historial de negocio de lo que no es un trabajo (hoy, la lista de bases SAP).
    Solo anexado; before/after con los campos permitidos del recurso."""

    __tablename__ = "change_history"
    __table_args__ = (
        Index("ix_change_history_resource", "resource_type", "resource_id"),
        Index("ix_change_history_company_created", "company_id", "created_at"),
    )

    company_id: Mapped[str] = mapped_column(String(36))
    action: Mapped[str] = mapped_column(String(60))  # p. ej. "sap_database.created"
    resource_type: Mapped[str] = mapped_column(String(40))
    resource_id: Mapped[str] = mapped_column(String(36))
    before: Mapped[dict] = mapped_column(JSON, default=dict)
    after: Mapped[dict] = mapped_column(JSON, default=dict)
    trace_id: Mapped[str | None] = mapped_column(String(36))


DOWNLOAD_MODES = ("single", "sequential", "zip")
DOWNLOAD_FILE_STATUSES = ("pending", "delivered", "failed")


class DocumentDownload(AuditMixin, Base):
    """Registro de negocio de una descarga de anexos SAP (quién bajó qué), solo anexado.

    Se crea al pedir la descarga, con la lista de archivos ya validada contra
    SAP. mode: single (un archivo), sequential (varios, uno por uno) o zip.
    created_by = actor que descarga; solo él puede bajar sus archivos.
    """

    __tablename__ = "document_downloads"
    __table_args__ = (
        CheckConstraint(f"mode IN {DOWNLOAD_MODES}", name="ck_document_downloads_mode"),
        Index("ix_document_downloads_company_created", "company_id", "created_at"),
        Index("ix_document_downloads_created_by", "created_by", "created_at"),
    )

    company_id: Mapped[str] = mapped_column(String(36))
    company_db: Mapped[str] = mapped_column(String(100))
    mode: Mapped[str] = mapped_column(String(20))
    file_count: Mapped[int] = mapped_column(Integer)
    trace_id: Mapped[str | None] = mapped_column(String(36))


class DocumentDownloadFile(AuditMixin, Base):
    """Un archivo de la descarga: documento, anexo y si llegó a entregarse.

    Lo único que cambia después del alta es la entrega: status (pending →
    delivered / failed), delivered_at y error (mensaje seguro de mostrar).
    """

    __tablename__ = "document_download_files"
    __table_args__ = (
        CheckConstraint(f"status IN {DOWNLOAD_FILE_STATUSES}", name="ck_document_download_files_status"),
        UniqueConstraint("download_id", "seq"),
    )

    download_id: Mapped[str] = mapped_column(ForeignKey("document_downloads.id"))
    seq: Mapped[int] = mapped_column(Integer)
    type_code: Mapped[str] = mapped_column(String(10))
    doc_entry: Mapped[int] = mapped_column(Integer)
    doc_num: Mapped[int | None] = mapped_column(Integer)
    attachment_entry: Mapped[int] = mapped_column(Integer)
    line: Mapped[int] = mapped_column(Integer)
    file_name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(String(300))


def reject_change(*_):
    """Impide modificar o eliminar eventos históricos durante el flush del ORM."""
    raise ValueError("Los eventos históricos son de solo anexado")


# Protege el ciclo habitual del ORM; no protege contra SQL directo.
event.listen(JobEvent, "before_update", reject_change)
event.listen(JobEvent, "before_delete", reject_change)
event.listen(ChangeHistory, "before_update", reject_change)
event.listen(ChangeHistory, "before_delete", reject_change)
event.listen(DocumentDownload, "before_update", reject_change)
event.listen(DocumentDownload, "before_delete", reject_change)
event.listen(DocumentDownloadFile, "before_delete", reject_change)
