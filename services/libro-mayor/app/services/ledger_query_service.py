"""Consultas sobre las líneas sincronizadas (libro_mayor.ledger_lines).

A diferencia de la consulta en vivo, no va a SAP ni evalúa reglas: lee la
copia local, ya clasificada (rule_id), con índices por empresa y fecha. Un año
de resumen responde en milisegundos.

Tres salidas con los mismos filtros:
- lines(): JSON paginado (limit/offset) para aplicaciones.
- summary(): totales por año, mes, codigo y subcodigo, y opcionalmente
  proveedor (agregado en SQL).
- iter_csv(): TODO el rango filtrado en CSV, en streaming, para Excel o Power
  BI ("Obtener datos → Desde la web"): no pagina y no carga todo en memoria.

Visibilidad (area_ids): None = toda la empresa (alcance company). Con áreas
(ledger.view de alcance area) solo se ven las líneas cuyos centros de costo
están homologados a esas áreas; las líneas sin centro o sin homologar, no.
Cada línea trae area_id / area_name de su homologación (null si no tiene).
"""

import csv
import io
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import extract, false, func, or_, select
from sqlalchemy.orm import Session

from app.core.db.connection import SessionLocal
from app.models.entities import ExpenseCategory, ExpenseRule, LedgerLine
from app.sap.ledger_reader import AccountFilter
from app.services.cost_center_service import CenterMap, load_center_map, visible_codes
from app.services.errors import InvalidDataError
from app.services.live_query_service import parse_accounts
from app.services.reporting import UNCLASSIFIED, build_summary, describe_rules, supplier_or_none

# Columnas de salida (mismo orden en JSON y CSV).
LINE_FIELDS = (
    "posting_date", "document_date", "document_number", "sap_transaction_id", "sap_line", "transaction_type",
    "folio", "document_type", "account_code", "account_name", "supplier", "description", "line_comment",
    "counter_account_code", "counter_account_name", "reference_1", "reference_2", "reference_3",
    "amount_local", "amount_foreign", "cost_center_code", "cost_center_area", "cost_center_name", "area_id", "area_name",
    "sap_created_at", "sap_updated_at", "rule_id", "codigo", "subcodigo", "nombre_cuenta",
)
CSV_BATCH = 2000


@dataclass(frozen=True)
class LedgerFilters:
    date_from: date
    date_to: date
    accounts: tuple[AccountFilter, ...] = ()  # Vacío = todas.
    codigo: str | None = None
    subcodigo: str | None = None
    cost_center_code: str | None = None
    unclassified: bool | None = None  # True = solo sin regla; False = solo clasificadas.
    # Solo clasificadas cuya regla apunta a una categoría principal (sin subcategoría).
    no_subcodigo: bool = False
    supplier: str | None = None  # Proveedor exacto, tal como viene de SAP.
    no_supplier: bool = False  # Solo líneas sin proveedor (NULL o vacío en SAP).


def classified(line: LedgerLine, described: dict[str, dict], centers: CenterMap) -> dict:
    """Fila de salida: datos de SAP + codigo, subcodigo, nombre_cuenta y área homologada."""
    info = described.get(line.rule_id, UNCLASSIFIED)
    row = {field: getattr(line, field) for field in LINE_FIELDS if hasattr(LedgerLine, field)}
    row.update(info)
    row.update(centers.area(line.cost_center_code))
    row["nombre_cuenta"] = info["nombre_cuenta"] or line.account_name
    return row


class LedgerQueryService:
    def __init__(self, db: Session):
        self.db = db

    def lines(
        self, company_id: str, filters: LedgerFilters, *, area_ids: frozenset[str] | None, limit: int, offset: int
    ) -> dict:
        with self.db.begin():
            centers = load_center_map(self.db, company_id)
            conditions = _conditions(self.db, company_id, filters, area_ids, centers)
            total = self.db.scalar(select(func.count()).select_from(LedgerLine).where(*conditions))
            rows = list(
                self.db.scalars(
                    select(LedgerLine).where(*conditions).order_by(*_ORDER).limit(limit).offset(offset)
                )
            )
            described = describe_rules(self.db, {row.rule_id for row in rows})
        next_offset = offset + len(rows)
        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "next_offset": next_offset if next_offset < total else None,
            "lines": [classified(row, described, centers) for row in rows],
        }

    def summary(
        self, company_id: str, filters: LedgerFilters, *, area_ids: frozenset[str] | None, by_supplier: bool = False
    ) -> list[dict]:
        """Agregado en SQL por (año, mes, regla) y, con by_supplier, también por proveedor."""
        with self.db.begin():
            conditions = _conditions(self.db, company_id, filters, area_ids)
            year = extract("year", LedgerLine.posting_date)
            month = extract("month", LedgerLine.posting_date)
            group = [year, month, LedgerLine.rule_id] + ([LedgerLine.supplier] if by_supplier else [])
            rows = self.db.execute(
                select(*group, func.count(), func.sum(LedgerLine.amount_local), func.sum(LedgerLine.amount_foreign))
                .where(*conditions)
                .group_by(*group)
            ).all()
            partial: dict[tuple, list] = {}
            for row in rows:
                *keys, n, local, foreign = row
                key = (int(keys[0]), int(keys[1]), *keys[2:])
                if by_supplier:
                    # NULL y "" llegan de SQL como grupos distintos: se suman en uno.
                    key = (*key[:3], supplier_or_none(key[3]))
                totals = partial.setdefault(key, [0, Decimal(0), Decimal(0)])
                totals[0] += n
                totals[1] += local or Decimal(0)
                totals[2] += foreign or Decimal(0)
            described = describe_rules(self.db, {key[2] for key in partial})
        return build_summary(partial, described, by_supplier=by_supplier)

    def validate(self, company_id: str, filters: LedgerFilters, *, area_ids: frozenset[str] | None) -> None:
        """Valida los filtros antes de empezar un streaming (después ya no se puede responder 422)."""
        with self.db.begin():
            _conditions(self.db, company_id, filters, area_ids)


