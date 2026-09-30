"""Reglas de clasificación (libro_mayor.expense_rules).

Cada alta, edición o baja guarda su historial y registra, en la MISMA
transacción, una reclasificación (classification_runs, reason=rule_change)
que el worker procesa después: el cambio de regla nunca reclasifica dentro
de la solicitud HTTP. Ver app/services/classifier.py para el orden y las
condiciones.
"""

from decimal import Decimal

from platform_audit import current_trace_id, step
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.common.mixin_model import utcnow
from app.models.entities import ClassificationRun, ExpenseCategory, ExpenseRule
from app.services.actors import user_actor_id
from app.services.errors import InvalidDataError, NotFoundError
from app.services.history import record_change

CONDITIONS = (
    "account_code", "counter_account_code", "cost_center_code", "include_text", "exclude_text", "amount_min", "amount_max",
)
TEXT_FIELDS = ("account_code", "counter_account_code", "cost_center_code", "include_text", "exclude_text", "report_name")
EDITABLE = (*CONDITIONS, "priority", "category_id", "report_name")


def _snapshot(rule: ExpenseRule) -> dict:
    data = {field: getattr(rule, field) for field in EDITABLE}
    for field in ("amount_min", "amount_max"):
        if data[field] is not None:
            data[field] = str(data[field])  # JSON sin perder decimales.
    return data


class RuleService:
    def __init__(self, db: Session):
        self.db = db

    def list(self, company_id: str, *, include_inactive: bool = False) -> list[ExpenseRule]:
        """En orden de evaluación: priority y luego id."""
        with self.db.begin():
            query = select(ExpenseRule).where(ExpenseRule.company_id == company_id)
            if not include_inactive:
                query = query.where(ExpenseRule.is_active.is_(True))
            return list(self.db.scalars(query.order_by(ExpenseRule.priority, ExpenseRule.id)))

    def get(self, company_id: str, rule_id: str) -> ExpenseRule:
        with self.db.begin():
            rule = self._find(company_id, rule_id, active_only=False)
        if rule is None:
            raise NotFoundError("Regla no encontrada.")
        return rule

    def create(self, *, company_id: str, user_id: str, values: dict) -> ExpenseRule:
        values = _normalize(values)
        with step("rule.create"), self.db.begin():
            rule = ExpenseRule(company_id=company_id, **{field: values.get(field) for field in EDITABLE})
            self._validate(company_id, rule)
            actor_id = user_actor_id(self.db, user_id)
            now = utcnow()
            rule.created_at, rule.created_by = now, actor_id
            self.db.add(rule)
            self.db.flush()
            record_change(
                self.db, action="rule.create", resource_type="rule", resource_id=rule.id,
                company_id=company_id, actor_id=actor_id, now=now, before={}, after=_snapshot(rule),
            )
            self._enqueue_reclassify(rule, actor_id, now)
        return rule

    def update(self, *, company_id: str, user_id: str, rule_id: str, changes: dict) -> ExpenseRule:
        """Cambia solo los campos enviados; null borra una condición opcional."""
        changes = _normalize(changes)
        with step("rule.update"), self.db.begin():
            rule = self._find(company_id, rule_id, lock=True)
            if rule is None:
                raise NotFoundError("Regla no encontrada.")
            before = _snapshot(rule)
            for field, value in changes.items():
                setattr(rule, field, value)
            self._validate(company_id, rule)
            after = _snapshot(rule)
            if after == before:
                return rule
            actor_id = user_actor_id(self.db, user_id)
            now = utcnow()
            rule.updated_at, rule.updated_by = now, actor_id
            record_change(
                self.db, action="rule.update", resource_type="rule", resource_id=rule.id,
                company_id=company_id, actor_id=actor_id, now=now, before=before, after=after,
            )
            self._enqueue_reclassify(rule, actor_id, now)
        return rule

    def deactivate(self, *, company_id: str, user_id: str, rule_id: str) -> None:
        """Baja lógica; sus líneas se reclasifican con las reglas que quedan."""
        with step("rule.delete"), self.db.begin():
            rule = self._find(company_id, rule_id, lock=True)
            if rule is None:
                raise NotFoundError("Regla no encontrada.")
            actor_id = user_actor_id(self.db, user_id)
            now = utcnow()
            rule.is_active = False
            rule.deleted_at = rule.updated_at = now
            rule.deleted_by = rule.updated_by = actor_id
            record_change(
                self.db, action="rule.delete", resource_type="rule", resource_id=rule.id,
                company_id=company_id, actor_id=actor_id, now=now, before=_snapshot(rule), after={},
            )
            self._enqueue_reclassify(rule, actor_id, now)

    def _validate(self, company_id: str, rule: ExpenseRule) -> None:
        if rule.priority is None:
            raise InvalidDataError("priority es obligatoria.")
        if not rule.category_id:
            raise InvalidDataError("category_id es obligatoria.")
        if all(getattr(rule, field) is None for field in CONDITIONS):
            raise InvalidDataError("La regla necesita al menos una condición.")
        if rule.amount_min is not None and rule.amount_max is not None and rule.amount_min > rule.amount_max:
            raise InvalidDataError("amount_min no puede ser mayor que amount_max.")
        category = self.db.scalar(
            select(ExpenseCategory.id).where(
                ExpenseCategory.id == rule.category_id,
                ExpenseCategory.company_id == company_id,
                ExpenseCategory.is_active.is_(True),
            )
        )
        if category is None:
            raise NotFoundError("Categoría no encontrada.")

    def _enqueue_reclassify(self, rule: ExpenseRule, actor_id: str, now) -> None:
        self.db.add(
            ClassificationRun(
                company_id=rule.company_id, reason="rule_change", rule_id=rule.id, status="pending",
                trace_id=current_trace_id(), created_at=now, created_by=actor_id,
            )
        )

    def _find(self, company_id: str, rule_id: str, active_only: bool = True, lock: bool = False):
        query = select(ExpenseRule).where(ExpenseRule.id == rule_id, ExpenseRule.company_id == company_id)
        if active_only:
            query = query.where(ExpenseRule.is_active.is_(True))
        if lock:
            query = query.with_for_update()
        return self.db.scalar(query)


def _normalize(values: dict) -> dict:
    """Textos sin espacios alrededor; "" = sin condición (None). Importes como Decimal."""
    result = dict(values)
    for field in TEXT_FIELDS:
        if field in result and result[field] is not None:
            result[field] = result[field].strip() or None
    for field in ("amount_min", "amount_max"):
        if result.get(field) is not None:
            result[field] = Decimal(result[field])
    return result
