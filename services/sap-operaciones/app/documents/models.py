"""Datos de la búsqueda de documentos y anexos, independientes de la fuente.

Las fuentes (Service Layer hoy, HANA quizás mañana) reciben un DocumentQuery
ya validado y devuelven DocumentRow / AttachmentRow: nunca respuestas crudas de
SAP. Las reglas de la búsqueda viven aquí, así son las mismas para cualquier fuente.

Dos modos (uno por búsqueda):
- Exacto: un criterio (doc_entry, doc_num, num_at_card o folio).
- Por cliente/proveedor: card_code y/o card_name (ambos "contiene": el código
  de socio lleva prefijo, p. ej. P20610983970, y se busca por el RUC), con rango
  de fechas obligatorio. Abiertos y cerrados (no se filtra por estado).
"""

import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date

from app.documents.catalog import DOC_ENTRY, DOC_NUM, DOCUMENT_TYPES, FOLIO, NUM_AT_CARD, DocumentType
from app.services.errors import InvalidDataError

MAX_DATE_RANGE_DAYS = 366  # Una búsqueda por cliente/proveedor no recorre más de un año.
MIN_PARTNER_CHARS = 3  # Código y nombre se buscan con "contiene": evita "contiene 'a'".
MAX_TEXT_CHARS = 100
MAX_PAGE_SIZE = 100

# "F001-00047012", "F001-47012" o "F001 47012" -> ("F001", 47012).
FOLIO_PATTERN = re.compile(r"\s*([A-Za-z0-9]{1,10})\s*[-\s]\s*0*(\d{1,12})\s*")


@dataclass(frozen=True)
class DocumentQuery:
    doc_type: DocumentType
    doc_entry: int | None = None
    doc_num: int | None = None
    num_at_card: str | None = None
    folio_prefix: str | None = None
    folio_number: int | None = None
    card_code: str | None = None
    card_name: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    offset: int = 0
    limit: int = 50


@dataclass(frozen=True)
class DocumentRow:
    type_code: str
    doc_entry: int
    doc_num: int | None
    num_at_card: str | None
    folio: str | None  # "F001-47012" o None.
    card_code: str | None
    card_name: str | None
    doc_date: date | None
    attachment_entry: int | None  # None = sin anexos.


@dataclass(frozen=True)
class AttachmentRow:
    line: int  # Posición del anexo en el documento (1, 2, ...): lo que pide el front para descargar.
    file_name: str  # Con extensión, p. ej. "factura.pdf".
    attached_on: date | None


@dataclass
class AttachmentFile:
    """Archivo abierto: se lee por partes (chunks) y no se guarda en el servicio."""

    file_name: str
    content_type: str
    size_bytes: int | None  # None si SAP no lo informa.
    chunks: Iterator[bytes]


def _positive_int(name: str, value: int | None) -> int | None:
    if value is not None and value <= 0:
        raise InvalidDataError(f"{name} debe ser un número positivo.")
    return value


def _text(name: str, value: str | None, min_chars: int = 1) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    if len(value) < min_chars or len(value) > MAX_TEXT_CHARS:
        raise InvalidDataError(f"{name} debe tener entre {min_chars} y {MAX_TEXT_CHARS} caracteres.")
    if any(ord(char) < 32 for char in value):
        raise InvalidDataError(f"{name} tiene caracteres no permitidos.")
    return value


def parse_folio(folio: str) -> tuple[str, int]:
    match = FOLIO_PATTERN.fullmatch(folio)
    if not match:
        raise InvalidDataError("Folio inválido: se espera SERIE-NÚMERO, p. ej. F001-47012.")
    return match.group(1).upper(), int(match.group(2))


def build_query(
    *,
    type_code: str,
    doc_entry: int | None = None,
    doc_num: int | None = None,
    num_at_card: str | None = None,
    folio: str | None = None,
    card_code: str | None = None,
    card_name: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    offset: int = 0,
    limit: int = 50,
) -> DocumentQuery:
    """Valida los filtros que llegan del front y arma la búsqueda."""
    doc_type = DOCUMENT_TYPES.get(type_code)
    if doc_type is None:
        raise InvalidDataError("Tipo de documento no admitido.")
    if offset < 0 or not 1 <= limit <= MAX_PAGE_SIZE:
        raise InvalidDataError(f"Paginación inválida (máximo {MAX_PAGE_SIZE} por página).")

    doc_entry = _positive_int("DocEntry", doc_entry)
    doc_num = _positive_int("Número de documento", doc_num)
    num_at_card = _text("Referencia", num_at_card)
    folio = _text("Folio", folio)
    card_code = _text("Código de cliente/proveedor", card_code, MIN_PARTNER_CHARS)
    card_name = _text("Nombre de cliente/proveedor", card_name, MIN_PARTNER_CHARS)

    exact = {DOC_ENTRY: doc_entry, DOC_NUM: doc_num, NUM_AT_CARD: num_at_card, FOLIO: folio}
    given = [name for name, value in exact.items() if value is not None]
    by_partner = card_code is not None or card_name is not None

    if given:
        if len(given) > 1 or by_partner or date_from or date_to:
            raise InvalidDataError("La búsqueda exacta admite un solo criterio, sin cliente/proveedor ni fechas.")
        if given[0] not in doc_type.criteria:
            raise InvalidDataError(f"{doc_type.label} no se puede buscar por ese criterio.")
        folio_prefix, folio_number = parse_folio(folio) if folio else (None, None)
        return DocumentQuery(doc_type, doc_entry=doc_entry, doc_num=doc_num, num_at_card=num_at_card,
                             folio_prefix=folio_prefix, folio_number=folio_number, offset=offset, limit=limit)

    if not by_partner:
        raise InvalidDataError("Indica un criterio exacto o un cliente/proveedor con rango de fechas.")
    if doc_type.partner == "none":
        raise InvalidDataError(f"{doc_type.label} no se busca por cliente/proveedor.")
    if date_from is None or date_to is None:
        raise InvalidDataError("La búsqueda por cliente/proveedor necesita fecha desde y hasta.")
    if date_from > date_to:
        raise InvalidDataError("La fecha desde no puede ser posterior a la fecha hasta.")
    if (date_to - date_from).days > MAX_DATE_RANGE_DAYS:
        raise InvalidDataError(f"El rango de fechas no puede superar {MAX_DATE_RANGE_DAYS} días.")
    return DocumentQuery(doc_type, card_code=card_code, card_name=card_name, date_from=date_from,
                         date_to=date_to, offset=offset, limit=limit)
