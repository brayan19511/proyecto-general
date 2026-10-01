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

# Nombres de proyecto-05 (acuerdo): codigo = categoría, subcodigo = subcategoría,
# nombre_cuenta = nombre de la línea en reportes.
UNCLASSIFIED = {"codigo": None, "subcodigo": None, "nombre_cuenta": None}


def describe_rules(db: Session, rule_ids: set[str]) -> dict[str, dict]:
    """rule_id → codigo, subcodigo y nombre_cuenta de la regla (incluye reglas ya dadas de baja)."""
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
            "codigo": top.name,
            "subcodigo": sub.name if sub else None,
            "nombre_cuenta": rule.report_name,
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


def supplier_or_none(supplier: str | None) -> str | None:
    """Proveedor para agrupar: NULL y texto vacío de SAP cuentan como "sin proveedor".

    Solo afecta a la salida del resumen; el dato guardado no se modifica.
    """
    return supplier if supplier and supplier.strip() else None


def build_summary(partial: dict, described: dict[str, dict], *, by_supplier: bool = False) -> list[dict]:
    """Totales por año, mes, codigo y subcodigo (sin regla = codigo null).

    Con by_supplier las claves parciales traen el proveedor como cuarto
    elemento, (año, mes, regla, proveedor), y cada fila de salida incluye
    "supplier" (null = sin proveedor).
    """
    totals = defaultdict(lambda: {"lines": 0, "amount_local": Decimal(0), "amount_foreign": Decimal(0)})
    for partial_key, (count, local, foreign) in partial.items():
        year, month, rule_id = partial_key[:3]
        info = described.get(rule_id, UNCLASSIFIED)
        key = (year, month, info["codigo"], info["subcodigo"])
        if by_supplier:
            key += (supplier_or_none(partial_key[3]),)
        totals[key]["lines"] += count
        totals[key]["amount_local"] += local
        totals[key]["amount_foreign"] += foreign

    rows = []
    for key, values in sorted(totals.items(), key=lambda item: tuple(v or "" for v in item[0])):
        row = {"year": key[0], "month": key[1], "codigo": key[2], "subcodigo": key[3], **values}
        if by_supplier:
            row["supplier"] = key[4]
        rows.append(row)
    return rows
