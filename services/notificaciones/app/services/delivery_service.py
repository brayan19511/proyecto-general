"""Entrega de mensajes por SMTP (lo usa el worker, app/worker.py).

Ciclo de un mensaje (acuerdos de docs/modelo-datos.md):

1. claim_next: toma UN mensaje pending/retrying vencido con FOR UPDATE SKIP
   LOCKED (varios workers no toman el mismo), lo pasa a sending con un bloqueo
   (locked_until) y confirma. El envío ocurre FUERA de esa transacción: no se
   mantiene una conexión a la base abierta mientras se habla con el servidor.
2. deliver: prueba las cuentas activas de la empresa por prioridad. Pasa a la
   siguiente solo si falló ANTES de que el servidor aceptara el mensaje
   (conexión, TLS, autenticación, remitente o destinatarios rechazados con 4xx,
   DATA rechazado). Un rechazo 5xx de destinatarios o del contenido es
   permanente: otra cuenta no lo arregla. Un corte durante DATA deja el
   mensaje uncertain: no se sabe si salió y no se reenvía solo.
3. finish: guarda el resultado, una fila de intento por cuenta probada y, si se
   envió, purga el contenido de sus adjuntos. Sin éxito ni error permanente:
   retrying con espera (RETRY_DELAYS_SECONDS) hasta agotar los reintentos;
   después, failed.

mark_expired_locks: un mensaje que sigue en sending con el bloqueo vencido
pasa a uncertain (el worker pudo morir después de transmitirlo).
"""

import logging
import smtplib
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from email.policy import SMTP
from email.utils import formataddr

from platform_audit import step
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.crypto import SecretDecryptionError, decrypt_secret
from app.models.common.mixin_model import utcnow
from app.models.entities import Message, MessageAttachment, MessageAttempt, SmtpAccount
from app.services.actors import WORKER, system_actor_id
from app.services.attachment_purge import purge_attachments
from app.services.message_builder import Attachment, build_mime
from app.services.recipients import Recipients
from app.services.smtp_transport import SmtpEndpoint, classify_error, open_connection

logger = logging.getLogger("notificaciones.delivery")


@dataclass
class _Try:
    """Resultado de probar una cuenta (se guarda como un MessageAttempt)."""

    smtp_account_id: str | None
    started_at: datetime
    finished_at: datetime | None = None
    outcome: str = "transient_error"  # sent | transient_error | permanent_error | uncertain | no_account
    smtp_code: int | None = None
    error_kind: str | None = None
    smtp_response: str | None = None


@dataclass
class _Delivery:
    tries: list[_Try] = field(default_factory=list)

    @property
    def outcome(self) -> str:
        return self.tries[-1].outcome if self.tries else "no_account"


class _PermanentRejection(Exception):
    def __init__(self, kind: str, code: int | None, response: str | None):
        self.kind, self.code, self.response = kind, code, response


class _Uncertain(Exception):
    pass


def _response_text(value) -> str | None:
    if value is None:
        return None
    text = value.decode("utf-8", "replace") if isinstance(value, bytes) else str(value)
    return text[:500]


# --- 1. Tomar trabajo ----------------------------------------------------------


def mark_expired_locks(db: Session) -> int:
    """sending con bloqueo vencido → uncertain, con su intento registrado."""
    with db.begin():
        now = utcnow()
        expired = list(db.scalars(
            select(Message).where(Message.status == "sending", Message.locked_until < now)
            .with_for_update(skip_locked=True)
        ))
        if not expired:
            return 0
        actor_id = system_actor_id(db, WORKER)
        for message in expired:
            db.add(MessageAttempt(
                company_id=message.company_id, message_id=message.id,
                attempt_number=_next_attempt_number(db, message.id), started_at=now, finished_at=now,
                outcome="uncertain", error_kind="worker_interrupted", created_at=now, created_by=actor_id,
            ))
            message.status, message.locked_until, message.locked_by = "uncertain", None, None
            message.last_attempt_at, message.next_attempt_at = now, None
            message.updated_at, message.updated_by = now, actor_id
            logger.warning("Mensaje %s: bloqueo vencido en sending, queda uncertain.", message.id)
        return len(expired)


