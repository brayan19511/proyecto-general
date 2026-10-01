"""Carga masiva de reglas (POST /rules/import).

Todo en UNA transacción: si una regla no es válida, no se guarda nada.
- Las categorías se indican por nombre (codigo, subcodigo en el JSON). Se busca
  una activa con ese nombre en su nivel (sin distinguir mayúsculas ni espacios
  al inicio o al final); si no existe, se crea.
- mode=replace: da de baja (baja lógica, con historial) todas las reglas
  activas de la empresa y crea las del archivo. Equivale al DELETE + INSERT de
  proyecto-05 sin borrar filas. mode=append: solo agrega.
- Cada regla creada o dada de baja queda en change_history. Al final se
  registra UNA reclasificación de todas las líneas (no una por regla).
- dry_run=true: hace todo y deshace al final; devuelve lo que habría pasado.
"""

import re
from collections import defaultdict
from decimal import Decimal, InvalidOperation

from platform_audit import current_trace_id, step
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.common.mixin_model import utcnow
from app.models.entities import ClassificationRun, ExpenseCategory, ExpenseRule
from app.services.actors import user_actor_id
from app.services.errors import InvalidDataError
from app.services.history import record_change
from app.services.rule_service import CONDITIONS, _normalize, _snapshot

GV_CODE = re.compile(r"\bGV\d{2}\b", re.IGNORECASE)
MAX_ERRORS_SHOWN = 20


def _key(name: str) -> str:
    return name.strip().casefold()


