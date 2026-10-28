"""Documentos SAP y sus anexos: /sap-operaciones/documents/...

Permiso sap_documents.view (alcance company). Solo lectura en SAP.
company_db: una de las Bases SAP sugeridas de la empresa (si no, 422).

Descargar: POST /documents/downloads registra qué se baja (modo single,
sequential o zip) y luego se piden los archivos (/files/{seq}) o el ZIP (/zip).
No hay descarga sin registro.
"""

from contextlib import ExitStack
from datetime import date
from urllib.parse import quote

from fastapi import APIRouter, Depends, Path, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from app.api.dependencies import CompanyContext, require_company_permission
from app.core.db.connection import get_db
from app.core.permissions import CAN_VIEW_DOCUMENTS
from app.documents.models import MAX_PAGE_SIZE
from app.schemas.documents import (
    AttachmentOut,
    DocumentOut,
    DocumentSearchOut,
    DocumentTypeOut,
    DownloadFileOut,
    DownloadIn,
    DownloadListItem,
    DownloadOut,
    DownloadPage,
)
from app.schemas.page import Page
from app.services import document_service, download_service
from app.services.download_service import FileRequest

router = APIRouter(prefix="/documents", tags=["documents"])

CompanyDb = Query(min_length=1, max_length=100, description="Base SAP (CompanyDB) de la lista de la empresa.")
TypeCode = Path(max_length=10, description="Código del tipo (GET /documents/types), p. ej. FV.")


@router.get("/types", response_model=list[DocumentTypeOut], operation_id="listDocumentTypes")
def list_types(ctx: CompanyContext = Depends(require_company_permission(*CAN_VIEW_DOCUMENTS))):
    """Tipos de documento y criterios de búsqueda admitidos por cada uno."""
    return [DocumentTypeOut(code=t.code, label=t.label, partner=t.partner, criteria=list(t.criteria))
            for t in document_service.list_types()]


@router.get("/search", response_model=DocumentSearchOut, operation_id="searchDocuments")
def search(
    company_db: str = CompanyDb,
    type_code: str = Query(max_length=10, alias="type", description="Código del tipo, p. ej. FV."),
    doc_entry: int | None = Query(default=None),
    doc_num: int | None = Query(default=None),
    num_at_card: str | None = Query(default=None, max_length=100),
    folio: str | None = Query(default=None, max_length=30, description="SERIE-NÚMERO, p. ej. F001-47012."),
    card_code: str | None = Query(default=None, max_length=100, description="Contiene (mínimo 3), p. ej. el RUC."),
    card_name: str | None = Query(default=None, max_length=100, description="Contiene (mínimo 3 caracteres)."),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
    ctx: CompanyContext = Depends(require_company_permission(*CAN_VIEW_DOCUMENTS)),
    db: Session = Depends(get_db),
):
    """Un criterio exacto (doc_entry, doc_num, num_at_card o folio), o cliente/proveedor
    (card_code y/o card_name) con date_from y date_to (máximo un año). Más recientes primero.

    SAP no informa el total: next_offset se ofrece mientras la página venga llena."""
    rows = document_service.search(
        db, ctx, company_db, type_code=type_code, doc_entry=doc_entry, doc_num=doc_num, num_at_card=num_at_card,
        folio=folio, card_code=card_code, card_name=card_name, date_from=date_from, date_to=date_to,
        offset=offset, limit=limit)
    items = [DocumentOut(type_code=r.type_code, doc_entry=r.doc_entry, doc_num=r.doc_num, num_at_card=r.num_at_card,
                         folio=r.folio, card_code=r.card_code, card_name=r.card_name, doc_date=r.doc_date,
                         has_attachments=r.attachment_entry is not None)
             for r in rows]
    next_offset = offset + limit if len(items) == limit else None
    return DocumentSearchOut(limit=limit, offset=offset, next_offset=next_offset, items=items)


@router.get("/{type_code}/{doc_entry}/attachments", response_model=list[AttachmentOut],
            operation_id="listDocumentAttachments")
def list_attachments(
    doc_entry: int = Path(ge=1),
    type_code: str = TypeCode,
    company_db: str = CompanyDb,
    ctx: CompanyContext = Depends(require_company_permission(*CAN_VIEW_DOCUMENTS)),
    db: Session = Depends(get_db),
):
    """Anexos del documento (vacío si no tiene). line identifica cada uno para descargarlo."""
    rows = document_service.list_attachments(db, ctx, company_db, type_code, doc_entry)
    return [AttachmentOut(line=r.line, file_name=r.file_name, attached_on=r.attached_on) for r in rows]


# --- Descargas (con registro)


