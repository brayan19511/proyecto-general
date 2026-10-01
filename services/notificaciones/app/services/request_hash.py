"""Huella de una solicitud de envío para la idempotencia (acuerdo 2026-10-01).

SHA-256 de un JSON canónico (claves ordenadas, sin espacios) del payload, donde
cada referencia a un archivo ("f1") se reemplaza por su nombre y el SHA-256 de
su contenido. Así un reintento que nombre las partes de otra forma ("a", "b")
pero envíe lo mismo produce la misma huella; cambiar un byte de un adjunto, no.
"""

import hashlib
import json
from collections.abc import Mapping


def sha256_hex(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def compute_request_hash(payload: dict, files: Mapping[str, tuple[str, str]]) -> str:
    """payload: el JSON recibido. files: nombre de la parte → (nombre del archivo, sha256)."""
    canonical = dict(payload)
    canonical["messages"] = [
        {
            **message,
            "attachments": [
                {"filename": files[part][0], "sha256": files[part][1]} for part in message.get("attachments", [])
            ],
        }
        for message in payload.get("messages", [])
    ]
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return sha256_hex(encoded.encode("utf-8"))
