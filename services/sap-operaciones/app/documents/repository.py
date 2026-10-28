"""Repositorio de documentos SAP: lo que el servicio necesita de la fuente.

Patrón repository: el servicio (validar permisos, empresa, registrar descargas)
solo usa esta interfaz. Hoy la implementa ServiceLayerDocumentRepository
(app/sap/sl_document_repository.py); cambiar a HANA + carpeta compartida sería
escribir otra implementación con los mismos métodos, sin tocar el servicio
ni el contrato HTTP.

Las credenciales y la conexión no forman parte de la interfaz: cada
implementación las recibe al construirse (Service Layer: URL, base y usuario
SAP; HANA: engine de solo lectura y carpeta de anexos).

Errores: lanzan los de app/services/errors.py (NotFoundError, UpstreamError,
...), nunca errores propios de la fuente.
"""

from contextlib import AbstractContextManager
from typing import Protocol

from app.documents.catalog import DocumentType
from app.documents.models import AttachmentFile, AttachmentRow, DocumentQuery, DocumentRow


class DocumentRepository(Protocol):
    def search(self, query: DocumentQuery) -> list[DocumentRow]:
        """Documentos que cumplen la búsqueda (una página, más recientes primero)."""
        ...

    def get_document(self, doc_type: DocumentType, doc_entry: int) -> DocumentRow:
        """Cabecera del documento. NotFoundError si no existe."""
        ...

    def list_attachments(self, doc_type: DocumentType, doc_entry: int) -> list[AttachmentRow]:
        """Anexos del documento; lista vacía si no tiene. NotFoundError si el documento no existe."""
        ...

    def open_attachment(self, doc_type: DocumentType, doc_entry: int, line: int) -> AbstractContextManager[AttachmentFile]:
        """Abre un anexo para enviarlo por partes; al salir del with se cierra la conexión.

        El archivo se resuelve desde el documento (nunca desde una ruta enviada
        por el cliente). NotFoundError si el documento o la línea no existen.
        """
        ...
