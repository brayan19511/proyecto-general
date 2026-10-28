"""Descargas de anexos SAP con registro de negocio (quién descargó qué).

Toda descarga pasa por un registro (decisión del usuario, 2026-10-27):
1. create_download: el front declara el modo y los archivos; se validan contra
   SAP (el documento existe y tiene ese anexo) y se guarda la cabecera con una
   línea por archivo. El cliente solo envía tipo, DocEntry y línea; nombres y
   DocNum los toma el servidor de SAP.
2. open_file (single / sequential, uno por llamada) u open_zip: entregan los
   archivos y marcan cada línea delivered o failed.

Solo quien creó la descarga puede bajar sus archivos, dentro de
DOWNLOAD_TTL_MINUTES. Ver el registro: cada uno el suyo; el administrador de
plataforma, todos los de la empresa.

La entrega se marca con una sesión propia: termina después de responder, cuando
la sesión de la solicitud puede estar cerrada. Si marcarla falla, el archivo ya
se entregó: se registra en el log técnico y no se corta la respuesta.
"""

import io
import logging
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import timedelta

from platform_audit import current_trace_id
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.api.dependencies import CompanyContext
from app.core.db.connection import SessionLocal
from app.documents.models import AttachmentFile
from app.models.common.mixin_model import new_id, utcnow
from app.models.entities import Actor, DocumentDownload, DocumentDownloadFile
from app.services.actors import user_actor_id
from app.services.document_service import doc_type_or_404, repository
from app.services.errors import ConflictError, ForbiddenError, InvalidDataError, NotFoundError, ServiceError

logger = logging.getLogger(__name__)

MAX_DOWNLOAD_FILES = 50
DOWNLOAD_TTL_MINUTES = 60  # Pasado este tiempo, se pide una descarga nueva (queda otro registro).
ZIP_CHUNK_BYTES = 64 * 1024


@dataclass(frozen=True)
class FileRequest:
    type_code: str
    doc_entry: int
    line: int


# --- Crear la descarga (registro)


def create_download(db: Session, ctx: CompanyContext, company_db: str, mode: str,
                    files: list[FileRequest]) -> tuple[DocumentDownload, list[DocumentDownloadFile]]:
    if mode not in ("single", "sequential", "zip"):
        raise InvalidDataError("Modo de descarga no admitido.")
    if not files:
        raise InvalidDataError("Selecciona al menos un archivo.")
    if mode == "single" and len(files) != 1:
        raise InvalidDataError("La descarga individual es de un solo archivo.")
    if len(files) > MAX_DOWNLOAD_FILES:
        raise InvalidDataError(f"Máximo {MAX_DOWNLOAD_FILES} archivos por descarga.")
    if len(set(files)) != len(files):
        raise InvalidDataError("Hay archivos repetidos en la selección.")
    for file in files:
        doc_type_or_404(file.type_code)

    # Se valida contra SAP antes de abrir la transacción: no se espera a SAP con la base bloqueada.
    resolved = []
    with repository(db, ctx, company_db) as repo:
        documents = {}
        for file in files:
            key = (file.type_code, file.doc_entry)
            if key not in documents:
                doc_type = doc_type_or_404(file.type_code)
                document = repo.get_document(doc_type, file.doc_entry)
                attachments = repo.list_attachments(doc_type, file.doc_entry) if document.attachment_entry else []
                documents[key] = (document, {a.line: a for a in attachments})
            document, attachments = documents[key]
            attachment = attachments.get(file.line)
            if attachment is None:
                raise InvalidDataError(f"El documento {document.doc_num or file.doc_entry} no tiene el anexo {file.line}.")
            resolved.append((file, document, attachment))

    now = utcnow()
    with db.begin():
        actor_id = user_actor_id(db, ctx.user_id)
        download = DocumentDownload(id=new_id(), company_id=ctx.company_id, company_db=company_db, mode=mode,
                                    file_count=len(resolved), trace_id=current_trace_id(), created_by=actor_id,
                                    created_at=now)
        db.add(download)
        db.flush()
        rows = [
            DocumentDownloadFile(id=new_id(), download_id=download.id, seq=seq, type_code=file.type_code,
                                 doc_entry=file.doc_entry, doc_num=document.doc_num,
                                 attachment_entry=document.attachment_entry, line=file.line,
                                 file_name=attachment.file_name, status="pending", created_by=actor_id,
                                 created_at=now)
            for seq, (file, document, attachment) in enumerate(resolved, start=1)
        ]
        db.add_all(rows)
    return download, rows


