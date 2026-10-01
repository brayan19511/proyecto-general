from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
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
    """Base de los modelos del servicio. Todas sus tablas van en el schema notificaciones.

    El schema se declara una sola vez aquí; los modelos lo heredan. Declararlo
    no lo crea en la base: lo crea migrations/env.py antes de migrar.
    """

    metadata = MetaData(schema="notificaciones")


class Actor(AuditMixin, Base):
    """Quién realizó una acción en este servicio.

    - user: subject_ref = id del usuario validado por auth (sin FK a auth).
    - system: subject_ref = nombre estable del proceso, p. ej.
      "notificaciones.worker" (envía y reintenta) o "notificaciones.retention"
      (avisos y cancelación por plazo). Se crean la primera vez que se usan.
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
    solo los campos permitidos del recurso (nunca contraseñas ni secretos).
    Se inserta en la misma transacción que el cambio: si falla, no hay cambio.
    Una corrección es otro evento, no la edición de uno anterior.
    """

    __tablename__ = "change_history"
    __table_args__ = (
        Index("ix_change_history_resource", "resource_type", "resource_id"),
        Index("ix_change_history_company_created", "company_id", "created_at"),
    )

    action: Mapped[str] = mapped_column(String(100))  # p. ej. "smtp_account.update"
    resource_type: Mapped[str] = mapped_column(String(50))  # p. ej. "smtp_account"
    resource_id: Mapped[str] = mapped_column(String(36))
    # Empresa afectada; NULL solo en cambios que no son de una empresa.
    company_id: Mapped[str | None] = mapped_column(String(36))
    trace_id: Mapped[str | None] = mapped_column(String(36))  # Enlace con audit.logs.
    before: Mapped[dict] = mapped_column(JSON, default=dict)
    after: Mapped[dict] = mapped_column(JSON, default=dict)
    # Motivo opcional que indica quien actúa (p. ej. al reprocesar o cancelar).
    reason: Mapped[str | None] = mapped_column(String(500))


def reject_change(*_):
    """Impide modificar o eliminar eventos históricos durante el flush del ORM."""
    raise ValueError("Los eventos históricos son de solo anexado")


# Protege el ciclo habitual del ORM; no protege contra SQL directo.
event.listen(ChangeHistory, "before_update", reject_change)
event.listen(ChangeHistory, "before_delete", reject_change)


class SmtpAccount(AuditMixin, Base):
    """Cuenta SMTP de una empresa. Se usan las activas por priority (menor
    primero) y, a igual prioridad, por created_at.

    company_id es el UUID de la empresa en auth (sin FK: auth es otro servicio).
    password_encrypted guarda la contraseña cifrada con app/core/crypto.py:
    nunca en claro, nunca devuelta por la API ni copiada al historial.
    security: starttls (normalmente 587) o ssl (TLS implícito, normalmente
    465). No se admite SMTP sin cifrar: la contraseña viajaría legible.

    priority no es única: intercambiar dos prioridades chocaría con un índice
    único no diferido.
    """

    __tablename__ = "smtp_accounts"
    __table_args__ = (
        unique_active("uq_smtp_accounts_company_name_active", "company_id", "name"),
        Index("ix_smtp_accounts_company_active_priority", "company_id", "is_active", "priority"),
        CheckConstraint("port BETWEEN 1 AND 65535", name="ck_smtp_accounts_port"),
        CheckConstraint(
            "security IN ('starttls', 'ssl')", name="ck_smtp_accounts_security"
        ),
        CheckConstraint("priority >= 0", name="ck_smtp_accounts_priority"),
        CheckConstraint(
            "timeout_seconds BETWEEN 1 AND 120", name="ck_smtp_accounts_timeout"
        ),
    )

    company_id: Mapped[str] = mapped_column(String(36))
    name: Mapped[str] = mapped_column(String(100))  # p. ej. "Office 365 principal"
    host: Mapped[str] = mapped_column(String(255))
    port: Mapped[int] = mapped_column(Integer)
    security: Mapped[str] = mapped_column(String(10))
    # NULL en relays que no piden autenticación.
    username: Mapped[str | None] = mapped_column(String(255))
    password_encrypted: Mapped[str | None] = mapped_column(Text)
    from_email: Mapped[str] = mapped_column(String(320))
    from_name: Mapped[str | None] = mapped_column(String(100))
    priority: Mapped[int] = mapped_column(Integer)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=30)


