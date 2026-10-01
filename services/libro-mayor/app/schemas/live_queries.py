from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class LiveQueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # "95*" = todas las que empiezan por 95; "979005400" = exacta.
    accounts: list[str] = Field(min_length=1, max_length=200, examples=[["95*", "97*", "701110002"]])
    date_from: date = Field(examples=["2026-01-01"])
    date_to: date = Field(examples=["2026-12-31"])
    # Tramos que se consultan a SAP en paralelo.
    split: Literal["month", "day"] = "month"
    # lines = solo líneas (default); summary = solo resumen (liviano, sin límite
    # de líneas); full = líneas + resumen.
    view: Literal["lines", "summary", "full"] = "lines"


class ClassifiedLineOut(BaseModel):
    """Línea tal como vino de SAP + su clasificación (null = sin clasificar)."""

    sap_transaction_id: int
    sap_line: int
    posting_date: date
    document_date: date | None
    document_number: str | None
    transaction_type: str | None
    folio: str | None
    document_type: str | None
    account_code: str
    account_name: str | None
    supplier: str | None
    description: str | None
    line_comment: str | None
    counter_account_code: str | None
    counter_account_name: str | None
    reference_1: str | None
    reference_2: str | None
    reference_3: str | None
    amount_local: Decimal
    amount_foreign: Decimal
    cost_center_code: str | None
    cost_center_area: str | None
    cost_center_name: str | None
    # Área de auth a la que está homologado el centro de costo (null = sin homologar).
    area_id: str | None = None
    area_name: str | None = None
    sap_created_at: datetime | None
    sap_updated_at: datetime | None
    rule_id: str | None
    # Nombres de proyecto-05: categoría, subcategoría y nombre para reportes
    # (el de la regla o, si no tiene, el de la cuenta SAP). null = sin clasificar.
    codigo: str | None
    subcodigo: str | None
    nombre_cuenta: str | None


class SummaryRowOut(BaseModel):
    year: int
    month: int
    codigo: str | None  # null = sin clasificar
    subcodigo: str | None
    lines: int
    amount_local: Decimal
    amount_foreign: Decimal


class LiveQueryResult(BaseModel):
    accounts: list[str]  # Filtros aplicados, sin repetidos.
    date_from: date
    date_to: date
    split: str
    chunks: int  # Tramos consultados a SAP.
    lines_total: int
    elapsed_ms: int
    summary: list[SummaryRowOut] | None  # null con view=lines.
    lines: list[ClassifiedLineOut] | None  # null con view=summary.
