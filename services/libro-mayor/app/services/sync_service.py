"""Sincronización de líneas desde SAP.

Flujo:
1. Se registra una ejecución "pending", sin consultar SAP:
   - request(): a mano (POST /sync-runs, kind=sync, rango de contabilización).
   - enqueue_scheduled(): el worker en cada turno de SYNC_SCHEDULE, una por
     cuenta activa: kind=initial si la cuenta nunca completó un initial/delta,
     kind=delta desde su marca de agua si ya lo hizo.
2. El worker (app/worker.py) la toma (claim_next) y la procesa (process): por
   cada día (sync/initial) o de una vez (delta) consulta SAP y guarda sus
   líneas + el avance en UNA transacción. Un fallo deja registrado hasta dónde
   llegó.
3. Repetir no duplica: la clave SAP (company_id, transaccion_id, linea)
   identifica cada línea; si ya existe y SAP la cambió, se actualiza; si es
   igual, no se toca. Por eso el delta puede releer días ya leídos.

Marca de agua de una cuenta: date_to del último initial o delta correcto (el
día SAP en que se creó). El siguiente delta relee desde ese día inclusive,
así no se pierden cambios hechos ese día después de la lectura anterior. Un
sync manual no la mueve: solo cubre su rango de contabilización.

Las líneas se guardan tal como vienen de SAP (acuerdo): sin corregir textos,
signos ni centros de costo vacíos. Cada línea nueva o cambiada se clasifica al
guardarse con las reglas activas en ese momento (classifier.py); si las
reglas cambian después, lo corrige la reclasificación.
"""

import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from platform_audit import current_trace_id, step
from sqlalchemy import exists, func, select
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.common.mixin_model import utcnow
from app.models.entities import Account, LedgerLine, SapCompany, SyncRun
from app.sap.connection import sap_enabled
from app.sap.ledger_reader import AccountFilter, SapLedgerReader
from app.services.account_service import has_open_run
from app.services.actors import SCHEDULER, system_actor_id, user_actor_id
from app.services.classifier import classify, load_rules
from app.services.errors import ConflictError, InvalidDataError, NotFoundError
from app.services.sap_company_service import active_sap_company

logger = logging.getLogger("libro_mayor.sync")

# Actor de los cambios que hace el worker (líneas y estado de ejecuciones).
WORKER = "libro-mayor.worker"


class SapDataError(Exception):
    """Una fila de SAP no cumple el contrato (tipo, vacío o largo). El mensaje es apto para mostrar."""


# --- Conversión fila SAP → valores de LedgerLine ---------------------------


def _required(value, column: str):
    if value is None or (isinstance(value, str) and not value.strip()):
        raise SapDataError(f"SAP devolvió {column} vacío.")
    return value


def _to_int(value, column):
    try:
        return int(_required(value, column))
    except (TypeError, ValueError):
        raise SapDataError(f"SAP devolvió {column} no numérico.") from None


def _to_decimal(value, column):
    try:
        return Decimal(str(_required(value, column)))
    except InvalidOperation:
        raise SapDataError(f"SAP devolvió {column} no numérico.") from None


def _to_date(value, column):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        raise SapDataError(f"SAP devolvió {column} con fecha inválida.") from None


def _to_datetime(value, column):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        raise SapDataError(f"SAP devolvió {column} con fecha inválida.") from None


def _to_str(value, column):
    return None if value is None else str(value)


# Columna SAP → (atributo de LedgerLine, conversión, obligatoria).
FIELD_MAP = {
    "transaccion_id": ("sap_transaction_id", _to_int, True),
    "linea": ("sap_line", _to_int, True),
    "fecha_contabilizacion": ("posting_date", _to_date, True),
    "fecha_documento": ("document_date", _to_date, False),
    "numero_documento": ("document_number", _to_str, False),
    "transaccion_tipo": ("transaction_type", _to_str, False),
    "folio": ("folio", _to_str, False),
    "tipo_documento": ("document_type", _to_str, False),
    "cuenta_asociada": ("account_code", _to_str, True),
    "nombre_cuenta_asociada": ("account_name", _to_str, False),
    "proveedor": ("supplier", _to_str, False),
    "descripcion": ("description", _to_str, False),
    "comentario_linea": ("line_comment", _to_str, False),
    "cuenta_contrapartida": ("counter_account_code", _to_str, False),
    "nombre_contrapartida": ("counter_account_name", _to_str, False),
    "referencia_1": ("reference_1", _to_str, False),
    "referencia_2": ("reference_2", _to_str, False),
    "referencia_3": ("reference_3", _to_str, False),
    "cargo_abono_ml": ("amount_local", _to_decimal, True),
    "cargo_abono_me": ("amount_foreign", _to_decimal, True),
    "centro_costo": ("cost_center_code", _to_str, False),
    "centro_area": ("cost_center_area", _to_str, False),
    "nombre_area": ("cost_center_name", _to_str, False),
    "fecha_creacion": ("sap_created_at", _to_datetime, False),
    "fecha_actualizacion": ("sap_updated_at", _to_datetime, False),
}
_COLUMNS = LedgerLine.__table__.columns


