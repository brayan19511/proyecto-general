"""Enmascarado y límites: qué se puede guardar de una solicitud.

Qué es sensible lo deciden dos listas de config.py (o las que pase cada
servicio en AuditConfig):
  - sensitive_keys: nombres exactos ("email", "api_key").
  - sensitive_key_parts: fragmentos; si el nombre CONTIENE uno, se oculta
    ("password" oculta "new_password" y "passwordHash").

Las comparaciones ignoran mayúsculas y acentos: "Contraseña", "CONTRASENA" y
"contraseña" son lo mismo. Los valores sensibles se guardan como "***".
Los bodies grandes o que no son JSON no se guardan, solo su tipo y tamaño.
"""

import json
import unicodedata
from dataclasses import dataclass
from urllib.parse import parse_qsl

MASK = "***"


def normalize(name: str) -> str:
    """Minúsculas y sin acentos: "Contraseña" → "contrasena"."""
    decomposed = unicodedata.normalize("NFKD", str(name))
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).lower().strip()


@dataclass(frozen=True)
class Masker:
    """Decide y aplica el enmascarado con las listas ya normalizadas."""

    keys: frozenset[str]
    parts: frozenset[str]

    @classmethod
    def from_lists(cls, keys, parts) -> "Masker":
        return cls(
            keys=frozenset(normalize(k) for k in keys),
            parts=frozenset(normalize(p) for p in parts if p),
        )

    def is_sensitive(self, name: str) -> bool:
        key = normalize(name)
        return key in self.keys or any(part in key for part in self.parts)

    def redact(self, value):
        """Recorre dicts y listas enmascarando los valores de claves sensibles."""
        if isinstance(value, dict):
            return {
                k: MASK if self.is_sensitive(k) else self.redact(v)
                for k, v in value.items()
            }
        if isinstance(value, list):
            return [self.redact(item) for item in value]
        return value


def safe_headers(headers: dict[str, str], allowed: frozenset[str], masker: Masker) -> dict:
    return {
        name: (MASK if masker.is_sensitive(name) else value)
        for name, value in headers.items()
        if name in allowed
    }


def safe_query(query_string: bytes, masker: Masker) -> dict:
    params = dict(parse_qsl(query_string.decode("latin-1"), keep_blank_values=True))
    return masker.redact(params)


def safe_body(raw: bytes, content_type: str, truncated: bool, limit: int, masker: Masker):
    """JSON enmascarado si cabe en el límite; si no, solo metadatos."""
    # Primero el tamaño: un body truncado puede no haber guardado ningún byte.
    if truncated or len(raw) > limit:
        return {"omitted": "too_large", "limit_bytes": limit}
    if not raw:
        return None
    if "json" not in content_type:
        return {"omitted": content_type or "unknown", "size_bytes": len(raw)}
    try:
        parsed = json.loads(raw)
    except ValueError:
        return {"omitted": "invalid_json", "size_bytes": len(raw)}
    return masker.redact(parsed)
