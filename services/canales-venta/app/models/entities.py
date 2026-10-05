"""Tablas propias de canales-venta (schema canales_venta en la base de la plataforma).

Las tablas de SKU NO están aquí: son de Ofisis (app/lastmiller/channels.py).
Aquí solo vive lo que este servicio necesita recordar: quién hizo cada cambio,
el historial de los SKU y las cargas masivas con su vista previa.
"""

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    UniqueConstraint,
    event,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.models.common.mixin_model import AuditMixin


class Base(DeclarativeBase):
    """Base de los modelos del servicio. Todas sus tablas van en el schema canales_venta.

    El schema se declara una sola vez aquí; los modelos lo heredan. Declararlo
    no lo crea en la base: lo crea migrations/env.py antes de migrar.
    """

    metadata = MetaData(schema="canales_venta")


class Actor(AuditMixin, Base):
    """Quién realizó una acción en este servicio (mismo diseño que libro-mayor).

    - user: subject_ref = id del usuario validado por auth (sin FK a auth).
    - system / service: procesos u otros servicios, cuando existan.

    Un actor se atribuye a sí mismo: id y created_by son el mismo valor.
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


IMPORT_KINDS = ("sku_full", "sku_partial", "promotions")
# previewed: lista para aplicar; invalid: el archivo tiene errores (no se aplica);
# applying: en curso; applied / failed: terminó; interrupted: quedó en curso sin
# avance (caída del proceso) y se liberó el canal; cancelled: vista previa descartada
# sin aplicar (no se tocó Ofisis).
IMPORT_STATUSES = ("previewed", "invalid", "applying", "applied", "failed", "interrupted", "cancelled")


class SkuImport(AuditMixin, Base):
    """Una carga masiva: el archivo leído, su vista previa y su aplicación.

    No se guarda el archivo, solo sus filas normalizadas (rows) y su SHA-256.
    plan es lo que mostró la vista previa; al aplicar se recalcula contra el
    estado actual de Ofisis y, si cambió (plan_hash distinto), no se aplica.
    created_by = quien previsualizó; applied_by = quien aplicó.
    """

    __tablename__ = "sku_imports"
    __table_args__ = (
        CheckConstraint(f"kind IN {IMPORT_KINDS}", name="ck_sku_imports_kind"),
        CheckConstraint(f"status IN {IMPORT_STATUSES}", name="ck_sku_imports_status"),
        Index("ix_sku_imports_channel_created", "channel", "created_at"),
        # Una sola carga en curso por canal (índice filtrado: PostgreSQL y SQL Server).
        Index(
            "uq_sku_imports_channel_applying",
            "channel",
            unique=True,
            postgresql_where=text("status = 'applying'"),
            mssql_where=text("status = 'applying'"),
        ),
    )

    company_id: Mapped[str] = mapped_column(String(36))
    channel: Mapped[str] = mapped_column(String(20))  # p. ej. "pe/rappi"
    kind: Mapped[str] = mapped_column(String(20))
    create_missing: Mapped[bool] = mapped_column(Boolean, default=False)
    filename: Mapped[str] = mapped_column(String(255))
    file_sha256: Mapped[str] = mapped_column(String(64))
    rows: Mapped[list] = mapped_column(JSON, default=list)
    errors: Mapped[list] = mapped_column(JSON, default=list)
    plan: Mapped[dict] = mapped_column(JSON, default=dict)
    plan_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20))
    total_changes: Mapped[int] = mapped_column(Integer, default=0)
    applied_changes: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(String(500))
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    applied_by: Mapped[str | None] = mapped_column(ForeignKey("actors.id"))
    trace_id: Mapped[str | None] = mapped_column(String(36))  # Enlace con audit.logs.


class SkuEvent(AuditMixin, Base):
    """Historial de negocio de los SKU, de solo anexado: una fila por cambio en Ofisis.

    action: sku.created, sku.activated, sku.deactivated, sku.deleted,
    promotion.added, promotion.removed. before/after: {"is_active": ...} o
    {"promotion": ...}. import_id: la carga masiva que lo produjo (NULL = cambio
    individual). El responsable y la fecha son created_by / created_at.
    """

    __tablename__ = "sku_events"
    __table_args__ = (
        Index("ix_sku_events_channel_sku", "channel", "sku"),
        Index("ix_sku_events_channel_created", "channel", "created_at"),
        Index("ix_sku_events_import", "import_id"),
    )

    company_id: Mapped[str] = mapped_column(String(36))
    channel: Mapped[str] = mapped_column(String(20))
    sku: Mapped[str] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(30))
    before: Mapped[dict] = mapped_column(JSON, default=dict)
    after: Mapped[dict] = mapped_column(JSON, default=dict)
    import_id: Mapped[str | None] = mapped_column(ForeignKey("sku_imports.id"))
    trace_id: Mapped[str | None] = mapped_column(String(36))


def reject_change(*_):
    """Impide modificar o eliminar eventos históricos durante el flush del ORM."""
    raise ValueError("Los eventos históricos son de solo anexado")


# Protege el ciclo habitual del ORM; no protege contra SQL directo.
event.listen(SkuEvent, "before_update", reject_change)
event.listen(SkuEvent, "before_delete", reject_change)
