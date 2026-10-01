from pydantic import BaseModel

from app.schemas.live_queries import ClassifiedLineOut, SummaryRowOut


class LedgerSummaryRowOut(SummaryRowOut):
    """Fila de GET /ledger/summary. "supplier" solo aparece con by_supplier=true
    (null = sin proveedor); sin ese parámetro la respuesta no cambia."""

    supplier: str | None = None


class LedgerLinesPage(BaseModel):
    """Una página de líneas sincronizadas. next_offset null = no hay más."""

    total: int
    limit: int
    offset: int
    next_offset: int | None
    lines: list[ClassifiedLineOut]