def to_line_values(row: dict) -> dict:
    """Convierte una fila de la vista SAP a los valores de LedgerLine, sin corregir su contenido."""
    values = {}
    for sap_column, (attribute, convert, required) in FIELD_MAP.items():
        raw = row.get(sap_column)
        value = convert(_required(raw, sap_column) if required else raw, sap_column)
        max_length = getattr(_COLUMNS[attribute].type, "length", None)
        if max_length and isinstance(value, str) and len(value) > max_length:
            raise SapDataError(f"SAP devolvió {sap_column} de {len(value)} caracteres (máximo {max_length}).")
        values[attribute] = value
    return values


# --- Solicitud (HTTP) ------------------------------------------------------


class SyncService:
    def __init__(self, db: Session):
        self.db = db

    def request(self, *, company_id: str, user_id: str, account_id: str, date_from: date, date_to: date) -> SyncRun:
        days = (date_to - date_from).days + 1
        if days < 1:
            raise InvalidDataError("date_to no puede ser anterior a date_from.")
        if days > settings.SYNC_MAX_DAYS:
            raise InvalidDataError(f"El rango no puede superar {settings.SYNC_MAX_DAYS} días.")
        if date_to > sap_today():
            raise InvalidDataError("date_to no puede ser una fecha futura (día de SAP).")
        if not sap_enabled():
            raise ConflictError("SAP no está configurado en este servicio (SAP_HOST).")

        try:
            with step("sync_run.create"), self.db.begin():
                if active_sap_company(self.db, company_id) is None:
                    raise ConflictError("La empresa no tiene compañía SAP configurada.")
                account = self.db.scalar(
                    select(Account).where(
                        Account.id == account_id, Account.company_id == company_id, Account.is_active.is_(True)
                    )
                )
                if account is None:
                    raise NotFoundError("Cuenta no encontrada.")
                if has_open_run(self.db, account_id):
                    raise ConflictError("La cuenta ya tiene una sincronización pendiente o en curso.")
                actor_id = user_actor_id(self.db, user_id)
                run = SyncRun(
                    company_id=company_id, account_id=account_id, kind="sync", origin="manual", status="pending",
                    date_from=date_from, date_to=date_to, days_total=days, trace_id=current_trace_id(),
                    created_at=utcnow(), created_by=actor_id,
                )
                self.db.add(run)
        except IntegrityError:
            # Dos solicitudes a la vez: el índice único de ejecuciones abiertas rechaza la segunda.
            raise ConflictError("La cuenta ya tiene una sincronización pendiente o en curso.") from None
        return run

    def get(self, company_id: str, run_id: str) -> SyncRun:
        with self.db.begin():
            run = self.db.scalar(select(SyncRun).where(SyncRun.id == run_id, SyncRun.company_id == company_id))
        if run is None:
            raise NotFoundError("Ejecución no encontrada.")
        return run

    def list(
        self, company_id: str, *, account_id: str | None, status: str | None, limit: int, offset: int
    ) -> list[SyncRun]:
        with self.db.begin():
            query = select(SyncRun).where(SyncRun.company_id == company_id)
            if account_id:
                query = query.where(SyncRun.account_id == account_id)
            if status:
                query = query.where(SyncRun.status == status)
            query = query.order_by(SyncRun.created_at.desc()).limit(limit).offset(offset)
            return list(self.db.scalars(query))


# --- Horario y marca de agua (worker) -------------------------------------


def sap_today() -> date:
    """Hoy según la zona horaria del servidor SAP (SAP_TIMEZONE)."""
    return utcnow().astimezone(settings.sap_zone).date()


def current_slot(now: datetime) -> datetime | None:
    """Último turno de SYNC_SCHEDULE que ya pasó (en UTC); None sin horario.

    Antes del primer turno del día, el último turno es el de ayer.
    """
    times = settings.schedule_times
    if not times:
        return None
    zone = settings.sap_zone
    local = now.astimezone(zone)
    past = [datetime.combine(local.date(), t, zone) for t in times]
    past = [slot for slot in past if slot <= local]
    slot = past[-1] if past else datetime.combine(local.date() - timedelta(days=1), times[-1], zone)
    return slot.astimezone(timezone.utc)


def watermark(db: Session, account_id: str) -> date | None:
    """Día SAP desde el que el próximo delta debe leer; None si nunca completó initial/delta."""
    return db.scalar(
        select(func.max(SyncRun.date_to)).where(
            SyncRun.account_id == account_id,
            SyncRun.status == "succeeded",
            SyncRun.kind.in_(("initial", "delta")),
        )
    )


