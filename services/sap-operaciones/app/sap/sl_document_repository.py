"""DocumentRepository sobre el Service Layer (OData v4 de SAP Business One).

Seguridad:
- La entidad sale del catálogo (lista blanca), nunca del cliente.
- Textos dentro de $filter: literales OData con la comilla simple duplicada
  (equivale a parametrizar en SQL). Números y fechas llegan ya tipados desde
  DocumentQuery, así que no pueden traer texto.
- httpx codifica los parámetros de la URL (&, #, espacios no rompen la consulta).
- El archivo a descargar se resuelve desde el documento: AttachmentEntry del
  documento + posición del anexo. El cliente nunca envía una ruta ni un AbsEntry.
- El nombre del archivo que viene de SAP se limpia (sin separadores de ruta ni
  caracteres de control) antes de usarse en la descarga.

Anexos en el Service Layer: Attachments2({AttachmentEntry}) lista las líneas
(FileName, FileExtension, AttachmentDate). El archivo:
- con folder (AttachmentFolder, SAP_ATTACHMENTS_DIR): se lee de la carpeta de
  anexos montada en el servicio (decisión del usuario, 2026-10-28);
- sin folder: Attachments2({id})/$value?filename='x'. Quien lee la carpeta es el
  servidor del Service Layer, y hoy no la tiene montada ("LINUX mount point").

El cliente (ServiceLayerClient) lo crea y cierra quien usa el repositorio.
"""

import mimetypes
import re
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date

from app.documents.catalog import FOLIO, NUM_AT_CARD, DocumentType
from app.documents.models import AttachmentFile, AttachmentRow, DocumentQuery, DocumentRow
from app.sap.attachment_folder import AttachmentFolder
from app.sap.service_layer import SapAuthError, SapError, SapNotFoundError, ServiceLayerClient
from app.services.errors import ConflictError, NotFoundError, UpstreamError

DOWNLOAD_CHUNK_BYTES = 64 * 1024
UNSAFE_FILE_NAME_CHARS = re.compile(r'[\x00-\x1f\x7f/\\:*?"<>|]')


def odata_string(value: str) -> str:
    """Literal de texto OData: entre comillas simples y con ' duplicada."""
    return "'" + value.replace("'", "''") + "'"


def odata_date(value: date) -> str:
    return odata_string(value.isoformat())


def safe_file_name(name: str) -> str:
    cleaned = UNSAFE_FILE_NAME_CHARS.sub("_", name).strip(" .")
    return cleaned[:200] or "anexo"


def _date(value) -> date | None:
    # El Service Layer devuelve fechas como "2026-10-27" o "2026-10-27T00:00:00Z".
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


@contextmanager
def _sap_errors(not_found: str, with_sap_detail: bool = False):
    """Traduce los errores del Service Layer a errores de negocio con mensaje seguro.

    with_sap_detail: agrega el texto de SAP al 404 (en la descarga, SAP responde 404
    tanto si falta el archivo como si su servidor no ve la carpeta de anexos)."""
    try:
        yield
    except SapNotFoundError as exc:
        if with_sap_detail and "mount point" in exc.message.lower():
            # Configuración del servidor del Service Layer (Linux), no un archivo faltante.
            raise UpstreamError("El servidor del Service Layer no tiene acceso a la carpeta de anexos "
                                f"(falta su punto de montaje en Linux). SAP: {exc.message}") from exc
        raise NotFoundError(f"{not_found} SAP: {exc.message}" if with_sap_detail else not_found) from exc
    except SapAuthError as exc:
        # El usuario SAP es configuración del servicio, no un dato del operador.
        raise ConflictError(f"No se pudo iniciar sesión en SAP con el usuario configurado. {exc.message}") from exc
    except SapError as exc:
        raise UpstreamError(exc.message) from exc