class RuleImportService:
    def __init__(self, db: Session):
        self.db = db

    def run(self, *, company_id: str, user_id: str, mode: str, dry_run: bool, rules: list[dict]) -> dict:
        items = self._validate(rules)
        transaction = self.db.begin()
        try:
            with step("rule.import", f"{len(items)} reglas, mode={mode}, dry_run={dry_run}"):
                result = self._apply(company_id, user_id, mode, items)
            result["dry_run"] = dry_run
            if dry_run:
                transaction.rollback()
                result["classification_run_id"] = None
            else:
                transaction.commit()
        except BaseException:
            transaction.rollback()
            raise
        return result

    def _validate(self, rules: list[dict]) -> list[dict]:
        """Valida todo antes de escribir; junta los errores con su número de fila (1 = primera)."""
        errors, items = [], []
        for index, raw in enumerate(rules, start=1):
            item = dict(raw)
            item["category"] = (item.get("category") or "").strip()
            item["subcategory"] = (item.get("subcategory") or "").strip() or None
            try:
                item.update(_normalize({k: item.get(k) for k in (*CONDITIONS, "report_name")}))
            except InvalidOperation:
                errors.append(f"fila {index}: importe no numérico")
                continue
            if not item["category"]:
                errors.append(f"fila {index}: falta codigo")
            if all(item.get(field) is None for field in CONDITIONS):
                errors.append(f"fila {index}: la regla necesita al menos una condición")
            low, high = item.get("amount_min"), item.get("amount_max")
            if isinstance(low, Decimal) and isinstance(high, Decimal) and low > high:
                errors.append(f"fila {index}: amount_min mayor que amount_max")
            items.append(item)
        if errors:
            more = f" (y {len(errors) - MAX_ERRORS_SHOWN} más)" if len(errors) > MAX_ERRORS_SHOWN else ""
            raise InvalidDataError("Reglas inválidas, no se guardó nada: " + "; ".join(errors[:MAX_ERRORS_SHOWN]) + more)
        return items

    def _apply(self, company_id: str, user_id: str, mode: str, items: list[dict]) -> dict:
        actor_id = user_actor_id(self.db, user_id)
        now = utcnow()
        categories = list(
            self.db.scalars(
                select(ExpenseCategory).where(ExpenseCategory.company_id == company_id, ExpenseCategory.is_active.is_(True))
            )
        )
        tops = {_key(c.name): c for c in categories if c.parent_id is None}
        subs = {(c.parent_id, _key(c.name)): c for c in categories if c.parent_id is not None}
        created_categories = []

        def create(name: str, parent: ExpenseCategory | None) -> ExpenseCategory:
            category = ExpenseCategory(
                company_id=company_id, parent_id=parent.id if parent else None, name=name,
                created_at=now, created_by=actor_id,
            )
            self.db.add(category)
            self.db.flush()
            record_change(
                self.db, action="category.create", resource_type="category", resource_id=category.id,
                company_id=company_id, actor_id=actor_id, now=now, before={},
                after={"name": name, "parent_id": category.parent_id},
            )
            created_categories.append({"name": name, "parent": parent.name if parent else None})
            return category

        deactivated = 0
        if mode == "replace":
            for rule in self.db.scalars(
                select(ExpenseRule)
                .where(ExpenseRule.company_id == company_id, ExpenseRule.is_active.is_(True))
                .with_for_update()
            ):
                rule.is_active = False
                rule.deleted_at = rule.updated_at = now
                rule.deleted_by = rule.updated_by = actor_id
                record_change(
                    self.db, action="rule.delete", resource_type="rule", resource_id=rule.id,
                    company_id=company_id, actor_id=actor_id, now=now, before=_snapshot(rule), after={},
                )
                deactivated += 1

        for item in items:
            top = tops.get(_key(item["category"]))
            if top is None:
                top = tops[_key(item["category"])] = create(item["category"], None)
            target = top
            if item["subcategory"]:
                target = subs.get((top.id, _key(item["subcategory"])))
                if target is None:
                    target = subs[(top.id, _key(item["subcategory"]))] = create(item["subcategory"], top)
            rule = ExpenseRule(
                company_id=company_id, priority=item["priority"], category_id=target.id,
                report_name=item.get("report_name"), created_at=now, created_by=actor_id,
                **{field: item.get(field) for field in CONDITIONS},
            )
            self.db.add(rule)
            self.db.flush()
            record_change(
                self.db, action="rule.create", resource_type="rule", resource_id=rule.id,
                company_id=company_id, actor_id=actor_id, now=now, before={}, after=_snapshot(rule),
            )

        run = ClassificationRun(
            company_id=company_id, reason="manual", status="pending", trace_id=current_trace_id(),
            created_at=now, created_by=actor_id,
        )
        self.db.add(run)
        self.db.flush()
        return {
            "mode": mode,
            "rules_created": len(items),
            "rules_deactivated": deactivated,
            "categories_created": created_categories,
            "warnings": _warnings(items, tops),
            "classification_run_id": run.id,
        }


def _warnings(items: list[dict], tops: dict) -> list[str]:
    """Avisos de datos (no impiden importar): nombres casi iguales y reglas repetidas."""
    warnings = []
    names = {top.name for top in tops.values()}
    without_code = defaultdict(set)
    for name in names:
        without_code[GV_CODE.sub("", name).strip().casefold()].add(name)
    for group in without_code.values():
        if len(group) > 1:
            warnings.append("Categorías que parecen la misma (difieren en el código GV): " + " / ".join(sorted(group)))
    spaced = defaultdict(set)
    for item in items:
        for name in filter(None, (item["category"], item["subcategory"])):
            spaced[" ".join(name.split()).casefold()].add(name)
    for group in spaced.values():
        if len(group) > 1:
            warnings.append("Nombres que solo difieren en espacios (quedan como categorías distintas): "
                            + " / ".join(repr(n) for n in sorted(group)))
    seen = defaultdict(list)
    for index, item in enumerate(items, start=1):
        key = tuple(str(item.get(field)) for field in (*CONDITIONS, "priority"))
        seen[key].append(index)
    for rows in seen.values():
        if len(rows) > 1:
            warnings.append(f"Reglas con las mismas condiciones y prioridad (gana la primera): filas {rows}")
    return warnings