def enqueue_scheduled(db: Session, now: datetime | None = None) -> int:
    """Crea las ejecuciones del turno actual. Devuelve cuántas creó.

    Una por cuenta activa (de empresas con compañía SAP activa) que aún no
    tenga la de este turno. Si la cuenta tiene una abierta (p. ej. una manual),
    espera: en la siguiente vuelta del worker se vuelve a intentar para el
    mismo turno. Varios workers pueden llamarla a la vez: el índice único
    (cuenta, turno) deja crear una sola.
    """
    if not sap_enabled():
        return 0
    now = now or utcnow()
    slot = current_slot(now)
    if slot is None:
        return 0
    created = 0
    with db.begin():
        candidates = db.execute(
            select(Account, SapCompany.sync_start_date)
            .join(SapCompany, (SapCompany.company_id == Account.company_id) & SapCompany.is_active.is_(True))
            .where(
                Account.is_active.is_(True),
                ~exists().where(SyncRun.account_id == Account.id, SyncRun.schedule_slot == slot),
                ~exists().where(SyncRun.account_id == Account.id, SyncRun.status.in_(("pending", "running"))),
            )
        ).all()
        if not candidates:
            return 0
        actor_id = system_actor_id(db, SCHEDULER)
        today = sap_today()
        for account, start_date in candidates:
            since = watermark(db, account.id)
            if since is None:
                kind, date_from, days = "initial", start_date, (today - start_date).days + 1
            else:
                kind, date_from, days = "delta", since, 1
            if days < 1:
                continue  # sync_start_date en el futuro: todavía no hay nada que cargar.
            try:
                with db.begin_nested():  # Si otro worker la creó, solo se deshace esta.
                    db.add(
                        SyncRun(
                            company_id=account.company_id, account_id=account.id, kind=kind, origin="schedule",
                            status="pending", date_from=date_from, date_to=today, days_total=days,
                            schedule_slot=slot, created_at=now, created_by=actor_id,
                        )
                    )
                created += 1
            except IntegrityError:
                pass
    if created:
        logger.info("Turno %s: %s ejecuciones programadas", slot.isoformat(), created)
    return created


# --- Procesamiento (worker) ------------------------------------------------


def mark_stale_runs(db: Session) -> int:
    """Marca fallidas las ejecuciones "running" sin avance reciente (worker caído)."""
    limit = utcnow() - timedelta(minutes=settings.SYNC_STALE_MINUTES)
    with db.begin():
        stale = list(
            db.scalars(
                select(SyncRun)
                .where(SyncRun.status == "running", SyncRun.heartbeat_at < limit)
                .with_for_update(skip_locked=True)
            )
        )
        if stale:
            actor_id = system_actor_id(db, WORKER)
            now = utcnow()
            for run in stale:
                _finish(run, "failed", actor_id, now, "Interrumpida: el worker dejó de avanzar (reintentar).")
    for run in stale:
        logger.warning("Ejecución %s marcada como interrumpida", run.id)
    return len(stale)