# --- Consultar el registro


def _visible(db: Session, ctx: CompanyContext, download_id: str) -> tuple[DocumentDownload, str]:
    """La descarga y el usuario que la hizo, si quien consulta puede verla (si no, 404)."""
    row = db.execute(
        select(DocumentDownload, Actor.subject_ref).join(Actor, Actor.id == DocumentDownload.created_by)
        .where(DocumentDownload.id == download_id, DocumentDownload.company_id == ctx.company_id)
    ).first()
    if row is None or (row[1] != ctx.user_id and not ctx.is_platform_admin):
        raise NotFoundError("Descarga no encontrada.")
    return row[0], row[1]


def get_download(db: Session, ctx: CompanyContext, download_id: str) -> dict:
    with db.begin():
        download, user = _visible(db, ctx, download_id)
        files = db.scalars(select(DocumentDownloadFile).where(DocumentDownloadFile.download_id == download.id)
                           .order_by(DocumentDownloadFile.seq)).all()
    return {"download": download, "user_id": user, "files": list(files)}


def list_downloads(db: Session, ctx: CompanyContext, *, limit: int, offset: int) -> tuple[list[dict], int]:
    conditions = [DocumentDownload.company_id == ctx.company_id]
    if not ctx.is_platform_admin:
        conditions.append(Actor.subject_ref == ctx.user_id)
    # Archivos entregados por descarga, para la lista (sin traer cada línea).
    delivered = (select(func.count()).where(DocumentDownloadFile.download_id == DocumentDownload.id,
                                            DocumentDownloadFile.status == "delivered")
                 .correlate(DocumentDownload).scalar_subquery())
    base = select(DocumentDownload).join(Actor, Actor.id == DocumentDownload.created_by).where(*conditions)
    with db.begin():
        total = db.scalar(select(func.count()).select_from(base.subquery()))
        rows = db.execute(
            select(DocumentDownload, Actor.subject_ref, delivered)
            .join(Actor, Actor.id == DocumentDownload.created_by).where(*conditions)
            .order_by(DocumentDownload.created_at.desc()).limit(limit).offset(offset)
        ).all()
    return [{"download": d, "user_id": user, "delivered_count": count} for d, user, count in rows], total


# --- Entregar archivos


def _own_download(db: Session, ctx: CompanyContext, download_id: str) -> DocumentDownload:
    """Solo quien creó la descarga baja sus archivos (el administrador también pide la suya)."""
    with db.begin():
        download, user = _visible(db, ctx, download_id)
    if user != ctx.user_id:
        raise ForbiddenError("Solo quien pidió la descarga puede bajar sus archivos.")
    if utcnow() - download.created_at > timedelta(minutes=DOWNLOAD_TTL_MINUTES):
        raise ConflictError("La descarga venció: vuelve a seleccionar los archivos.")
    return download


def _mark(download_id: str, actor_id: str, results: dict[int, tuple[str, str | None]]) -> None:
    """Guarda la entrega de cada archivo: {seq: (delivered | failed, error)}."""
    if not results:
        return
    try:
        now = utcnow()
        with SessionLocal() as db, db.begin():
            for seq, (status, error) in results.items():
                db.execute(
                    update(DocumentDownloadFile)
                    .where(DocumentDownloadFile.download_id == download_id, DocumentDownloadFile.seq == seq,
                           DocumentDownloadFile.status != "delivered")
                    .values(status=status, error=error, delivered_at=now if status == "delivered" else None,
                            updated_at=now, updated_by=actor_id)
                )
    except Exception:
        logger.exception("No se pudo registrar la entrega de la descarga %s", download_id)


def _error_message(exc: BaseException) -> str:
    if isinstance(exc, ServiceError):
        return str(exc)[:300]
    if isinstance(exc, (GeneratorExit, ConnectionAbortedError)):
        return "Descarga interrumpida."
    return "Error al obtener el archivo."