def claim_next(db: Session, worker_id: str) -> str | None:
    """Toma un mensaje listo para enviar; devuelve su id o None si no hay."""
    with db.begin():
        now = utcnow()
        message = db.scalar(
            select(Message)
            .where(Message.status.in_(("pending", "retrying")), Message.next_attempt_at <= now)
            .order_by(Message.next_attempt_at, Message.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if message is None:
            return None
        actor_id = system_actor_id(db, WORKER)
        message.status = "sending"
        message.locked_by = worker_id
        message.locked_until = now + timedelta(seconds=settings.WORKER_LOCK_SECONDS)
        message.attempts_in_cycle += 1
        message.updated_at, message.updated_by = now, actor_id
        return message.id


def _next_attempt_number(db: Session, message_id: str) -> int:
    current = db.scalar(select(func.max(MessageAttempt.attempt_number)).where(MessageAttempt.message_id == message_id))
    return (current or 0) + 1


# --- 2. Enviar -----------------------------------------------------------------


@dataclass(frozen=True)
class _Snapshot:
    """Lo necesario para enviar, leído antes de salir de la transacción."""

    message_id: str
    company_id: str
    recipients: Recipients
    reply_to: str | None
    subject: str
    body_html: str | None
    body_text: str | None
    message_id_header: str
    attachments: list[Attachment]
    accounts: list[tuple[str, SmtpEndpoint, str | None, str | None, str, str | None]]


def _load(db: Session, message_id: str) -> _Snapshot:
    with db.begin():
        message = db.get(Message, message_id)
        attachments = db.scalars(
            select(MessageAttachment).where(MessageAttachment.message_id == message_id)
            .order_by(MessageAttachment.sequence)
        )
        accounts = db.scalars(
            select(SmtpAccount)
            .where(SmtpAccount.company_id == message.company_id, SmtpAccount.is_active.is_(True))
            .order_by(SmtpAccount.priority, SmtpAccount.created_at)
        )
        return _Snapshot(
            message_id=message.id, company_id=message.company_id,
            recipients=Recipients(message.to_addresses, message.cc_addresses, message.bcc_addresses),
            reply_to=message.reply_to, subject=message.subject,
            body_html=message.body_html, body_text=message.body_text, message_id_header=message.message_id_header,
            attachments=[Attachment(a.filename, a.content_type, a.content) for a in attachments],
            accounts=[
                (
                    a.id, SmtpEndpoint(a.host, a.port, a.security, a.timeout_seconds),
                    a.username, a.password_encrypted, a.from_email, a.from_name,
                )
                for a in accounts
            ],
        )


def _send_with_account(snapshot: _Snapshot, account, attempt: _Try) -> None:
    """Envía con una cuenta. Sin excepción = aceptado. Lanza _PermanentRejection,
    _Uncertain o cualquier otra (fallo previo a la aceptación: probar otra cuenta)."""
    account_id, endpoint, username, encrypted, from_email, from_name = account
    password = decrypt_secret(encrypted) if encrypted is not None else None
    mime = build_mime(
        from_header=formataddr((from_name, from_email)) if from_name else from_email,
        recipients=snapshot.recipients, reply_to=snapshot.reply_to, subject=snapshot.subject,
        body_html=snapshot.body_html, body_text=snapshot.body_text,
        message_id=snapshot.message_id_header, attachments=snapshot.attachments,
    )
    smtp = open_connection(endpoint, username, password)
    try:
        # MAIL FROM y RCPT TO por separado: así se sabe si un fallo fue antes de DATA.
        code, response = smtp.mail(from_email)
        if code != 250:
            raise smtplib.SMTPSenderRefused(code, response, from_email)
        refused = {}
        for address in snapshot.recipients.all:
            code, response = smtp.rcpt(address)
            if code not in (250, 251):
                refused[address] = (code, response)
        if len(refused) == len(snapshot.recipients.all):
            codes = {code for code, _ in refused.values()}
            if all(500 <= code < 600 for code in codes):
                raise _PermanentRejection("recipients_refused", max(codes), _refused_text(refused))
            raise smtplib.SMTPRecipientsRefused(refused)  # 4xx: otra cuenta o reintento.
        try:
            code, response = smtp.data(mime.as_bytes(policy=SMTP))
        except smtplib.SMTPDataError as error:
            if 500 <= error.smtp_code < 600:
                raise _PermanentRejection("data_rejected", error.smtp_code, _response_text(error.smtp_error))
            raise  # 4xx: el servidor no lo aceptó; se puede probar otra cuenta.
        except (smtplib.SMTPServerDisconnected, TimeoutError, OSError) as error:
            raise _Uncertain() from error  # Cortado durante DATA: pudo haberse entregado.
        attempt.smtp_code = code
        if refused:
            attempt.smtp_response = f"Aceptado; rechazados: {_refused_text(refused)}"[:500]
        else:
            attempt.smtp_response = _response_text(response)
    finally:
        try:
            smtp.quit()
        except Exception:  # noqa: BLE001 - el resultado ya está decidido.
            smtp.close()


def _refused_text(refused: dict) -> str:
    return ", ".join(f"{address} ({code})" for address, (code, _) in refused.items())[:500]


def deliver(snapshot: _Snapshot) -> _Delivery:
    delivery = _Delivery()
    if not snapshot.accounts:
        delivery.tries.append(_Try(None, utcnow(), utcnow(), outcome="no_account", error_kind="no_account"))
        return delivery
    for account in snapshot.accounts:
        attempt = _Try(smtp_account_id=account[0], started_at=utcnow())
        delivery.tries.append(attempt)
        try:
            _send_with_account(snapshot, account, attempt)
            attempt.outcome = "sent"
            return delivery
        except _PermanentRejection as error:
            attempt.outcome, attempt.error_kind = "permanent_error", error.kind
            attempt.smtp_code, attempt.smtp_response = error.code, error.response
            return delivery
        except _Uncertain:
            attempt.outcome, attempt.error_kind = "uncertain", "interrupted_during_data"
            return delivery
        # Desde aquí: falló antes de que el servidor aceptara el mensaje → siguiente cuenta.
        except SecretDecryptionError:
            attempt.error_kind = "credentials_unreadable"
        except smtplib.SMTPSenderRefused as error:  # La cuenta no puede enviar como from_email.
            attempt.error_kind = "sender_refused"
            attempt.smtp_code, attempt.smtp_response = error.smtp_code, _response_text(error.smtp_error)
        except smtplib.SMTPResponseException as error:  # Auth, DATA 4xx u otro rechazo con código.
            attempt.error_kind = classify_error(error)
            attempt.smtp_code, attempt.smtp_response = error.smtp_code, _response_text(error.smtp_error)
        except smtplib.SMTPRecipientsRefused as error:  # Todos rechazados con 4xx.
            attempt.error_kind = "recipients_refused"
            attempt.smtp_response = _refused_text(error.recipients)
        except Exception as error:  # noqa: BLE001 - conexión, TLS, timeout, dirección bloqueada…
            attempt.error_kind = classify_error(error)
        finally:
            attempt.finished_at = utcnow()
    return delivery  # Todas las cuentas fallaron antes de la aceptación: transitorio.


# --- 3. Guardar el resultado ---------------------------------------------------


def finish(db: Session, message_id: str, delivery: _Delivery) -> str:
    """Aplica el resultado; devuelve el estado final del mensaje."""
    with db.begin():
        now = utcnow()
        actor_id = system_actor_id(db, WORKER)
        message = db.get(Message, message_id, with_for_update=True)
        number = _next_attempt_number(db, message_id)
        for attempt in delivery.tries:
            db.add(MessageAttempt(
                company_id=message.company_id, message_id=message_id, attempt_number=number,
                smtp_account_id=attempt.smtp_account_id, started_at=attempt.started_at,
                finished_at=attempt.finished_at or now, outcome=attempt.outcome, smtp_code=attempt.smtp_code,
                error_kind=attempt.error_kind, smtp_response=attempt.smtp_response,
                created_at=now, created_by=actor_id,
            ))

        outcome = delivery.outcome
        message.locked_until = message.locked_by = None
        message.last_attempt_at = now
        message.updated_at, message.updated_by = now, actor_id
        if outcome == "sent":
            message.status, message.sent_at, message.next_attempt_at = "sent", now, None
            purge_attachments(db, message_id, now=now, actor_id=actor_id)
        elif outcome == "permanent_error":
            message.status, message.next_attempt_at = "failed", None
        elif outcome == "uncertain":
            message.status, message.next_attempt_at = "uncertain", None
        else:  # transient_error / no_account
            retries_done = message.attempts_in_cycle - 1
            if retries_done < len(settings.RETRY_DELAYS_SECONDS):
                delay = settings.RETRY_DELAYS_SECONDS[retries_done]
                message.status, message.next_attempt_at = "retrying", now + timedelta(seconds=delay)
            else:
                message.status, message.next_attempt_at = "failed", None
        return message.status


def process(db: Session, message_id: str) -> str:
    with step("message.deliver"):
        snapshot = _load(db, message_id)
        delivery = deliver(snapshot)
        status = finish(db, message_id, delivery)
    logger.info("Mensaje %s: %s (%s cuenta(s) probada(s)).", message_id, status, len(delivery.tries))
    return status
