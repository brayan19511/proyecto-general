from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    MetaData,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    event,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.models.common.mixin_model import AuditMixin


class Base(DeclarativeBase):
    """Base de los modelos del servicio. Todas sus tablas van en el schema pagos_proveedores.

    El schema se declara una sola vez aquí; los modelos lo heredan. Declararlo
    no lo crea en la base: lo crea migrations/env.py antes de migrar.
    """

    metadata = MetaData(schema="pagos_proveedores")


class Actor(AuditMixin, Base):
    """Quién realizó una acción en este servicio.

    - user: subject_ref = id del usuario validado por auth (sin FK a auth).
    - system: subject_ref = nombre estable de un proceso interno, si llega a haberlo.
    - service: otro servicio autenticado, cuando exista credencial máquina.

    Un actor se atribuye a sí mismo: al crearlo, id y created_by son el mismo
    valor (se genera el id antes: actor_id = new_id()). Así ninguna fila queda
    sin responsable ni hace falta un actor "inventado" de bootstrap.
    label es solo una ayuda de lectura: sin email ni datos personales.
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
    return Index(
        name,
        *columns,
        unique=True,
        postgresql_where=text("is_active"),
        mssql_where=text("is_active = 1"),
    )


class ChangeHistory(AuditMixin, Base):
    """Historial de negocio, de solo anexado: una fila por cambio.

    El responsable y la fecha son created_by / created_at. before/after llevan
    solo los campos permitidos del recurso. Se inserta en la misma transacción
    que el cambio: si falla, no hay cambio. Una corrección es otro evento, no la
    edición de uno anterior.
    """

    __tablename__ = "change_history"
    __table_args__ = (
        Index("ix_change_history_resource", "resource_type", "resource_id"),
        Index("ix_change_history_company_created", "company_id", "created_at"),
    )

    action: Mapped[str] = mapped_column(String(100))  # p. ej. "provider.update"
    resource_type: Mapped[str] = mapped_column(String(50))  # p. ej. "provider"
    resource_id: Mapped[str] = mapped_column(String(36))
    # Empresa afectada; NULL solo en cambios que no son de una empresa.
    company_id: Mapped[str | None] = mapped_column(String(36))
    trace_id: Mapped[str | None] = mapped_column(String(36))  # Enlace con audit.logs.
    before: Mapped[dict] = mapped_column(JSON, default=dict)
    after: Mapped[dict] = mapped_column(JSON, default=dict)
    # Motivo opcional que indica quien actúa (p. ej. al descartar un lote).
    reason: Mapped[str | None] = mapped_column(String(500))


def reject_change(*_):
    """Impide modificar o eliminar eventos históricos durante el flush del ORM."""
    raise ValueError("Los eventos históricos son de solo anexado")


# Protege el ciclo habitual del ORM; no protege contra SQL directo.
event.listen(ChangeHistory, "before_update", reject_change)
event.listen(ChangeHistory, "before_delete", reject_change)


class CompanySettings(AuditMixin, Base):
    """Configuración de pagos-proveedores por empresa (acuerdo 2026-10-01).

    Una fila activa por empresa; se crea al guardar la primera vez.
    default_template_code: plantilla de notificaciones para los lotes; NULL =
    DEFAULT_TEMPLATE_CODE del servicio. La elige payments.admin. Los cambios
    quedan en change_history (settings.update).
    """

    __tablename__ = "company_settings"
    __table_args__ = (unique_active("uq_company_settings_company_active", "company_id"),)

    company_id: Mapped[str] = mapped_column(String(36))
    default_template_code: Mapped[str | None] = mapped_column(String(100))


class Provider(AuditMixin, Base):
    """Proveedor de la empresa (antes finance.payment_providers de proyecto-05).

    company_id: UUID de la empresa en auth (sin FK). tax_id se guarda normalizado
    (document_key) y es único entre los activos de la empresa: el lector de
    constancias identifica primero por documento. match_names son las claves
    normalizadas (name_key) de legal_name y commercial_names, para identificar
    por nombre cuando la constancia no trae documento; se recalculan al guardar
    y nunca vienen del body. Una misma clave no puede pertenecer a dos
    proveedores activos de la empresa (sería ambiguo a quién enviarle).
    """

    __tablename__ = "providers"
    __table_args__ = (
        unique_active("uq_providers_company_tax_id_active", "company_id", "tax_id"),
        Index("ix_providers_company_active_name", "company_id", "is_active", "legal_name"),
    )

    company_id: Mapped[str] = mapped_column(String(36))
    tax_id: Mapped[str] = mapped_column(String(20))
    legal_name: Mapped[str] = mapped_column(String(255))
    commercial_names: Mapped[list] = mapped_column(JSON, default=list)
    match_names: Mapped[list] = mapped_column(JSON, default=list)
    payment_emails: Mapped[list] = mapped_column(JSON, default=list)


class Batch(AuditMixin, Base):
    """Lote de constancias: se suben una vez, se leen y se envían a los proveedores.

    status: draft (se puede corregir el maestro, quitar archivos o descartarlo)
    → sending (entregas congeladas, llamando a notificaciones; reintentar es
    seguro) → sent (notification_dispatch_id fijado). Quién subió: created_by;
    quién envió: updated_by. Descartar = baja lógica, solo en draft.

    template_code, custom_subject y custom_message se fijan al enviar (fase 1) y
    se reutilizan si hay que reintentar: así el reintento manda lo mismo.
    """

    __tablename__ = "batches"
    __table_args__ = (
        CheckConstraint("status IN ('draft', 'sending', 'sent')", name="ck_batches_status"),
        Index("ix_batches_company_created", "company_id", "created_at"),
    )

    company_id: Mapped[str] = mapped_column(String(36))
    reference: Mapped[str | None] = mapped_column(String(100))  # Va como consumer_reference a notificaciones.
    status: Mapped[str] = mapped_column(String(10), default="draft")
    template_code: Mapped[str | None] = mapped_column(String(100))
    custom_subject: Mapped[str | None] = mapped_column(String(998))  # Parámetro "asunto" de la plantilla.
    custom_message: Mapped[str | None] = mapped_column(Text)  # Parámetro "mensaje" de la plantilla.
    notification_dispatch_id: Mapped[str | None] = mapped_column(String(36))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class BatchDelivery(AuditMixin, Base):
    """Evidencia de un envío: un proveedor del lote tal como estaba al enviar.

    Copia tax_id, legal_name y payment_emails: si después se edita el maestro,
    aquí queda a quién y a qué correos se envió. Su id es el consumer_reference
    del mensaje en notificaciones.
    """

    __tablename__ = "batch_deliveries"
    __table_args__ = (UniqueConstraint("batch_id", "sequence", name="uq_batch_deliveries_batch_sequence"),)

    company_id: Mapped[str] = mapped_column(String(36))
    batch_id: Mapped[str] = mapped_column(ForeignKey("batches.id"))
    sequence: Mapped[int] = mapped_column(Integer)
    provider_id: Mapped[str] = mapped_column(ForeignKey("providers.id"))
    tax_id: Mapped[str] = mapped_column(String(20))
    legal_name: Mapped[str] = mapped_column(String(255))
    payment_emails: Mapped[list] = mapped_column(JSON)
    totals: Mapped[list] = mapped_column(JSON)  # [{"moneda", "moneda_simbolo", "total"}]


class BatchFile(AuditMixin, Base):
    """Una constancia del lote: su contenido (sin purga: retención indefinida),
    el resultado de leerla y, al enviar, la entrega a la que se asignó.

    Quitar un archivo de un borrador = baja lógica (is_active=false).
    already_sent_in_batch_id: este pago ya se envió en otro lote de la empresa;
    solo es un aviso. already_sent_match dice cómo se detectó: "file" (mismo
    PDF, sha256) o "data" (otro PDF con los mismos datos de pago).
    """

    __tablename__ = "batch_files"
    __table_args__ = (
        UniqueConstraint("batch_id", "sequence", name="uq_batch_files_batch_sequence"),
        # El mismo PDF no puede estar dos veces activo en un lote.
        unique_active("uq_batch_files_batch_sha256_active", "batch_id", "sha256"),
        Index("ix_batch_files_company_sha256", "company_id", "sha256"),
        CheckConstraint("parse_status IN ('parsed', 'error')", name="ck_batch_files_parse_status"),
    )

    company_id: Mapped[str] = mapped_column(String(36))
    batch_id: Mapped[str] = mapped_column(ForeignKey("batches.id"))
    sequence: Mapped[int] = mapped_column(Integer)
    original_filename: Mapped[str] = mapped_column(String(255))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    content: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
    parse_status: Mapped[str] = mapped_column(String(10))
    parse_error: Mapped[str | None] = mapped_column(String(500))
    used_ocr: Mapped[bool] = mapped_column(Boolean, default=False)
    # Lo extraído, en columnas para consultar (NULL si no se pudo leer).
    beneficiary_name: Mapped[str | None] = mapped_column(String(255))
    beneficiary_tax_id: Mapped[str | None] = mapped_column(String(30))
    account: Mapped[str | None] = mapped_column(String(60))
    currency: Mapped[str | None] = mapped_column(String(10))
    amount: Mapped[Decimal | None] = mapped_column(Numeric(19, 2))
    operation_date: Mapped[date | None] = mapped_column(Date)
    # Todo lo que devolvió el lector (datos_destino y datos_operacion), con
    # importes como texto: es la entrada del agrupamiento.
    extracted: Mapped[dict | None] = mapped_column(JSON)
    already_sent_in_batch_id: Mapped[str | None] = mapped_column(ForeignKey("batches.id"))
    already_sent_match: Mapped[str | None] = mapped_column(String(10))
    delivery_id: Mapped[str | None] = mapped_column(ForeignKey("batch_deliveries.id"))
