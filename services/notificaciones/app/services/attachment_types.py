"""Tipos de adjunto permitidos, reconocidos por su contenido (acuerdo 2026-10-01).

Lista positiva: PDF, PNG, JPEG, GIF, Excel (xlsx, xls), Word (docx, doc), ZIP,
CSV y TXT. Se usa una tabla propia de firmas (los primeros bytes de cada
formato) en lugar de una librería: la lista es corta y así no hay dependencia
de sistema (libmagic).

- La extensión del nombre debe coincidir con el contenido: un "factura.pdf"
  que en realidad es un ZIP se rechaza.
- El content_type que se guarda es el detectado, nunca el que declara el cliente.
- xlsx/docx son ZIP: se distinguen por la lista de archivos internos, sin
  descomprimir nada (sin riesgo de bombas ZIP).
- xls/doc antiguos comparten formato (OLE2): ambos se aceptan con esa firma y
  su extensión decide el tipo.
- CSV/TXT no tienen firma: se exige texto (sin bytes de control salvo
  tabulador, salto de línea y retorno de carro).
"""

import unicodedata
import zipfile
from io import BytesIO

from app.services.errors import InvalidDataError

_PNG = b"\x89PNG\r\n\x1a\n"
_JPEG = b"\xff\xd8\xff"
_GIF = (b"GIF87a", b"GIF89a")
_OLE2 = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"  # .doc / .xls anteriores a 2007.
_TEXT_CONTROL_ALLOWED = {0x09, 0x0A, 0x0C, 0x0D}  # \t \n \f \r


def _is_pdf(content: bytes) -> bool:
    # La especificación admite basura antes de la cabecera (hasta 1024 bytes).
    return b"%PDF-" in content[:1024]


def _zip_names(content: bytes) -> list[str] | None:
    """Lista de archivos internos de un ZIP (solo el índice), o None si no es ZIP."""
    if not content.startswith(b"PK\x03\x04"):
        return None
    try:
        with zipfile.ZipFile(BytesIO(content)) as archive:
            return archive.namelist()
    except zipfile.BadZipFile:
        return None


def _is_text(content: bytes) -> bool:
    return all(byte >= 0x20 or byte in _TEXT_CONTROL_ALLOWED for byte in content)


def _text_type(base: str, content: bytes) -> str:
    try:
        content.decode("utf-8")
        charset = "utf-8"
    except UnicodeDecodeError:
        charset = "windows-1252"  # Habitual en CSV exportados desde Excel en Windows.
    return f"{base}; charset={charset}"


def detect_content_type(filename: str, content: bytes) -> str:
    """content_type para guardar y enviar. InvalidDataError si el tipo no se admite
    o la extensión no coincide con el contenido."""
    if not content:
        raise InvalidDataError(f"{filename}: el archivo está vacío.")
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if extension == "pdf" and _is_pdf(content):
        return "application/pdf"
    if extension == "png" and content.startswith(_PNG):
        return "image/png"
    if extension in ("jpg", "jpeg") and content.startswith(_JPEG):
        return "image/jpeg"
    if extension == "gif" and content.startswith(_GIF):
        return "image/gif"
    if extension == "xls" and content.startswith(_OLE2):
        return "application/vnd.ms-excel"
    if extension == "doc" and content.startswith(_OLE2):
        return "application/msword"
    if extension in ("xlsx", "docx", "zip"):
        names = _zip_names(content)
        if names is not None:
            if extension == "xlsx" and "xl/workbook.xml" in names:
                return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            if extension == "docx" and "word/document.xml" in names:
                return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            if extension == "zip":
                return "application/zip"
    if extension in ("csv", "txt") and _is_text(content):
        return _text_type("text/csv" if extension == "csv" else "text/plain", content)

    raise InvalidDataError(
        f"{filename}: tipo no permitido o el contenido no coincide con la extensión. "
        "Permitidos: pdf, png, jpg, gif, xlsx, xls, docx, doc, zip, csv, txt.",
        code="attachment_type_not_allowed",
    )


def sanitize_filename(raw: str | None) -> str:
    """Nombre seguro para el adjunto: sin rutas, sin caracteres de control y con
    extensión. "../../x.pdf" → "x.pdf". InvalidDataError si queda vacío o sin extensión."""
    name = unicodedata.normalize("NFC", raw or "")
    name = name.replace("\\", "/").rsplit("/", 1)[-1]  # Solo el último tramo de una ruta.
    name = "".join(ch for ch in name if unicodedata.category(ch)[0] != "C")  # Controles, formato.
    name = name.strip().strip(".").strip()
    if "." not in name or not name.rsplit(".", 1)[0] or not name.rsplit(".", 1)[1]:
        raise InvalidDataError(f"Nombre de archivo no válido: {raw!r}. Debe tener nombre y extensión.")
    if len(name) > 255:
        stem, extension = name.rsplit(".", 1)
        name = f"{stem[: 254 - len(extension)]}.{extension}"
    return name