def claim_next(db: Session) -> str | None:
    """Toma la ejecución pendiente más antigua y la marca "running".

    skip_locked: si hay varios workers, cada uno toma una distinta sin esperar.
    """
    with db.begin():
        run = db.scalar(
            select(SyncRun)
            .where(SyncRun.status == "pending")
            .order_by(SyncRun.created_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if run is None:
            return None
        now = utcnow()
        run.status = "running"
        run.started_at = run.heartbeat_at = run.updated_at = now
        run.updated_by = system_actor_id(db, WORKER)
        return run.id


def process(db: Session, run_id: str) -> None:
    """Procesa una ejecución ya tomada. Nunca lanza: el resultado queda en la fila."""
    try:
        with db.begin():
            run = db.get(SyncRun, run_id)
            account = db.get(Account, run.account_id)
            sap_company = active_sap_company(db, run.company_id)
            actor_id = system_actor_id(db, WORKER)
            if not account.is_active:
                raise ConflictError("La cuenta fue dada de baja antes de sincronizar.")
            if sap_company is None:
                raise ConflictError("La empresa no tiene compañía SAP activa.")
        reader = SapLedgerReader(sap_company.sap_schema, sap_company.source_view)
        accounts = [AccountFilter(account.code, account.match_mode)]

        for offset in range(run.days_total):  # delta: days_total = 1 (una sola consulta).
            # Consultas a SAP fuera de la transacción local.
            if run.kind == "delta":
                label = f"cambios desde {run.date_from}"
                rows = reader.lines_changed_since(accounts, run.date_from)
            else:
                day = run.date_from + timedelta(days=offset)
                label = str(day)
                rows = reader.lines_by_posting_date(accounts, day, day)
            with db.begin():
                run = db.get(SyncRun, run_id, with_for_update=True, populate_existing=True)
                inserted, updated = _save_rows(db, run, actor_id, rows)
                now = utcnow()
                run.days_done += 1
                run.rows_read += len(rows)
                run.rows_inserted += inserted
                run.rows_updated += updated
                run.heartbeat_at = run.updated_at = now
                run.updated_by = actor_id
            logger.info("Ejecución %s (%s): %s leídas, %s nuevas, %s actualizadas", run_id, label, len(rows), inserted, updated)

        with db.begin():
            _finish(db.get(SyncRun, run_id), "succeeded", actor_id, utcnow())
        logger.info("Ejecución %s terminada", run_id)
    except Exception as exc:  # noqa: BLE001 - cualquier fallo termina la ejecución como fallida.
        db.rollback()
        message = safe_message(exc)
        # Solo el mensaje seguro: el texto crudo de una excepción puede traer datos
        # o credenciales (regla de logs: de las excepciones, solo el tipo).
        logger.error("Ejecución %s fallida: %s", run_id, message)
        with db.begin():
            _finish(db.get(SyncRun, run_id), "failed", system_actor_id(db, WORKER), utcnow(), message)


def _save_rows(db: Session, run: SyncRun, actor_id: str, rows: list[dict]) -> tuple[int, int]:
    """Inserta o actualiza las líneas leídas de SAP y las clasifica. Devuelve (insertadas, actualizadas).

    "actualizadas" cuenta cambios de datos de SAP. Si solo cambia la
    clasificación (las reglas cambiaron desde la última vez), se corrige sin
    contarla como actualización de SAP.
    """
    values = [to_line_values(row) for row in rows]
    keys = [(v["sap_transaction_id"], v["sap_line"]) for v in values]
    if len(set(keys)) != len(keys):
        raise SapDataError("SAP devolvió líneas repetidas (transaccion_id, linea) en una misma consulta.")

    existing: dict[tuple[int, int], LedgerLine] = {}
    transaction_ids = sorted({key[0] for key in keys})
    for start in range(0, len(transaction_ids), 1000):  # SQL Server admite ~2100 parámetros por consulta.
        chunk = transaction_ids[start : start + 1000]
        for line in db.scalars(
            select(LedgerLine).where(LedgerLine.company_id == run.company_id, LedgerLine.sap_transaction_id.in_(chunk))
        ):
            existing[(line.sap_transaction_id, line.sap_line)] = line

    now = utcnow()
    rules = load_rules(db, run.company_id)  # Reglas vigentes en esta transacción.
    inserted = updated = 0
    for key, line_values in zip(keys, values):
        rule_id = classify(line_values, rules)
        line = existing.get(key)
        if line is None:
            db.add(
                LedgerLine(
                    company_id=run.company_id, account_id=run.account_id, last_sync_run_id=run.id,
                    rule_id=rule_id, classified_at=now, created_at=now, created_by=actor_id, **line_values,
                )
            )
            inserted += 1
            continue
        changes = {name: value for name, value in line_values.items() if getattr(line, name) != value}
        if line.account_id != run.account_id:  # La trajo otra cuenta registrada (p. ej. un prefijo dado de baja).
            changes["account_id"] = run.account_id
        if changes:
            updated += 1
            line.last_sync_run_id = run.id
        if line.rule_id != rule_id:
            changes["rule_id"] = rule_id
            line.classified_at = now
        if changes:
            for name, value in changes.items():
                setattr(line, name, value)
            line.updated_at = now
            line.updated_by = actor_id
    return inserted, updated


def _finish(run: SyncRun, status: str, actor_id: str, now: datetime, error: str | None = None) -> None:
    run.status = status
    run.finished_at = run.updated_at = now
    run.updated_by = actor_id
    run.safe_error = error[:500] if error else None


def safe_message(exc: Exception) -> str:
    """Mensaje para la fila de la ejecución y el log: sin SQL, credenciales ni datos.

    Errores propios: su mensaje (ya pensado para mostrarse). Errores del driver:
    tipo y código numérico (p. ej. hdbcli -10709 = no se pudo conectar),
    suficientes para buscar la causa sin exponer el texto del error.
    """
    if isinstance(exc, (SapDataError, ConflictError, InvalidDataError)):
        return str(exc)
    if isinstance(exc, DBAPIError):
        code = getattr(exc.orig, "errorcode", None) or getattr(exc.orig, "sqlstate", None)
        suffix = f", código {code}" if code else ""
        return f"Error de base de datos o de SAP ({type(exc.orig).__name__}{suffix})."
    return f"Error inesperado ({type(exc).__name__})."