class ServiceLayerDocumentRepository:
    def __init__(self, client: ServiceLayerClient, folder: AttachmentFolder | None = None):
        self._client = client
        self._folder = folder

    def search(self, query: DocumentQuery) -> list[DocumentRow]:
        doc_type = query.doc_type
        params = {
            "$select": ",".join(self._fields(doc_type)),
            "$filter": self._filter(query),
            "$orderby": "DocDate desc,DocEntry desc",
            "$top": str(query.limit),
            "$skip": str(query.offset),
        }
        # Sin este encabezado el Service Layer corta en 20 filas por respuesta.
        headers = {"Prefer": f"odata.maxpagesize={query.limit}"}
        with _sap_errors("Documento no encontrado."):
            body = self._client.get_json(doc_type.sl_entity, params, headers)
        return [self._document_row(doc_type, row) for row in body.get("value", [])]

    def get_document(self, doc_type: DocumentType, doc_entry: int) -> DocumentRow:
        path = f"{doc_type.sl_entity}({int(doc_entry)})"
        with _sap_errors("Documento no encontrado."):
            body = self._client.get_json(path, {"$select": ",".join(self._fields(doc_type))})
        return self._document_row(doc_type, body)

    def list_attachments(self, doc_type: DocumentType, doc_entry: int) -> list[AttachmentRow]:
        attachment_entry = self._attachment_entry(doc_type, doc_entry)
        if attachment_entry is None:
            return []
        return [row for row, _ in self._attachment_lines(attachment_entry)]

    @contextmanager
    def open_attachment(self, doc_type: DocumentType, doc_entry: int, line: int) -> Iterator[AttachmentFile]:
        attachment_entry = self._attachment_entry(doc_type, doc_entry)
        lines = self._attachment_lines(attachment_entry) if attachment_entry is not None else []
        if not 1 <= line <= len(lines):
            raise NotFoundError("Anexo no encontrado.")
        row, sap_file_name = lines[line - 1]
        if self._folder is not None:
            with self._folder.open(sap_file_name, row.file_name) as attachment:
                yield attachment
            return
        path = f"Attachments2({attachment_entry})/$value"
        with _sap_errors("SAP no entregó el archivo del anexo.", with_sap_detail=True):
            with self._client.stream(path, {"filename": odata_string(sap_file_name)}) as response:
                # Con Content-Encoding (gzip) el largo es el comprimido, no el del archivo.
                length = None if response.headers.get("Content-Encoding") else response.headers.get("Content-Length")
                yield AttachmentFile(
                    file_name=row.file_name,
                    content_type=mimetypes.guess_type(row.file_name)[0] or "application/octet-stream",
                    size_bytes=int(length) if length and length.isdigit() else None,
                    chunks=response.iter_bytes(DOWNLOAD_CHUNK_BYTES),
                )

    # --- Internos

    def _attachment_entry(self, doc_type: DocumentType, doc_entry: int) -> int | None:
        return self.get_document(doc_type, doc_entry).attachment_entry

    def _attachment_lines(self, attachment_entry: int) -> list[tuple[AttachmentRow, str]]:
        """(fila para el front, nombre del archivo tal como lo espera SAP)."""
        with _sap_errors("Los anexos del documento no existen en SAP."):
            body = self._client.get_json(f"Attachments2({int(attachment_entry)})")
        lines = []
        for position, item in enumerate(body.get("Attachments2_Lines", []), start=1):
            name, extension = item.get("FileName") or "", item.get("FileExtension") or ""
            sap_file_name = f"{name}.{extension}" if extension else name
            lines.append((AttachmentRow(position, safe_file_name(sap_file_name), _date(item.get("AttachmentDate"))),
                          sap_file_name))
        return lines

    @staticmethod
    def _fields(doc_type: DocumentType) -> list[str]:
        fields = ["DocEntry", "DocNum", "DocDate", "AttachmentEntry"]
        if NUM_AT_CARD in doc_type.criteria:
            fields.append("NumAtCard")
        if FOLIO in doc_type.criteria:
            fields += ["FolioPrefixString", "FolioNumber"]
        if doc_type.partner != "none":
            fields += ["CardCode", "CardName"]
        return fields

    @staticmethod
    def _filter(query: DocumentQuery) -> str:
        # Cada valor es int, date o texto escapado: nada llega crudo al $filter.
        if query.doc_entry is not None:
            return f"DocEntry eq {int(query.doc_entry)}"
        if query.doc_num is not None:
            return f"DocNum eq {int(query.doc_num)}"
        if query.num_at_card is not None:
            return f"NumAtCard eq {odata_string(query.num_at_card)}"
        if query.folio_prefix is not None:
            return (f"FolioPrefixString eq {odata_string(query.folio_prefix)}"
                    f" and FolioNumber eq {int(query.folio_number)}")
        conditions = []
        if query.card_code is not None:
            conditions.append(f"contains(CardCode, {odata_string(query.card_code)})")
        if query.card_name is not None:
            conditions.append(f"contains(CardName, {odata_string(query.card_name)})")
        conditions.append(f"DocDate ge {odata_date(query.date_from)}")
        conditions.append(f"DocDate le {odata_date(query.date_to)}")
        return " and ".join(conditions)

    @staticmethod
    def _document_row(doc_type: DocumentType, row: dict) -> DocumentRow:
        prefix, number = row.get("FolioPrefixString"), row.get("FolioNumber")
        return DocumentRow(
            type_code=doc_type.code,
            doc_entry=int(row["DocEntry"]),
            doc_num=row.get("DocNum"),
            num_at_card=row.get("NumAtCard"),
            folio=f"{prefix}-{number}" if prefix and number else None,
            card_code=row.get("CardCode"),
            card_name=row.get("CardName"),
            doc_date=_date(row.get("DocDate")),
            attachment_entry=int(row["AttachmentEntry"]) if row.get("AttachmentEntry") else None,
        )
