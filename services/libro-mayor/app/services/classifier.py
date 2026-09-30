"""Motor de clasificación: decide qué regla clasifica una línea. Función pura.

Lo usan la sincronización, la reclasificación y las consultas en vivo, así una
misma línea se clasifica igual en los tres caminos (determinismo).

Reglas (heredado de proyecto-05, sin tipo_regla):
- Se evalúan por priority y luego id; gana la PRIMERA que cumple.
- Una condición vacía no filtra; todas las llenas deben cumplirse.
- account_code, counter_account_code y cost_center_code: iguales exactos.
- include_text debe aparecer y exclude_text no, sin distinguir mayúsculas, en
  proveedor, descripción o referencias 1–3 (texto tal como viene de SAP).
- amount_min / amount_max: con el importe en moneda local con signo.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import ExpenseRule

# Columnas de la línea donde se buscan los textos (TEXT_SEARCH_COLUMNS de proyecto-05).
TEXT_FIELDS = ("supplier", "description", "reference_1", "reference_2", "reference_3")


@dataclass(frozen=True)
class CompiledRule:
    id: str
    account_code: str | None
    counter_account_code: str | None
    cost_center_code: str | None
    include_text: str | None  # Ya en casefold.
    exclude_text: str | None
    amount_min: Decimal | None
    amount_max: Decimal | None

    def matches(self, line: dict, text: str) -> bool:
        if self.account_code is not None and line.get("account_code") != self.account_code:
            return False
        if self.counter_account_code is not None and line.get("counter_account_code") != self.counter_account_code:
            return False
        if self.cost_center_code is not None and line.get("cost_center_code") != self.cost_center_code:
            return False
        if self.include_text is not None and self.include_text not in text:
            return False
        if self.exclude_text is not None and self.exclude_text in text:
            return False
        amount = line.get("amount_local")
        if self.amount_min is not None and (amount is None or amount < self.amount_min):
            return False
        if self.amount_max is not None and (amount is None or amount > self.amount_max):
            return False
        return True


def _clean(value: str | None) -> str | None:
    """Texto de condición: sin espacios alrededor; vacío = sin condición."""
    if value is None:
        return None
    value = value.strip()
    return value or None


def compile_rules(rules: Iterable[ExpenseRule]) -> list[CompiledRule]:
    """Prepara las reglas activas en el orden de evaluación (priority, id)."""
    rules = list(rules)  # Puede ser un resultado de consulta: solo se recorre una vez.
    compiled = [
        CompiledRule(
            id=rule.id,
            account_code=_clean(rule.account_code),
            counter_account_code=_clean(rule.counter_account_code),
            cost_center_code=_clean(rule.cost_center_code),
            include_text=(_clean(rule.include_text) or "").casefold() or None,
            exclude_text=(_clean(rule.exclude_text) or "").casefold() or None,
            amount_min=rule.amount_min,
            amount_max=rule.amount_max,
        )
        for rule in rules
        if rule.is_active
    ]
    order = {rule.id: (rule.priority, rule.id) for rule in rules}
    return sorted(compiled, key=lambda r: order[r.id])


FIELDS = ("account_code", "counter_account_code", "cost_center_code", "amount_local", *TEXT_FIELDS)


def line_dict(line) -> dict:
    """Campos que usa classify() tomados de una fila de LedgerLine."""
    return {field: getattr(line, field) for field in FIELDS}


def search_text(line: dict) -> str:
    return " ".join(str(line.get(field) or "") for field in TEXT_FIELDS).casefold()


def classify(line: dict, rules: list[CompiledRule]) -> str | None:
    """Id de la primera regla que cumple la línea, o None (sin clasificar).

    line: valores con los nombres de SapLineColumns (account_code, supplier, …).
    """
    text = search_text(line)
    for rule in rules:
        if rule.matches(line, text):
            return rule.id
    return None


def load_rules(db: Session, company_id: str) -> list[CompiledRule]:
    """Reglas activas de la empresa, listas para classify()."""
    return compile_rules(
        db.scalars(select(ExpenseRule).where(ExpenseRule.company_id == company_id, ExpenseRule.is_active.is_(True)))
    )