def _stream(stack: ExitStack, chunks, file_name: str, content_type: str,
            size_bytes: int | None = None) -> StreamingResponse:
    """Respuesta por partes que cierra la descarga y la sesión SAP al terminar.

    Si el envío no termina (el cliente corta o la respuesta no llega a salir),
    se cierra con error: la entrega queda failed, no delivered."""
    state = {"done": False}

    def body():
        with stack:
            yield from chunks
            state["done"] = True

    def cleanup():
        if not state["done"]:
            interrupted = ConnectionAbortedError("Descarga interrumpida.")
            stack.__exit__(type(interrupted), interrupted, None)

    ascii_name = file_name.encode("ascii", "ignore").decode() or "anexo"
    headers = {"Content-Disposition": f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(file_name)}"}
    if size_bytes is not None:
        headers["Content-Length"] = str(size_bytes)
    return StreamingResponse(body(), media_type=content_type, headers=headers, background=BackgroundTask(cleanup))


def _download_out(result: dict) -> DownloadOut:
    download = result["download"]
    return DownloadOut(id=download.id, company_db=download.company_db, mode=download.mode,
                       file_count=download.file_count, user_id=result["user_id"], trace_id=download.trace_id,
                       created_at=download.created_at,
                       files=[DownloadFileOut.model_validate(f) for f in result["files"]])


@router.post("/downloads", response_model=DownloadOut, status_code=status.HTTP_201_CREATED,
             operation_id="createDocumentDownload")
def create_download(data: DownloadIn, ctx: CompanyContext = Depends(require_company_permission(*CAN_VIEW_DOCUMENTS)),
                    db: Session = Depends(get_db)):
    """Registra la descarga (quién, qué archivos, en qué modo) tras comprobar en SAP que
    cada anexo existe. Después: GET /files/{seq} por archivo, o GET /zip."""
    files = [FileRequest(f.type_code, f.doc_entry, f.line) for f in data.files]
    download, rows = download_service.create_download(db, ctx, data.company_db, data.mode, files)
    return _download_out({"download": download, "user_id": ctx.user_id, "files": rows})


@router.get("/downloads", response_model=DownloadPage, operation_id="listDocumentDownloads")
def list_downloads(page: Page = Depends(), ctx: CompanyContext = Depends(require_company_permission(*CAN_VIEW_DOCUMENTS)),
                   db: Session = Depends(get_db)):
    """Registro de descargas, más recientes primero: las propias (el administrador de
    plataforma ve las de toda la empresa)."""
    rows, total = download_service.list_downloads(db, ctx, limit=page.limit, offset=page.offset)
    items = [DownloadListItem(id=r["download"].id, company_db=r["download"].company_db, mode=r["download"].mode,
                              file_count=r["download"].file_count, delivered_count=r["delivered_count"],
                              user_id=r["user_id"], created_at=r["download"].created_at)
             for r in rows]
    return DownloadPage(total=total, limit=page.limit, offset=page.offset, next_offset=page.next_offset(total),
                        items=items)


@router.get("/downloads/{download_id}", response_model=DownloadOut, operation_id="getDocumentDownload")
def get_download(download_id: str = Path(max_length=36),
                 ctx: CompanyContext = Depends(require_company_permission(*CAN_VIEW_DOCUMENTS)),
                 db: Session = Depends(get_db)):
    """Detalle: cada archivo con su documento y si se entregó."""
    return _download_out(download_service.get_download(db, ctx, download_id))


@router.get("/downloads/{download_id}/files/{seq}", operation_id="downloadDocumentFile",
            response_class=StreamingResponse, responses={200: {"content": {"application/octet-stream": {}}}})
def download_file(download_id: str = Path(max_length=36), seq: int = Path(ge=1),
                  ctx: CompanyContext = Depends(require_company_permission(*CAN_VIEW_DOCUMENTS)),
                  db: Session = Depends(get_db)):
    """Un archivo de una descarga single o sequential (solo quien la pidió, una vez)."""
    # Se abre antes de responder: un anexo inexistente es un error HTTP, no un archivo vacío.
    stack = ExitStack()
    attachment = stack.enter_context(download_service.open_file(db, ctx, download_id, seq))
    return _stream(stack, attachment.chunks, attachment.file_name, attachment.content_type, attachment.size_bytes)


@router.get("/downloads/{download_id}/zip", operation_id="downloadDocumentZip",
            response_class=StreamingResponse, responses={200: {"content": {"application/zip": {}}}})
def download_zip(download_id: str = Path(max_length=36),
                 ctx: CompanyContext = Depends(require_company_permission(*CAN_VIEW_DOCUMENTS)),
                 db: Session = Depends(get_db)):
    """Todos los archivos de una descarga zip en un solo ZIP, armado mientras se envía.
    Los que SAP no entrega se listan en NO_DESCARGADOS.txt."""
    stack = ExitStack()
    file_name, chunks = stack.enter_context(download_service.open_zip(db, ctx, download_id))
    return _stream(stack, chunks, file_name, "application/zip")
