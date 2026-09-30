"""Reclasificación de líneas sincronizadas (libro_mayor.classification_runs).

No consulta SAP: recalcula rule_id de ledger_lines con las reglas activas.
- rule_change (lo registra rule_service): líneas candidatas de una regla =
  las que hoy tienen esa regla (pueden dejar de cumplirla o la regla se dio de
  baja) + las que podrían cumplir sus condiciones actuales (pueden pasar a
  ella). Las demás no cambian: su primera regla que cumple sigue siendo la misma.
- manual (POST /classification-runs): todas las líneas de la empresa o las de
  un rango de fechas de contabilización. Sirve para clasificar lo sincronizado
  antes de tener reglas.
El worker avanza por lotes ordenados por id (CLASSIFY_BATCH_SIZE), con commit
y avance por lote: un fallo deja hecho lo anterior y se puede repetir.
"""

import logging
from datetime import date, timedelta

from platform_audit import current_trace_id, step
from sqlalchemy import and_, or_, select, true
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.common.mixin_model import utcnow
from app.models.entities import ClassificationRun, ExpenseRule, LedgerLine
from app.services.actors import system_actor_id, user_actor_id
from app.services.classifier import classify, line_dict, load_rules
from app.services.errors import InvalidDataError, NotFoundError

logger = logging.getLogger("libro_mayor.classification")
WORKER = "libro-mayor.worker"


class ClassificationService:
    def __init__(self, db: Session):
        self.db = db

    def request(self, *, company_id: str, user_id: str, date_from: date | None, date_to: date | None) -> ClassificationRun:
        if (date_from is None) != (date_to is None):
            raise InvalidDataError("date_from y date_to van juntos (o ninguno: todas las líneas).")
        if date_from is not None and date_to < date_from:
            raise InvalidDataError("date_to no puede ser anterior a date_from.")
        with step("classification_run.create"), self.db.begin():
            actor_id = user_actor_id(self.db, user_id)
            run = ClassificationRun(
                company_id=company_id, reason="manual", status="pending", date_from=date_from, date_to=date_to,
                trace_id=current_trace_id(), created_at=utcnow(), created_by=actor_id,
            )
            self.db.add(run)
        return run

    def get(self, company_id: str, run_id: str) -> ClassificationRun:
        with self.db.begin():
            run = self.db.scalar(
                select(ClassificationRun).where(ClassificationRun.id == run_id, ClassificationRun.company_id == company_id)
            )
        if run is None:
            raise NotFoundError("Reclasificación no encontrada.")
        return run

    def list(self, company_id: str, *, limit: int, offset: int) -> list[ClassificationRun]:
        with self.db.begin():
            return list(
                self.db.scalars(
                    select(ClassificationRun)
                    .where(ClassificationRun.company_id == company_id)
                    .order_by(ClassificationRun.created_at.desc())
                    .limit(limit)
                    .offset(offset)
                )
            )


# --- Worker ----------------------------------------------------------------


def mark_stale(db: Session) -> None:
    limit = utcnow() - timedelta(minutes=settings.SYNC_STALE_MINUTES)
    with db.begin():
        for run in db.scalars(
            select(ClassificationRun)
            .where(ClassificationRun.status == "running", ClassificationRun.heartbeat_at < limit)
            .with_for_update(skip_locked=True)
        ):
            _finish(run, "failed", system_actor_id(db, WORKER), "Interrumpida: el worker dejó de avanzar (reintentar).")
            logger.warning("Reclasificación %s marcada como interrumpida", run.id)


def claim_next(db: Session) -> str | None:
    with db.begin():
        run = db.scalar(
            select(ClassificationRun)
            .where(ClassificationRun.status == "pending")
            .order_by(ClassificationRun.created_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if run is None:
            return None
        run.status = "running"
        run.started_at = run.heartbeat_at = run.updated_at = utcnow()
        run.updated_by = system_actor_id(db, WORKER)
        return run.id


def process(db: Session, run_id: str) -> None:
    """Procesa una reclasificación ya tomada. Nunca lanza: el resultado queda en la fila."""
    try:
        with db.begin():
            run = db.get(ClassificationRun, run_id)
            actor_id = system_actor_id(db, WORKER)
            scope = _scope(db, run)
        while True:
            with db.begin():
                run = db.get(ClassificationRun, run_id, with_for_update=True, populate_existing=True)
                rules = load_rules(db, run.company_id)  # Reglas vigentes en cada lote.
                query = select(LedgerLine).where(LedgerLine.company_id == run.company_id, scope)
                if run.last_line_id is not None:
                    query = query.where(LedgerLine.id > run.last_line_id)
                lines = list(db.scalars(query.order_by(LedgerLine.id).limit(settings.CLASSIFY_BATCH_SIZE)))
                now = utcnow()
                if not lines:
                    _finish(run, "succeeded", actor_id)
                    break
                changed = 0
                for line in lines:
                    rule_id = classify(line_dict(line), rules)
                    if rule_id != line.rule_id:
                        line.rule_id = rule_id
                        line.classified_at = line.updated_at = now
                        line.updated_by = actor_id
                        changed += 1
                run.rows_checked += len(lines)
                run.rows_changed += changed
                run.last_line_id = lines[-1].id
                run.heartbeat_at = run.updated_at = now
                run.updated_by = actor_id
        logger.info("Reclasificación %s terminada: %s revisadas, %s cambiadas", run_id, run.rows_checked, run.rows_changed)
    except Exception as exc:  # noqa: BLE001 - cualquier fallo termina la reclasificación como fallida.
        db.rollback()
        message = f"Error inesperado ({type(exc).__name__})."  # Solo el tipo: el texto puede traer datos.
        logger.error("Reclasificación %s fallida: %s", run_id, message)
        with db.begin():
            _finish(db.get(ClassificationRun, run_id), "failed", system_actor_id(db, WORKER), message)


def _scope(db: Session, run: ClassificationRun):
    """Condición SQL de las líneas a revisar (además de la empresa)."""
    if run.reason == "manual":
        if run.date_from is None:
            return true()
        return LedgerLine.posting_date.between(run.date_from, run.date_to)

    rule = db.get(ExpenseRule, run.rule_id)
    had_rule = LedgerLine.rule_id == rule.id
    if not rule.is_active:
        return had_rule
    # Prefiltro SQL con las condiciones exactas y de importe; los textos los
    # evalúa classify() en Python (búsqueda sin mayúsculas portable).
    conditions = []
    for field in ("account_code", "counter_account_code", "cost_center_code"):
        value = getattr(rule, field)
        if value is not None:
            conditions.append(getattr(LedgerLine, field) == value)
    if rule.amount_min is not None:
        conditions.append(LedgerLine.amount_local >= rule.amount_min)
    if rule.amount_max is not None:
        conditions.append(LedgerLine.amount_local <= rule.amount_max)
    may_match = and_(*conditions) if conditions else true()
    return or_(had_rule, may_match)


def _finish(run: ClassificationRun, status: str, actor_id: str, error: str | None = None) -> None:
    now = utcnow()
    run.status = status
    run.finished_at = run.updated_at = now
    run.updated_by = actor_id
    run.safe_error = error[:500] if error else None