@contextmanager
def open_file(db: Session, ctx: CompanyContext, download_id: str, seq: int) -> Iterator[AttachmentFile]:
    """Un archivo de una descarga single o sequential. Al salir del with queda delivered o failed."""
    download = _own_download(db, ctx, download_id)
    if download.mode == "zip":
        raise ConflictError("Esta descarga es un ZIP: usa /zip.")
    with db.begin():
        file = db.scalar(select(DocumentDownloadFile).where(DocumentDownloadFile.download_id == download.id,
                                                            DocumentDownloadFile.seq == seq))
    if file is None:
        raise NotFoundError("Archivo no encontrado en la descarga.")
    if file.status == "delivered":
        raise ConflictError("Este archivo ya se descargó: pide una descarga nueva para bajarlo otra vez.")

    try:
        with repository(db, ctx, download.company_db) as repo:
            with repo.open_attachment(doc_type_or_404(file.type_code), file.doc_entry, file.line) as attachment:
                yield attachment
    except BaseException as exc:
        _mark(download.id, download.created_by, {seq: ("failed", _error_message(exc))})
        raise
    _mark(download.id, download.created_by, {seq: ("delivered", None)})


class _ZipSink(io.RawIOBase):
    """Destino del ZIP que se vacía por partes: el ZIP nunca está entero en memoria."""

    def __init__(self):
        self._chunks: list[bytes] = []

    def writable(self) -> bool:
        return True

    def write(self, data) -> int:
        self._chunks.append(bytes(data))
        return len(data)

    def drain(self) -> bytes:
        data = b"".join(self._chunks)
        self._chunks.clear()
        return data


def _zip_name(file: DocumentDownloadFile, used: set[str]) -> str:
    """Carpeta por documento (FV_100/factura.pdf), sin repetir nombres dentro del ZIP."""
    name = f"{file.type_code}_{file.doc_num or file.doc_entry}/{file.file_name}"
    stem, dot, extension = name.rpartition(".")
    candidate, n = name, 2
    while candidate in used:
        candidate = f"{stem} ({n}).{extension}" if dot else f"{name} ({n})"
        n += 1
    used.add(candidate)
    return candidate


@contextmanager
def open_zip(db: Session, ctx: CompanyContext, download_id: str) -> Iterator[tuple[str, Iterator[bytes]]]:
    """(nombre del ZIP, bytes por partes). Un archivo que SAP no entrega queda failed y
    se lista en NO_DESCARGADOS.txt dentro del ZIP; los demás siguen."""
    download = _own_download(db, ctx, download_id)
    if download.mode != "zip":
        raise ConflictError("Esta descarga no es un ZIP.")
    with db.begin():
        files = db.scalars(select(DocumentDownloadFile)
                           .where(DocumentDownloadFile.download_id == download.id,
                                  DocumentDownloadFile.status != "delivered")
                           .order_by(DocumentDownloadFile.seq)).all()
    if not files:
        raise ConflictError("Los archivos de esta descarga ya se entregaron: pide una descarga nueva.")

    # La sesión con SAP se abre antes de responder: base o credencial inválidas son un error HTTP, no un ZIP vacío.
    with repository(db, ctx, download.company_db) as repo:
        def chunks() -> Iterator[bytes]:
            results: dict[int, tuple[str, str | None]] = {}
            sink, used, missing = _ZipSink(), set(), []
            try:
                with zipfile.ZipFile(sink, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                    for file in files:
                        try:
                            with repo.open_attachment(doc_type_or_404(file.type_code), file.doc_entry,
                                                      file.line) as attachment:
                                with archive.open(_zip_name(file, used), "w", force_zip64=True) as target:
                                    for chunk in attachment.chunks:
                                        target.write(chunk)
                                        if data := sink.drain():
                                            yield data
                        except ServiceError as exc:
                            # Este archivo falló; el ZIP sigue con los demás.
                            results[file.seq] = ("failed", _error_message(exc))
                            missing.append(f"{file.type_code} {file.doc_num or file.doc_entry} - {file.file_name}: {exc}")
                            continue
                        results[file.seq] = ("delivered", None)
                    if missing:
                        archive.writestr("NO_DESCARGADOS.txt", "\r\n".join(missing))
                yield sink.drain()
            except BaseException as exc:
                # Corte del cliente o de SAP: lo que no llegó a completarse queda failed.
                for file in files:
                    if results.get(file.seq, ("",))[0] != "failed":
                        results[file.seq] = ("failed", _error_message(exc))
                raise
            finally:
                _mark(download.id, download.created_by, results)

        yield f"anexos-{download.id[:8]}.zip", chunks()