class Template(AuditMixin, Base):
    """Plantilla general de correo (paso 2; reemplaza a mailing_parameters de proyecto-05).

    El consumidor envía template_code + parameters; notificaciones arma asunto y
    cuerpo con Jinja2 en sandbox (app/services/template_engine.py) y suma los
    destinatarios fijos a los del consumidor. Los mensajes guardan el resultado
    ya armado y template_id: editar la plantilla no cambia lo ya enviado.
    """

    __tablename__ = "templates"
    __table_args__ = (
        unique_active("uq_templates_company_code_active", "company_id", "code"),
        CheckConstraint(
            "body_html_template IS NOT NULL OR body_text_template IS NOT NULL", name="ck_templates_body"
        ),
    )

    company_id: Mapped[str] = mapped_column(String(36))
    code: Mapped[str] = mapped_column(String(100))  # p. ej. "payment_provider_summary".
    name: Mapped[str] = mapped_column(String(150))
    description: Mapped[str | None] = mapped_column(String(500))
    subject_template: Mapped[str] = mapped_column(String(998))
    body_html_template: Mapped[str | None] = mapped_column(Text)
    body_text_template: Mapped[str | None] = mapped_column(Text)
    # Destinatarios fijos (ya normalizados), que se suman a los del consumidor.
    to_addresses: Mapped[list] = mapped_column(JSON, default=list)
    cc_addresses: Mapped[list] = mapped_column(JSON, default=list)
    bcc_addresses: Mapped[list] = mapped_column(JSON, default=list)
    reply_to: Mapped[str | None] = mapped_column(String(320))


def _in(column: str, values: tuple[str, ...]) -> str:
    """Expresión SQL portable para un CHECK de valores fijos: column IN ('a', 'b')."""
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


DISPATCH_KINDS = ("standard", "failure_notice")
MESSAGE_STATUSES = ("pending", "sending", "retrying", "sent", "failed", "uncertain", "cancelled")
CANCEL_REASONS = ("manual", "expired")
ATTEMPT_OUTCOMES = ("sent", "transient_error", "permanent_error", "uncertain", "no_account")


class Dispatch(AuditMixin, Base):
    """Un envío: el trabajo que agrupa N mensajes (docs/modelo-datos.md).

    Quien lo solicitó es created_by. No guarda estado ni progreso: se calculan
    agregando sus mensajes, así varios workers no actualizan la misma fila.

    Idempotencia: única (company_id, created_by, idempotency_key) sobre TODAS las
    filas. Misma clave y mismo request_hash = el mismo envío; distinto hash = 409.

    kind failure_notice: aviso previo a la cancelación por plazo, creado por el
    proceso notificaciones.retention para el envío notice_for_dispatch_id. Un
    aviso fallido nunca genera otro aviso.
    """

    __tablename__ = "dispatches"
    __table_args__ = (
        UniqueConstraint("company_id", "created_by", "idempotency_key", name="uq_dispatches_idempotency"),
        CheckConstraint(_in("kind", DISPATCH_KINDS), name="ck_dispatches_kind"),
        CheckConstraint(
            "(kind = 'standard' AND notice_for_dispatch_id IS NULL)"
            " OR (kind = 'failure_notice' AND notice_for_dispatch_id IS NOT NULL)",
            name="ck_dispatches_notice_target",
        ),
        Index("ix_dispatches_company_created", "company_id", "created_at"),
        Index("ix_dispatches_company_creator_created", "company_id", "created_by", "created_at"),
    )

    company_id: Mapped[str] = mapped_column(String(36))
    kind: Mapped[str] = mapped_column(String(20), default="standard")
    idempotency_key: Mapped[str] = mapped_column(String(100))
    request_hash: Mapped[str] = mapped_column(String(64))  # SHA-256 del contenido recibido.
    consumer: Mapped[str | None] = mapped_column(String(50))  # Informativo, p. ej. payment_provider.
    consumer_reference: Mapped[str | None] = mapped_column(String(100))  # P. ej. id del lote.
    # Tomado de auth al crear (para el aviso de fallos). No está verificado.
    requester_email: Mapped[str | None] = mapped_column(String(320))
    notice_for_dispatch_id: Mapped[str | None] = mapped_column(ForeignKey("dispatches.id"))
    trace_id: Mapped[str | None] = mapped_column(String(36))  # Enlace con audit.logs.


