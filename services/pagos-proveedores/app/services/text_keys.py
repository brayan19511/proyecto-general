"""Claves para comparar documentos y nombres de proveedor (de proyecto-05, pdf_parser.py).

- document_key: RUC/DNI con solo alfanuméricos en mayúscula ("R - 20609307235"
  → "R20609307235"; "20-6093-07235" → "20609307235").
- name_key: nombre sin tildes, en mayúscula, sin puntuación y con espacios
  simples, para que "METEC CO., LIMITED" y "Metec Co. Limited" sean el mismo.

El lector de PDFs usa las mismas funciones para que la comparación coincida.
"""

import re
import unicodedata


def _without_accents(value: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", value) if unicodedata.category(c) != "Mn")


def document_key(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"[^0-9A-Z]", "", value.upper())


def name_key(value: str | None) -> str:
    if not value:
        return ""
    base = _without_accents(value).upper()
    base = re.sub(r"[^A-Z0-9 ]+", " ", base)
    return re.sub(r"\s+", " ", base).strip()