def iter_csv(company_id: str, filters: LedgerFilters, delimiter: str, area_ids: frozenset[str] | None) -> Iterator[bytes]:
    """CSV en streaming con su propia sesión (la de la solicitud ya se cerró al empezar a enviar).

    UTF-8 con BOM para que Excel reconozca los acentos. Fechas AAAA-MM-DD e
    importes con punto decimal y signo.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=delimiter, lineterminator="\r\n")
    writer.writerow(LINE_FIELDS)
    yield ("﻿" + buffer.getvalue()).encode("utf-8")
    with SessionLocal() as db, db.begin():
        centers = load_center_map(db, company_id)
        conditions = _conditions(db, company_id, filters, area_ids, centers)
        described: dict[str, dict] = {}
        result = db.scalars(
            select(LedgerLine).where(*conditions).order_by(*_ORDER).execution_options(yield_per=CSV_BATCH)
        )
        for batch in result.partitions(CSV_BATCH):
            missing = {line.rule_id for line in batch if line.rule_id and line.rule_id not in described}
            described.update(describe_rules(db, missing))
            buffer.seek(0)
            buffer.truncate()
            for line in batch:
                row = classified(line, described, centers)
                writer.writerow(["" if row[f] is None else _text(row[f]) for f in LINE_FIELDS])
            yield buffer.getvalue().encode("utf-8")


_ORDER = (LedgerLine.posting_date, LedgerLine.sap_transaction_id, LedgerLine.sap_line)


def _text(value) -> str:
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _conditions(
    db: Session, company_id: str, filters: LedgerFilters, area_ids: frozenset[str] | None, centers: CenterMap | None = None
) -> list:
    if filters.date_to < filters.date_from:
        raise InvalidDataError("date_to no puede ser anterior a date_from.")
    if filters.subcodigo and filters.no_subcodigo:
        raise InvalidDataError("subcodigo y no_subcodigo no se pueden usar juntos.")
    if filters.supplier and filters.no_supplier:
        raise InvalidDataError("supplier y no_supplier no se pueden usar juntos.")
    conditions = [
        LedgerLine.company_id == company_id,
        LedgerLine.posting_date.between(filters.date_from, filters.date_to),
    ]
    if area_ids is not None and centers is None:
        centers = load_center_map(db, company_id)
    codes = visible_codes(db, company_id, area_ids, centers)
    if codes is not None:  # Alcance area: solo centros homologados a sus áreas.
        conditions.append(LedgerLine.cost_center_code.in_(sorted(codes)) if codes else false())
    if filters.accounts:
        conditions.append(or_(*(
            LedgerLine.account_code.like(f"{a.code}%") if a.match_mode == "prefix" else LedgerLine.account_code == a.code
            for a in filters.accounts
        )))
    if filters.cost_center_code:
        conditions.append(LedgerLine.cost_center_code == filters.cost_center_code)
    if filters.unclassified is True:
        conditions.append(LedgerLine.rule_id.is_(None))
    elif filters.unclassified is False:
        conditions.append(LedgerLine.rule_id.is_not(None))
    if filters.codigo or filters.subcodigo or filters.no_subcodigo:
        rule_ids = _rules_for(db, company_id, filters.codigo, filters.subcodigo, filters.no_subcodigo)
        conditions.append(LedgerLine.rule_id.in_(rule_ids) if rule_ids else false())
    if filters.supplier:
        conditions.append(LedgerLine.supplier == filters.supplier)
    if filters.no_supplier:
        # Mismo criterio que supplier_or_none: NULL o solo espacios.
        conditions.append(or_(LedgerLine.supplier.is_(None), func.trim(LedgerLine.supplier) == ""))
    return conditions


def _rules_for(
    db: Session, company_id: str, codigo: str | None, subcodigo: str | None, no_subcodigo: bool = False
) -> list[str]:
    """Reglas (activas o no) cuyo destino es ese codigo y/o subcodigo, comparando nombres sin mayúsculas.

    no_subcodigo: solo reglas que apuntan a una categoría principal (sin subcategoría).
    """
    categories = list(db.scalars(select(ExpenseCategory).where(ExpenseCategory.company_id == company_id)))
    by_id = {c.id: c for c in categories}

    def matches(category: ExpenseCategory) -> bool:
        top = by_id[category.parent_id] if category.parent_id else category
        sub = category if category.parent_id else None
        if codigo and top.name.strip().casefold() != codigo.strip().casefold():
            return False
        if subcodigo and (sub is None or sub.name.strip().casefold() != subcodigo.strip().casefold()):
            return False
        if no_subcodigo and sub is not None:
            return False
        return True

    targets = [c.id for c in categories if matches(c)]
    if not targets:
        return []
    return list(db.scalars(select(ExpenseRule.id).where(ExpenseRule.company_id == company_id,
                                                        ExpenseRule.category_id.in_(targets))))


def parse_account_list(raw: str | None) -> tuple[AccountFilter, ...]:
    """"95*,701110002" → filtros (misma sintaxis que la consulta en vivo)."""
    if not raw:
        return ()
    return tuple(parse_accounts([part for part in raw.split(",") if part.strip()]))