class Message(AuditMixin, Base):
    """Un correo dentro de un envío. Su contenido no se edita: para corregir se crea otro envío.

    Estados: pending → sending → sent | retrying | failed | uncertain;
    retrying → sending; failed/uncertain → pending (reproceso manual) o cancelled.
    Un bloqueo vencido en sending pasa a uncertain, nunca vuelve a la cola: el
    worker pudo morir después de transmitirlo.

    is_active no se usa para cancelar: cancelar es un estado. Los mensajes no se
    dan de baja. company_id se repite (también está en el envío) para filtrar
    sin join.
    """

    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint("dispatch_id", "sequence", name="uq_messages_dispatch_sequence"),
        CheckConstraint(_in("status", MESSAGE_STATUSES), name="ck_messages_status"),
        CheckConstraint("body_html IS NOT NULL OR body_text IS NOT NULL", name="ck_messages_body"),
        CheckConstraint(
            "(status = 'cancelled' AND cancelled_at IS NOT NULL AND cancel_reason IS NOT NULL)"
            " OR (status <> 'cancelled' AND cancelled_at IS NULL AND cancel_reason IS NULL)",
            name="ck_messages_cancelled",
        ),
        CheckConstraint(
            f"cancel_reason IS NULL OR {_in('cancel_reason', CANCEL_REASONS)}", name="ck_messages_cancel_reason"
        ),
        CheckConstraint("sequence >= 1 AND attempts_in_cycle >= 0 AND size_bytes >= 0", name="ck_messages_counts"),
        # El worker toma pendientes y reintentos vencidos.
        Index("ix_messages_status_next_attempt", "status", "next_attempt_at"),
        # Detecta bloqueos vencidos en sending.
        Index("ix_messages_status_locked_until", "status", "locked_until"),
        # Plazos de aviso (2 días) y cancelación (3 días) de fallidos e inciertos.
        Index("ix_messages_status_last_attempt", "status", "last_attempt_at"),
        # Progreso de un envío (conteo por estado).
        Index("ix_messages_dispatch_status", "dispatch_id", "status"),
    )

    company_id: Mapped[str] = mapped_column(String(36))
    dispatch_id: Mapped[str] = mapped_column(ForeignKey("dispatches.id"))
    sequence: Mapped[int] = mapped_column(Integer)  # Orden dentro del envío, desde 1.
    consumer_reference: Mapped[str | None] = mapped_column(String(100))  # P. ej. código del proveedor.
    # Listas finales de direcciones (máx. 50 entre las tres, se valida al crear).
    to_addresses: Mapped[list] = mapped_column(JSON)
    cc_addresses: Mapped[list] = mapped_column(JSON, default=list)
    bcc_addresses: Mapped[list] = mapped_column(JSON, default=list)
    reply_to: Mapped[str | None] = mapped_column(String(320))
    subject: Mapped[str] = mapped_column(String(998))  # Límite de línea de RFC 5322.
    body_html: Mapped[str | None] = mapped_column(Text)
    body_text: Mapped[str | None] = mapped_column(Text)
    # Message-ID generado al crear e igual en cada intento: el destinatario puede
    # reconocer un duplicado si un incierto se reprocesa.
    message_id_header: Mapped[str] = mapped_column(String(255))
    size_bytes: Mapped[int] = mapped_column(Integer)  # Tamaño MIME final (límite 25 MB).
    # Plantilla con la que se armó (NULL si el consumidor envió el contenido armado).
    template_id: Mapped[str | None] = mapped_column(ForeignKey("templates.id"))

    status: Mapped[str] = mapped_column(String(20), default="pending")
    attempts_in_cycle: Mapped[int] = mapped_column(Integer, default=0)  # Se reinicia al reprocesar.
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_by: Mapped[str | None] = mapped_column(String(100))  # Id del proceso worker.
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notice_dispatch_id: Mapped[str | None] = mapped_column(ForeignKey("dispatches.id"))  # Aviso que ya lo incluyó.
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_reason: Mapped[str | None] = mapped_column(String(20))


