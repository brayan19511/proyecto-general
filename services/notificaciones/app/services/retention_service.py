"""Retención de mensajes fallidos o inciertos (acuerdos 5 y 9 del alcance).

Lo ejecuta el worker cada RETENTION_INTERVAL_SECONDS. Plazos desde
last_attempt_at, en UTC:

1. Cancelación (RETENTION_CANCEL_AFTER_HOURS, 72 h): failed/uncertain sin
   reproceso → cancelled (expired), adjuntos purgados, evento message.cancel.
   Se ejecuta primero: así no se avisa de algo que ya debía cancelarse (p. ej.
   si el worker estuvo detenido días).
2. Aviso (RETENTION_NOTICE_AFTER_HOURS, 48 h): por cada envío standard con
   mensajes así y con requester_email, un envío failure_notice con un correo al
   solicitante. Los mensajes avisados guardan notice_dispatch_id (no se vuelve
   a avisar de ellos; un reproceso lo limpia). El aviso sale por el flujo
   normal del worker; si falla no genera otro aviso, y la cancelación ocurre
   igual.

Varias réplicas no se pisan: los mensajes se toman con FOR UPDATE SKIP LOCKED.
Todo lo hace el actor de sistema notificaciones.retention (no un usuario).
"""

import logging
from datetime import timedelta
from itertools import groupby

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.common.mixin_model import new_id, utcnow
from app.models.entities import Dispatch, Message, SmtpAccount
from app.services.actors import RETENTION, system_actor_id
from app.services.attachment_purge import purge_attachments
from app.services.history import record_change
from app.services.message_builder import PLACEHOLDER_FROM, build_mime, mime_size
from app.services.notice_content import NoticeItem, build_notice
from app.services.recipients import Recipients, normalize_address
from app.services.request_hash import sha256_hex

logger = logging.getLogger("notificaciones.retention")

_WAITING = ("failed", "uncertain")
_BATCH = 500  # Mensajes por pasada: acota la transacción; lo que falte va en la siguiente.


def run(db: Session) -> tuple[int, int]:
    """(mensajes cancelados, avisos creados)."""
    return cancel_expired(db), create_notices(db)


def cancel_expired(db: Session) -> int:
    with db.begin():
        now = utcnow()
        limit = now - timedelta(hours=settings.RETENTION_CANCEL_AFTER_HOURS)
        messages = list(db.scalars(
            select(Message)
            .where(Message.status.in_(_WAITING), Message.last_attempt_at <= limit)
            .order_by(Message.last_attempt_at)
            .limit(_BATCH)
            .with_for_update(skip_locked=True)
        ))
        if not messages:
            return 0
        actor_id = system_actor_id(db, RETENTION)
        for message in messages:
            before = message.status
            message.status, message.cancelled_at, message.cancel_reason = "cancelled", now, "expired"
            message.next_attempt_at = None
            message.updated_at, message.updated_by = now, actor_id
            purge_attachments(db, message.id, now=now, actor_id=actor_id)
            record_change(
                db, action="message.cancel", resource_type="message", resource_id=message.id,
                company_id=message.company_id, actor_id=actor_id, now=now,
                before={"status": before}, after={"status": "cancelled", "cancel_reason": "expired"},
                reason=f"Sin reproceso {settings.RETENTION_CANCEL_AFTER_HOURS} h después del último intento.",
            )
        return len(messages)


def create_notices(db: Session) -> int:
    with db.begin():
        now = utcnow()
        limit = now - timedelta(hours=settings.RETENTION_NOTICE_AFTER_HOURS)
        rows = db.execute(
            select(Message, Dispatch)
            .join(Dispatch, Dispatch.id == Message.dispatch_id)
            .where(
                Message.status.in_(_WAITING),
                Message.last_attempt_at <= limit,
                Message.notice_dispatch_id.is_(None),
                Dispatch.kind == "standard",  # Nunca se avisa de un aviso.
                Dispatch.requester_email.is_not(None),
            )
            .order_by(Message.dispatch_id, Message.sequence)
            .limit(_BATCH)
            .with_for_update(of=Message, skip_locked=True)
        ).all()
        if not rows:
            return 0
        actor_id = system_actor_id(db, RETENTION)
        created = 0
        for _, group in groupby(rows, key=lambda row: row[1].id):
            group = list(group)
            original = group[0][1]
            messages = [message for message, _ in group]
            notice = _create_notice(db, original, messages, actor_id=actor_id, now=now)
            if notice is None:
                continue
            for message in messages:
                message.notice_dispatch_id = notice.id
                message.updated_at, message.updated_by = now, actor_id
            created += 1
        return created


def _create_notice(db: Session, original: Dispatch, messages: list[Message], *, actor_id: str, now):
    domain_email = db.scalar(
        select(SmtpAccount.from_email)
        .where(SmtpAccount.company_id == original.company_id, SmtpAccount.is_active.is_(True))
        .order_by(SmtpAccount.priority, SmtpAccount.created_at)
        .limit(1)
    )
    if domain_email is None:
        # Sin cuenta activa el aviso no podría salir. Se reintenta en la próxima
        # pasada (los mensajes siguen sin notice_dispatch_id); la cancelación sigue su plazo.
        logger.warning("Retención: envío %s sin cuenta SMTP activa; aviso pospuesto.", original.id)
        return None
    try:
        requester = normalize_address(original.requester_email)
    except Exception:  # noqa: BLE001 - email inválido en auth: no se puede avisar.
        logger.warning("Retención: envío %s con requester_email no válido; sin aviso.", original.id)
        return None

    first_attempt = min(m.last_attempt_at for m in messages)
    content = build_notice(
        dispatch_id=original.id, consumer=original.consumer, consumer_reference=original.consumer_reference,
        dispatch_created_at=original.created_at,
        items=[NoticeItem(m.to_addresses, m.subject, m.status) for m in messages],
        cancel_at=first_attempt + timedelta(hours=settings.RETENTION_CANCEL_AFTER_HOURS),
    )
    key = f"failure-notice:{original.id}:{now.isoformat()}"
    notice = Dispatch(
        company_id=original.company_id, kind="failure_notice", idempotency_key=key, request_hash=sha256_hex(key.encode()),
        consumer="notificaciones", consumer_reference=original.consumer_reference,
        notice_for_dispatch_id=original.id, created_at=now, created_by=actor_id,
    )
    db.add(notice)
    db.flush()

    recipients = Recipients(to=[requester], cc=[], bcc=[])
    message_id_header = f"<{new_id()}@{domain_email.rsplit('@', 1)[1]}>"
    mime = build_mime(
        from_header=PLACEHOLDER_FROM, recipients=recipients, reply_to=None, subject=content.subject,
        body_html=content.body_html, body_text=content.body_text, message_id=message_id_header, attachments=[],
    )
    db.add(Message(
        company_id=original.company_id, dispatch_id=notice.id, sequence=1, to_addresses=recipients.to,
        cc_addresses=[], bcc_addresses=[], subject=content.subject, body_html=content.body_html,
        body_text=content.body_text, message_id_header=message_id_header, size_bytes=mime_size(mime),
        status="pending", attempts_in_cycle=0, next_attempt_at=now, created_at=now, created_by=actor_id,
    ))
    record_change(
        db, action="dispatch.failure_notice", resource_type="dispatch", resource_id=notice.id,
        company_id=original.company_id, actor_id=actor_id, now=now, before={},
        after={"notice_for_dispatch_id": original.id, "messages": len(messages)},
    )
    return notice
