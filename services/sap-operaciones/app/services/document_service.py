"""Documentos SAP: búsqueda y anexos (/documents). Las descargas, con su
registro, en download_service.py.

Solo lectura en SAP. Las reglas que no dependen de la fuente viven
aquí y en app/documents/models.py; el acceso a SAP, en un DocumentRepository.

- La base (CompanyDB) debe estar en las Bases SAP sugeridas de la empresa: el
  usuario SAP de documentos no puede apuntar a cualquier base.
- URL del Service Layer: la de la empresa o la del despliegue (igual que los trabajos).
- Credencial: una sola, SAP_DOCUMENTS_USER / SAP_DOCUMENTS_PASSWORD (por ahora).
- No se mantiene abierta una transacción de PostgreSQL mientras se espera a SAP.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import CompanyContext
from app.core.config import settings
from app.documents.catalog import DOCUMENT_TYPES, DocumentType
from app.documents.models import AttachmentRow, DocumentRow, build_query
from app.documents.repository import DocumentRepository
from app.models.entities import SapDatabase
from app.sap.attachment_folder import AttachmentFolder
from app.sap.session_pool import shared_client
from app.sap.sl_document_repository import ServiceLayerDocumentRepository
from app.services.errors import ConflictError, InvalidDataError, NotFoundError
from app.services.job_service import service_layer_url


def list_types() -> list[DocumentType]:
    return list(DOCUMENT_TYPES.values())


def doc_type_or_404(type_code: str) -> DocumentType:
    doc_type = DOCUMENT_TYPES.get(type_code)
    if doc_type is None:
        raise NotFoundError("Tipo de documento no admitido.")
    return doc_type


def _check_company_db(db: Session, ctx: CompanyContext, company_db: str) -> None:
    with db.begin():
        found = db.scalar(select(SapDatabase.id).where(
            SapDatabase.company_id == ctx.company_id,
            SapDatabase.company_db == company_db,
            SapDatabase.is_active.is_(True),
        ))
    if found is None:
        raise InvalidDataError("La base SAP no está entre las bases de la empresa.")


def _sap_credentials(ctx: CompanyContext, company_db: str) -> tuple[str, str]:
    """Usuario y clave SAP para consultar documentos.

    Único punto a cambiar cuando haya credenciales por usuario: hoy devuelve la
    del despliegue para cualquier usuario, empresa y base.
    """
    if not settings.SAP_DOCUMENTS_USER or settings.SAP_DOCUMENTS_PASSWORD is None:
        raise ConflictError("El usuario SAP para documentos no está configurado (SAP_DOCUMENTS_USER).")
    return settings.SAP_DOCUMENTS_USER, settings.SAP_DOCUMENTS_PASSWORD.get_secret_value()


@contextmanager
def repository(db: Session, ctx: CompanyContext, company_db: str) -> Iterator[DocumentRepository]:
    """Repositorio de la empresa sobre la base indicada. Para cambiar a HANA,
    este es el único lugar que construye la implementación."""
    _check_company_db(db, ctx, company_db)
    base_url = service_layer_url(db, ctx.company_id)
    user, password = _sap_credentials(ctx, company_db)
    # Archivos desde la carpeta de anexos montada, si está configurada; si no, por el Service Layer.
    folder = AttachmentFolder(settings.SAP_ATTACHMENTS_DIR) if settings.SAP_ATTACHMENTS_DIR else None
    # Sesión del Service Layer compartida entre solicitudes (no se cierra aquí).
    yield ServiceLayerDocumentRepository(shared_client(base_url, company_db, user, password), folder)


def search(db: Session, ctx: CompanyContext, company_db: str, *, type_code: str, doc_entry: int | None,
           doc_num: int | None, num_at_card: str | None, folio: str | None, card_code: str | None,
           card_name: str | None, date_from: date | None, date_to: date | None,
           offset: int, limit: int) -> list[DocumentRow]:
    # Se valida antes de conectar a SAP: un filtro inválido no abre sesión.
    query = build_query(type_code=type_code, doc_entry=doc_entry, doc_num=doc_num, num_at_card=num_at_card,
                        folio=folio, card_code=card_code, card_name=card_name, date_from=date_from,
                        date_to=date_to, offset=offset, limit=limit)
    with repository(db, ctx, company_db) as repo:
        return repo.search(query)


def list_attachments(db: Session, ctx: CompanyContext, company_db: str, type_code: str,
                     doc_entry: int) -> list[AttachmentRow]:
    doc_type = doc_type_or_404(type_code)
    with repository(db, ctx, company_db) as repo:
        return repo.list_attachments(doc_type, doc_entry)