class MessageAttachment(AuditMixin, Base):
    """Adjunto de un mensaje. content se carga solo al pedirlo (deferred): los
    listados no leen los bytes.

    Purga (acuerdo 5): cuando el mensaje queda sent o cancelled, content pasa a
    NULL y se fija content_purged_at. La fila y sus metadatos se conservan; no
    es un borrado de fila.
    """

    __tablename__ = "message_attachments"
    __table_args__ = (
        UniqueConstraint("message_id", "sequence", name="uq_message_attachments_message_sequence"),
        CheckConstraint("sequence >= 1 AND size_bytes >= 0", name="ck_message_attachments_counts"),
        CheckConstraint(
            "(content IS NULL AND content_purged_at IS NOT NULL)"
            " OR (content IS NOT NULL AND content_purged_at IS NULL)",
            name="ck_message_attachments_purge",
        ),
    )

    company_id: Mapped[str] = mapped_column(String(36))
    message_id: Mapped[str] = mapped_column(ForeignKey("messages.id"))
    sequence: Mapped[int] = mapped_column(Integer)
    filename: Mapped[str] = mapped_column(String(255))  # Ya saneado (sin rutas ni controles).
    content_type: Mapped[str] = mapped_column(String(100))  # Validado por contenido.
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    content: Mapped[bytes | None] = mapped_column(LargeBinary, deferred=True)
    content_purged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MessageAttempt(AuditMixin, Base):
    """Solo anexado: una fila por cada cuenta probada en cada intento.

    Si la cuenta 1 falla antes de que el servidor acepte el mensaje y la 2 lo
    envía, quedan dos filas con el mismo attempt_number. created_by es el actor
    notificaciones.worker. smtp_response solo lo ve notifications.admin.
    """

    __tablename__ = "message_attempts"
    __table_args__ = (
        CheckConstraint(_in("outcome", ATTEMPT_OUTCOMES), name="ck_message_attempts_outcome"),
        CheckConstraint("attempt_number >= 1", name="ck_message_attempts_number"),
        Index("ix_message_attempts_message_number", "message_id", "attempt_number"),
    )

    company_id: Mapped[str] = mapped_column(String(36))
    message_id: Mapped[str] = mapped_column(ForeignKey("messages.id"))
    attempt_number: Mapped[int] = mapped_column(Integer)  # Acumulado del mensaje.
    smtp_account_id: Mapped[str | None] = mapped_column(ForeignKey("smtp_accounts.id"))  # NULL: no había cuenta.
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    outcome: Mapped[str] = mapped_column(String(20))
    smtp_code: Mapped[int | None] = mapped_column(Integer)
    error_kind: Mapped[str | None] = mapped_column(String(100))  # Categoría, sin texto sensible.
    smtp_response: Mapped[str | None] = mapped_column(String(500))  # Truncada.


event.listen(MessageAttempt, "before_update", reject_change)
event.listen(MessageAttempt, "before_delete", reject_change)
