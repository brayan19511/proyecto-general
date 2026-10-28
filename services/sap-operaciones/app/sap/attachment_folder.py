"""Lectura de anexos SAP desde la carpeta de anexos montada en el contenedor.

Decisión del usuario (2026-10-28): el servidor del Service Layer (Linux) no
tiene montada \\\\10.0.0.13\\Anexo ("Fail to get the LINUX mount point"), así que
sap-operaciones lee el archivo de esa carpeta, montada en solo lectura en
SAP_ATTACHMENTS_DIR. Búsqueda y lista de anexos siguen por el Service Layer.

- El archivo es <carpeta de anexos>/<FileName>.<FileExtension> (ATC1.trgtPath).
  El SourcePath del Service Layer es la PC desde donde se subió: no sirve.
- Nunca se lista la carpeta (cientos de miles de archivos): se abre la ruta exacta.
- El nombre viene de SAP, pero igual se valida: sin separadores ni "..", y la
  ruta final debe quedar dentro de la carpeta montada.
- Solo anexos en la carpeta actual de SAP: si alguna vez cambió la carpeta de
  anexos en la configuración de SAP, los anteriores no estarían aquí.
"""

import mimetypes
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from app.documents.models import AttachmentFile
from app.services.errors import ConflictError, NotFoundError

CHUNK_BYTES = 64 * 1024


class AttachmentFolder:
    def __init__(self, base_dir: str):
        self._base = Path(base_dir).resolve()

    def _path(self, sap_file_name: str) -> Path:
        if not sap_file_name or any(sep in sap_file_name for sep in ("/", "\\", "\x00")) or sap_file_name in (".", ".."):
            raise NotFoundError("El nombre del anexo en SAP no es válido.")
        path = (self._base / sap_file_name).resolve()
        if path.parent != self._base:
            raise NotFoundError("El nombre del anexo en SAP no es válido.")
        return path

    @contextmanager
    def open(self, sap_file_name: str, file_name: str) -> Iterator[AttachmentFile]:
        """sap_file_name: tal como está en la carpeta; file_name: el saneado para la descarga."""
        if not self._base.is_dir():
            raise ConflictError("La carpeta de anexos no está montada en el servicio (SAP_ATTACHMENTS_DIR).")
        path = self._path(sap_file_name)
        try:
            handle = path.open("rb")
        except FileNotFoundError:
            raise NotFoundError("El archivo del anexo no está en la carpeta de anexos.") from None
        except OSError:
            raise ConflictError("No se pudo leer la carpeta de anexos.") from None
        with handle:
            size = path.stat().st_size

            def chunks() -> Iterator[bytes]:
                while data := handle.read(CHUNK_BYTES):
                    yield data

            yield AttachmentFile(
                file_name=file_name,
                content_type=mimetypes.guess_type(file_name)[0] or "application/octet-stream",
                size_bytes=size,
                chunks=chunks(),
            )
