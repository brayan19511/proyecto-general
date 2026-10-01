"""Purga del contenido de adjuntos (acuerdo 5 del alcance).

Cuando un mensaje termina (sent) o se cancela, sus bytes ya no hacen falta:
content pasa a NULL y se fija content_purged_at. La fila y sus metadatos
(nombre, tipo, tamaño, hash) se conservan: es un UPDATE, no un borrado de fila.
"""

from datetime import datetime

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models.entities import MessageAttachment


def purge_attachments(db: Session, message_id: str, *, now: datetime, actor_id: str) -> None:
    """Agrega la purga a la transacción en curso."""
    db.execute(
        update(MessageAttachment)
        .where(MessageAttachment.message_id == message_id, MessageAttachment.content_purged_at.is_(None))
        .values(content=None, content_purged_at=now, updated_at=now, updated_by=actor_id)
    )
