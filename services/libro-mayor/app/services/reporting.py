"""Presentación de líneas clasificadas: categoría/subcategoría de cada regla y resumen.

Lo usan las consultas en vivo y, más adelante, las consultas sobre
ledger_lines. La clasificación es un rule_id; la categoría se resuelve al leer
(renombrar una categoría no obliga a reclasificar). El resumen se arma sumando
totales parciales por (año, mes, regla): no hace falta tener todas las líneas
en memoria a la vez.
"""

from collections import defaultdict
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import ExpenseCategory, ExpenseRule

UNCLASSIFIED = {
    "category_code": None, "category_name": None, "subcategory_code": None, "subcategory_name": None, "report_name": None,
}


def describe_rules(db: Session, rule_ids: set[str]) -> dict[str, dict]:
    """rule_id → categoría, subcategoría y nombre de reporte (incluye reglas ya dadas de baja)."""
    rule_ids = {rule_id for rule_id in rule_ids if rule_id}
    if not rule_ids:
        return {}
    rules = {r.id: r for r in db.scalars(select(ExpenseRule).where(ExpenseRule.id.in_(rule_ids)))}
    category_ids = {r.category_id for r in rules.values()}
    categories = {c.id: c for c in db.scalars(select(ExpenseCategory).where(ExpenseCategory.id.in_(category_ids)))}
    parent_ids = {c.parent_id for c in categories.values() if c.parent_id} - categories.keys()
    if parent_ids:
        categories.update({c.id: c for c in db.scalars(select(ExpenseCategory).where(ExpenseCategory.id.in_(parent_ids)))})

    described = {}
    for rule_id, rule in rules.items():
        category = categories[rule.category_id]
        parent = categories.get(category.parent_id) if category.parent_id else None
        top, sub = (parent, category) if parent else (category, None)
        described[rule_id] = {
            "category_code": top.code,
            "category_name": top.name,
            "subcategory_code": sub.code if sub else None,
            "subcategory_name": sub.name if sub else None,
            "report_name": rule.report_name,
        }
    return described


def summary_key(line: dict) -> tuple:
    """Clave de agregación parcial: (año, mes, regla)."""
    return line["posting_date"].year, line["posting_date"].month, line.get("rule_id")


def add_to_partial(partial: dict, line: dict) -> None:
    """Suma una línea al total parcial {(año, mes, regla): [líneas, ML, ME]}."""
    totals = partial.setdefault(summary_key(line), [0, Decimal(0), Decimal(0)])
    totals[0] += 1
    totals[1] += line["amount_local"]
    totals[2] += line["amount_foreign"]


def merge_partials(partials: list[dict]) -> dict:
    merged: dict = {}
    for partial in partials:
        for key, (count, local, foreign) in partial.items():
            totals = merged.setdefault(key, [0, Decimal(0), Decimal(0)])
            totals[0] += count
            totals[1] += local
            totals[2] += foreign
    return merged


def build_summary(partial: dict, described: dict[str, dict]) -> list[dict]:
    """Totales por año, mes, categoría y subcategoría (sin regla = categoría null)."""
    totals = defaultdict(lambda: {"lines": 0, "amount_local": Decimal(0), "amount_foreign": Decimal(0)})
    for (year, month, rule_id), (count, local, foreign) in partial.items():
        info = described.get(rule_id, UNCLASSIFIED)
        key = (year, month, info["category_code"], info["category_name"],
               info["subcategory_code"], info["subcategory_name"])
        totals[key]["lines"] += count
        totals[key]["amount_local"] += local
        totals[key]["amount_foreign"] += foreign
    return [
        {"year": k[0], "month": k[1], "category_code": k[2], "category_name": k[3],
         "subcategory_code": k[4], "subcategory_name": k[5], **v}
        for k, v in sorted(totals.items(), key=lambda item: (item[0][0], item[0][1], item[0][2] or "", item[0][4] or ""))
    ]
