from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Numeric,
    String,
    UniqueConstraint,
    event,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.models.common.mixin_model import AuditMixin


class Base(DeclarativeBase):
    """Base de los modelos del servicio. Todas sus tablas van en el schema libro_mayor.

    El schema se declara una sola vez aquí; los modelos lo heredan. Declararlo
    no lo crea en la base: lo crea migrations/env.py antes de migrar.
    """

    metadata = MetaData(schema="libro_mayor")


class Actor(AuditMixin, Base):
    """Quién realizó una acción en este servicio.

    - user: subject_ref = id del usuario validado por auth (sin FK a auth).
    - system: subject_ref = nombre estable del proceso, p. ej.
      "libro-mayor.scheduler" (sincronización programada).
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


class SapCompany(AuditMixin, Base):
    """Empresa de la plataforma → compañía SAP (base/schema SBO en HANA).

    company_id es el UUID de la empresa en auth (sin FK: auth es otro
    servicio). sap_schema se usará como identificador SQL al consultar HANA:
    el código lo valida (solo letras, dígitos y _) antes de guardarlo y nunca
    lo toma de una solicitud de consulta. Las credenciales HANA no van aquí,
    sino en la configuración del despliegue.

    Una empresa tiene una sola compañía SAP activa, y una compañía SAP
    pertenece a una sola empresa: así no se mezclan datos entre empresas.
    """

    __tablename__ = "sap_companies"
    __table_args__ = (
        unique_active("uq_sap_companies_company_active", "company_id"),
        unique_active("uq_sap_companies_schema_active", "sap_schema"),
    )

    company_id: Mapped[str] = mapped_column(String(36))
    sap_schema: Mapped[str] = mapped_column(String(128))  # p. ej. SBO_RASH_PRODUCCION
    source_view: Mapped[str] = mapped_column(String(128))  # p. ej. VW_LIBRO_MAYOR_PERSONALIZADO_2
    # Desde qué fecha contable se hace la primera carga de cada cuenta.
    sync_start_date: Mapped[date] = mapped_column(Date)


class Account(AuditMixin, Base):
    """Cuenta (o grupo de cuentas) de SAP que se sincroniza para una empresa.

    - exact: una cuenta concreta, p. ej. 979005400.
    - prefix: todas las que empiezan así, p. ej. 95 (95%).

    Superposición (prohibida, se valida en el servicio al registrar): dos
    cuentas activas de la misma empresa no pueden cubrir una misma cuenta SAP,
    p. ej. prefijo 97 y exacta 979005400. Así cada línea pertenece a una sola
    cuenta registrada. La base solo garantiza que no se repita el mismo code.
    """

    __tablename__ = "accounts"
    __table_args__ = (
        unique_active("uq_accounts_company_code_active", "company_id", "code"),
        CheckConstraint("match_mode IN ('exact', 'prefix')", name="ck_accounts_match_mode"),
    )

    company_id: Mapped[str] = mapped_column(String(36))
    code: Mapped[str] = mapped_column(String(20))
    match_mode: Mapped[str] = mapped_column(String(10))
    # Nombre de referencia (p. ej. "UTILES DE ESCRITORIO"); el de cada línea viene de SAP.
    name: Mapped[str | None] = mapped_column(String(150))


class ChangeHistory(AuditMixin, Base):
    """Historial de negocio, de solo anexado: una fila por cambio.

    El responsable y la fecha son created_by / created_at. before/after llevan
    solo los campos permitidos del recurso (nunca secretos ni credenciales).
    Se inserta en la misma transacción que el cambio: si falla, no hay cambio.
    Una corrección es otro evento, no la edición de uno anterior.
    """

    __tablename__ = "change_history"
    __table_args__ = (
        Index("ix_change_history_resource", "resource_type", "resource_id"),
        Index("ix_change_history_company_created", "company_id", "created_at"),
    )

    action: Mapped[str] = mapped_column(String(100))  # p. ej. "account.create"
    resource_type: Mapped[str] = mapped_column(String(50))  # p. ej. "account"
    resource_id: Mapped[str] = mapped_column(String(36))
    # Empresa afectada; NULL solo en cambios que no son de una empresa.
    company_id: Mapped[str | None] = mapped_column(String(36))
    trace_id: Mapped[str | None] = mapped_column(String(36))  # Enlace con audit.logs.
    before: Mapped[dict] = mapped_column(JSON, default=dict)
    after: Mapped[dict] = mapped_column(JSON, default=dict)


def reject_change(*_):
    """Impide modificar o eliminar eventos históricos durante el flush del ORM."""
    raise ValueError("Los eventos históricos son de solo anexado")


# Protege el ciclo habitual del ORM; no protege contra SQL directo.
event.listen(ChangeHistory, "before_update", reject_change)
event.listen(ChangeHistory, "before_delete", reject_change)


SYNC_STATUSES = ("pending", "running", "succeeded", "failed")


class SyncRun(AuditMixin, Base):
    """Una ejecución de sincronización (estado persistente del trabajo).

    kind:
    - sync: rango de fechas de contabilización pedido a mano (POST /sync-runs).
    - initial: primera carga de una cuenta por horario, desde
      sap_companies.sync_start_date hasta hoy (día SAP).
    - delta: líneas creadas o actualizadas en SAP desde date_from (la marca de
      agua) hasta date_to (hoy en SAP al crearla).

    La marca de agua de una cuenta es el date_to del último initial o delta
    correcto; un sync manual no la mueve (cubre solo su rango). La procesa el
    worker; cada día (o el delta completo) se guarda en su propia transacción
    junto con el avance. No es un log técnico: es el estado del trabajo.

    Una cuenta no puede tener dos ejecuciones pendientes o en curso a la vez, ni
    dos del mismo turno del horario (índices únicos filtrados).
    """

    __tablename__ = "sync_runs"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'running', 'succeeded', 'failed')", name="ck_sync_runs_status"),
        CheckConstraint("kind IN ('sync', 'initial', 'delta')", name="ck_sync_runs_kind"),
        CheckConstraint("origin IN ('manual', 'schedule')", name="ck_sync_runs_origin"),
        CheckConstraint("date_to >= date_from", name="ck_sync_runs_range"),
        Index(
            "uq_sync_runs_account_open",
            "account_id",
            unique=True,
            postgresql_where=text("status IN ('pending', 'running')"),
            mssql_where=text("status IN ('pending', 'running')"),
        ),
        Index(
            "uq_sync_runs_account_slot",
            "account_id",
            "schedule_slot",
            unique=True,
            postgresql_where=text("schedule_slot IS NOT NULL"),
            mssql_where=text("schedule_slot IS NOT NULL"),
        ),
        Index("ix_sync_runs_company_created", "company_id", "created_at"),
        Index("ix_sync_runs_status_created", "status", "created_at"),
    )

    company_id: Mapped[str] = mapped_column(String(36))
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"))
    kind: Mapped[str] = mapped_column(String(20), default="sync")
    # manual = POST /sync-runs; schedule = horario del worker (fase C). ("trigger" es
    # palabra reservada en SQL Server.)
    origin: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    # Rango de fechas de contabilización, inclusivo.
    date_from: Mapped[date] = mapped_column(Date)
    date_to: Mapped[date] = mapped_column(Date)
    days_total: Mapped[int] = mapped_column(Integer)
    days_done: Mapped[int] = mapped_column(Integer, default=0)
    rows_read: Mapped[int] = mapped_column(Integer, default=0)
    rows_inserted: Mapped[int] = mapped_column(Integer, default=0)
    rows_updated: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # El worker lo renueva al terminar cada día; si deja de avanzar, la ejecución
    # se considera interrumpida (SYNC_STALE_MINUTES).
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Mensaje apto para mostrar (sin credenciales ni SQL); el detalle va al log del worker.
    safe_error: Mapped[str | None] = mapped_column(String(500))
    trace_id: Mapped[str | None] = mapped_column(String(36))  # Solicitud que la creó.
    # Turno del horario que la creó (UTC); NULL en las manuales.
    schedule_slot: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SapLineColumns:
    """Columnas de una línea tal como la devuelve la vista SAP, sin corregir.

    Separadas de LedgerLine para leerlas en un solo lugar. La correspondencia
    con las columnas de la vista está en FIELD_MAP (app/services/sync_service.py).
    """

    sap_transaction_id: Mapped[int] = mapped_column(BigInteger)  # transaccion_id
    sap_line: Mapped[int] = mapped_column(Integer)  # linea
    posting_date: Mapped[date] = mapped_column(Date)  # fecha_contabilizacion
    document_date: Mapped[date | None] = mapped_column(Date)  # fecha_documento
    document_number: Mapped[str | None] = mapped_column(String(50))  # numero_documento
    transaction_type: Mapped[str | None] = mapped_column(String(50))  # transaccion_tipo
    folio: Mapped[str | None] = mapped_column(String(50))
    document_type: Mapped[str | None] = mapped_column(String(50))  # tipo_documento
    account_code: Mapped[str] = mapped_column(String(50))  # cuenta_asociada
    account_name: Mapped[str | None] = mapped_column(String(150))  # nombre_cuenta_asociada
    supplier: Mapped[str | None] = mapped_column(String(255))  # proveedor
    description: Mapped[str | None] = mapped_column(String(255))  # descripcion
    line_comment: Mapped[str | None] = mapped_column(String(255))  # comentario_linea
    counter_account_code: Mapped[str | None] = mapped_column(String(100))  # cuenta_contrapartida
    counter_account_name: Mapped[str | None] = mapped_column(String(150))  # nombre_contrapartida
    reference_1: Mapped[str | None] = mapped_column(String(200))
    reference_2: Mapped[str | None] = mapped_column(String(200))
    reference_3: Mapped[str | None] = mapped_column(String(200))
    # Con signo, tal como SAP (acuerdo). ML = moneda local; ME = extranjera.
    amount_local: Mapped[Decimal] = mapped_column(Numeric(19, 4))  # cargo_abono_ml
    amount_foreign: Mapped[Decimal] = mapped_column(Numeric(19, 4))  # cargo_abono_me
    cost_center_code: Mapped[str | None] = mapped_column(String(100))  # centro_costo
    cost_center_area: Mapped[str | None] = mapped_column(String(100))  # centro_area
    cost_center_name: Mapped[str | None] = mapped_column(String(100))  # nombre_area
    # Hora de SAP tal como viene (sin zona: hora del servidor SAP).
    sap_created_at: Mapped[datetime | None] = mapped_column(DateTime)  # fecha_creacion
    sap_updated_at: Mapped[datetime | None] = mapped_column(DateTime)  # fecha_actualizacion


class LedgerLine(SapLineColumns, AuditMixin, Base):
    """Línea del libro mayor copiada de SAP, tal como viene (acuerdo), y su clasificación.

    Clave SAP: (company_id, sap_transaction_id, sap_line). Nunca se borra: si
    SAP la cambia, la sincronización actualiza sus datos. created_by /
    updated_by son el actor del worker; last_sync_run_id dice qué ejecución
    la trajo o actualizó por última vez (y por ella, quién la pidió).

    rule_id: regla que la clasifica (NULL = sin clasificar). Es un dato
    derivado: se recalcula al sincronizar y al reprocesar; sin historial por
    línea (el registro es la ejecución de clasificación).
    """

    __tablename__ = "ledger_lines"
    __table_args__ = (
        UniqueConstraint("company_id", "sap_transaction_id", "sap_line", name="uq_ledger_lines_sap_key"),
        Index("ix_ledger_lines_company_posting", "company_id", "posting_date"),
        Index("ix_ledger_lines_account_posting", "account_id", "posting_date"),
        Index("ix_ledger_lines_company_cost_center", "company_id", "cost_center_code"),
        Index("ix_ledger_lines_company_sap_updated", "company_id", "sap_updated_at"),
        Index("ix_ledger_lines_company_rule", "company_id", "rule_id"),
    )

    company_id: Mapped[str] = mapped_column(String(36))
    # Cuenta registrada que la trajo (no la cuenta SAP: esa es account_code).
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"))
    last_sync_run_id: Mapped[str] = mapped_column(ForeignKey("sync_runs.id"))
    rule_id: Mapped[str | None] = mapped_column(ForeignKey("expense_rules.id"))
    classified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ExpenseCategory(AuditMixin, Base):
    """Categoría de gasto de una empresa, en dos niveles (p. ej. GV08 OPERACIONES
    → DIFERENCIA EN UNIDADES DE COSTEO). parent_id NULL = categoría; con
    parent_id = subcategoría de una categoría (no hay tercer nivel).

    El código es único por empresa entre las activas, en ambos niveles. Las
    reglas apuntan a una categoría o subcategoría: renombrarla no obliga a
    reclasificar líneas.
    """

    __tablename__ = "expense_categories"
    __table_args__ = (unique_active("uq_expense_categories_company_code_active", "company_id", "code"),)

    company_id: Mapped[str] = mapped_column(String(36))
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("expense_categories.id"))
    code: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(150))


class ExpenseRule(AuditMixin, Base):
    """Regla de clasificación (antes finance.reglas_gastos).

    Condiciones (vacía = no filtra; todas las llenas deben cumplirse):
    account_code, counter_account_code y cost_center_code son iguales exactos;
    include_text / exclude_text se buscan sin distinguir mayúsculas en
    proveedor, descripción y referencias 1–3; amount_min / amount_max comparan
    el importe en moneda local con signo.
    Se evalúan por priority y luego id: gana la primera que cumple.
    Resultado: category_id y report_name (nombre para reportes; vacío = el
    nombre de la cuenta SAP). Sin tipo_regla (acuerdo).
    """

    __tablename__ = "expense_rules"
    __table_args__ = (
        Index("ix_expense_rules_company_priority", "company_id", "is_active", "priority"),
        CheckConstraint(
            "amount_min IS NULL OR amount_max IS NULL OR amount_min <= amount_max", name="ck_expense_rules_amounts"
        ),
    )

    company_id: Mapped[str] = mapped_column(String(36))
    priority: Mapped[int] = mapped_column(Integer)
    account_code: Mapped[str | None] = mapped_column(String(50))
    counter_account_code: Mapped[str | None] = mapped_column(String(100))
    cost_center_code: Mapped[str | None] = mapped_column(String(100))
    include_text: Mapped[str | None] = mapped_column(String(255))
    exclude_text: Mapped[str | None] = mapped_column(String(255))
    amount_min: Mapped[Decimal | None] = mapped_column(Numeric(19, 4))
    amount_max: Mapped[Decimal | None] = mapped_column(Numeric(19, 4))
    category_id: Mapped[str] = mapped_column(ForeignKey("expense_categories.id"))
    report_name: Mapped[str | None] = mapped_column(String(150))


class ClassificationRun(AuditMixin, Base):
    """Reclasificación de líneas sincronizadas (trabajo del worker; no consulta SAP).

    - reason=rule_change: la crea el alta, edición o baja de una regla; revisa
      solo las líneas candidatas (las que tenían esa regla y las que podrían
      cumplirla ahora).
    - reason=manual: POST /classification-runs; revisa las líneas con fecha de
      contabilización en [date_from, date_to] (o todas si no hay rango).
    Avanza por lotes ordenados por id (last_line_id), con commit por lote.
    """

    __tablename__ = "classification_runs"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'running', 'succeeded', 'failed')", name="ck_classification_runs_status"),
        CheckConstraint("reason IN ('rule_change', 'manual')", name="ck_classification_runs_reason"),
        Index("ix_classification_runs_status_created", "status", "created_at"),
        Index("ix_classification_runs_company_created", "company_id", "created_at"),
    )

    company_id: Mapped[str] = mapped_column(String(36))
    reason: Mapped[str] = mapped_column(String(20))
    rule_id: Mapped[str | None] = mapped_column(ForeignKey("expense_rules.id"))
    date_from: Mapped[date | None] = mapped_column(Date)
    date_to: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    rows_checked: Mapped[int] = mapped_column(Integer, default=0)
    rows_changed: Mapped[int] = mapped_column(Integer, default=0)
    last_line_id: Mapped[str | None] = mapped_column(String(36))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    safe_error: Mapped[str | None] = mapped_column(String(500))
    trace_id: Mapped[str | None] = mapped_column(String(36))
