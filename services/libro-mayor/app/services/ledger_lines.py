"""Consultas pequeñas sobre libro_mayor.ledger_lines que usan otros servicios."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import LedgerLine


def has_lines(db: Session, **filters) -> bool:
    """¿Hay líneas sincronizadas con estos filtros? p. ej. has_lines(db, account_id=...)."""
    query = select(LedgerLine.id)
    for column, value in filters.items():
        query = query.where(getattr(LedgerLine, column) == value)
    return db.scalar(query.limit(1)) is not None
