"""Descargas en CSV con la librería estándar (sin paquetes externos).

Mismo formato que el front (shared/utils/download.ts → toCsv): separador ";",
UTF-8 con BOM y saltos CRLF, para que Excel en español lo abra con tildes y
columnas separadas. Decisión del usuario (2026-10-04): todas las descargas en CSV.
"""

import csv
from collections.abc import Iterable, Sequence
from datetime import datetime
from io import StringIO
from urllib.parse import quote

from fastapi.responses import Response


def csv_response(filename: str, headers: Sequence[str], rows: Iterable[Sequence]) -> Response:
    buffer = StringIO()
    writer = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
    writer.writerow(headers)
    for row in rows:
        writer.writerow([_cell(value) for value in row])
    ascii_name = filename.encode("ascii", "ignore").decode() or "descarga.csv"
    return Response(
        content="﻿" + buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"},
    )


def _cell(value):
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")  # Excel la reconoce como fecha y hora.
    if isinstance(value, bool):
        return "Sí" if value else "No"
    return value
