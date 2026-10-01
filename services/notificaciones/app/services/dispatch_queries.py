"""Consultas de envíos, mensajes, adjuntos e intentos (solo lectura).

Alcance (Access.scope, app/api/dependencies.py):
- company: todo lo de la empresa validada por auth.
- own: solo los envíos con created_by = el actor del usuario. Los avisos previos
  (failure_notice) los crea un proceso de sistema: solo se ven con company.
Fuera del alcance o de otra empresa: NotFoundError (404), igual que inexistente.

El estado del envío no es columna: el filtro status se traduce a EXISTS sobre
sus mensajes, así la paginación y el total siguen siendo exactos.
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import and_, exists, func, not_, select
from sqlalchemy.orm import Session

from app.api.dependencies import Access
from app.core.permissions import CAN_ADMIN
from app.models.entities import Actor, Dispatch, Message, MessageAttachment, MessageAttempt, SmtpAccount
from app.schemas.messages import AttachmentOut, AttemptOut, MessageDetailOut, MessageSummaryOut, MessageTechnicalOut
from app.services.errors import GoneError, NotFoundError

_IN_PROGRESS = ("pending", "sending", "retrying")
_WITH_ERRORS = ("failed", "uncertain", "cancelled")


@dataclass(frozen=True)
class DispatchFilters:
    status: str | None = None
    consumer: str | None = None
    consumer_reference: str | None = None
    kind: str | None = None
    created_from: datetime | None = None
    created_to: datetime | None = None
    requested_by_user_id: str | None = None  # Usuario de auth que lo solicitó.
    requester_email: str | None = None  # Parte del correo del solicitante (sin distinguir mayúsculas).


def _escape_like(text: str) -> str:
    """El texto buscado es literal: % y _ no actúan como comodines."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _messages_of_dispatch(*conditions):
    return exists().where(Message.dispatch_id == Dispatch.id, *conditions)


def _status_condition(status: str):
    """Mismas reglas que dispatch_progress.derive_status, escritas como EXISTS."""
    if status == "pending":
        return not_(_messages_of_dispatch(Message.status != "pending"))
    if status == "in_progress":
        return and_(
            _messages_of_dispatch(Message.status.in_(_IN_PROGRESS)),
            _messages_of_dispatch(Message.status != "pending"),
        )
    if status == "completed":
        # Al menos un mensaje: un envío vacío cuenta como pending, igual que en derive_status.
        return and_(_messages_of_dispatch(), not_(_messages_of_dispatch(Message.status != "sent")))
    # completed_with_errors
    return and_(
        not_(_messages_of_dispatch(Message.status.in_(_IN_PROGRESS))),
        _messages_of_dispatch(Message.status.in_(_WITH_ERRORS)),
    )


class DispatchQueries:
    def __init__(self, db: Session):
        self.db = db

    # --- Alcance ---------------------------------------------------------

    def _scope_conditions(self, access: Access) -> list | None:
        """Condiciones sobre Dispatch según el alcance; None si own y el usuario
        nunca operó aquí (no tiene actor, así que no tiene envíos)."""
        conditions = [Dispatch.company_id == access.ctx.company_id]
        if access.scope == "own":
            actor_id = self.db.scalar(
                select(Actor.id).where(Actor.kind == "user", Actor.subject_ref == access.ctx.user_id)
            )
            if actor_id is None:
                return None
            conditions.append(Dispatch.created_by == actor_id)
        return conditions

    def find_dispatch(self, access: Access, dispatch_id: str) -> Dispatch:
        conditions = self._scope_conditions(access)
        dispatch = None
        if conditions is not None:
            dispatch = self.db.scalar(select(Dispatch).where(Dispatch.id == dispatch_id, *conditions))
        if dispatch is None:
            raise NotFoundError("Envío no encontrado.")
        return dispatch

    def find_message(self, access: Access, message_id: str) -> Message:
        conditions = self._scope_conditions(access)
        message = None
        if conditions is not None:
            message = self.db.scalar(
                select(Message).join(Dispatch, Dispatch.id == Message.dispatch_id)
                .where(Message.id == message_id, Message.company_id == access.ctx.company_id, *conditions)
            )
        if message is None:
            raise NotFoundError("Mensaje no encontrado.")
        return message

    # --- Envíos ----------------------------------------------------------

    def list_dispatches(
        self, access: Access, filters: DispatchFilters, *, limit: int, offset: int
    ) -> tuple[list[Dispatch], int]:
        with self.db.begin():
            conditions = self._scope_conditions(access)
            if conditions is None:
                return [], 0
            if filters.status:
                conditions.append(_status_condition(filters.status))
            if filters.consumer:
                conditions.append(Dispatch.consumer == filters.consumer)
            if filters.consumer_reference:
                conditions.append(Dispatch.consumer_reference == filters.consumer_reference)
            if filters.kind:
                conditions.append(Dispatch.kind == filters.kind)
            if filters.created_from:
                conditions.append(Dispatch.created_at >= filters.created_from)
            if filters.created_to:
                conditions.append(Dispatch.created_at < filters.created_to)
            if filters.requested_by_user_id:
                # El solicitante es el actor de created_by; con alcance own se
                # suma a la condición de propios (otro usuario → lista vacía).
                conditions.append(
                    Dispatch.created_by.in_(
                        select(Actor.id).where(Actor.kind == "user", Actor.subject_ref == filters.requested_by_user_id)
                    )
                )
            if filters.requester_email:
                pattern = "%" + _escape_like(filters.requester_email.strip().lower()) + "%"
                conditions.append(func.lower(Dispatch.requester_email).like(pattern, escape="\\"))
            total = self.db.scalar(select(func.count()).select_from(Dispatch).where(*conditions))
            rows = self.db.scalars(
                select(Dispatch).where(*conditions)
                .order_by(Dispatch.created_at.desc(), Dispatch.id.desc()).limit(limit).offset(offset)
            )
            return list(rows), total

    def get_dispatch(self, access: Access, dispatch_id: str) -> Dispatch:
        with self.db.begin():
            return self.find_dispatch(access, dispatch_id)

    def list_messages(
        self, access: Access, dispatch_id: str, *, status: str | None, limit: int, offset: int
    ) -> tuple[list[MessageSummaryOut], int]:
        with self.db.begin():
            dispatch = self.find_dispatch(access, dispatch_id)
            conditions = [Message.dispatch_id == dispatch.id]
            if status:
                conditions.append(Message.status == status)
            total = self.db.scalar(select(func.count()).select_from(Message).where(*conditions))
            rows = self.db.scalars(
                select(Message).where(*conditions).order_by(Message.sequence).limit(limit).offset(offset)
            )
            return [summary(m) for m in rows], total

    # --- Mensajes --------------------------------------------------------

    def get_message(self, access: Access, message_id: str) -> MessageDetailOut:
        with self.db.begin():
            message = self.find_message(access, message_id)
            # content es deferred: aquí no se leen los bytes de los adjuntos.
            attachments = self.db.scalars(
                select(MessageAttachment).where(MessageAttachment.message_id == message.id)
                .order_by(MessageAttachment.sequence)
            )
            is_admin = access.ctx.scope_for(CAN_ADMIN) == "company"
            return MessageDetailOut(
                **summary(message).model_dump(),
                dispatch_id=message.dispatch_id, reply_to=message.reply_to,
                body_html=message.body_html, body_text=message.body_text, cancel_reason=message.cancel_reason,
                attachments=[
                    AttachmentOut(
                        id=a.id, sequence=a.sequence, filename=a.filename, content_type=a.content_type,
                        size_bytes=a.size_bytes, available=a.content_purged_at is None,
                    )
                    for a in attachments
                ],
                created_at=message.created_at,
                technical=MessageTechnicalOut(
                    message_id_header=message.message_id_header, size_bytes=message.size_bytes,
                    next_attempt_at=message.next_attempt_at, locked_until=message.locked_until,
                ) if is_admin else None,
            )

    def get_attachment(self, access: Access, message_id: str, attachment_id: str) -> tuple[str, str, bytes]:
        """(filename, content_type, bytes). 410 si el contenido ya se purgó."""
        with self.db.begin():
            message = self.find_message(access, message_id)
            attachment = self.db.scalar(
                select(MessageAttachment).where(
                    MessageAttachment.id == attachment_id, MessageAttachment.message_id == message.id
                )
            )
            if attachment is None:
                raise NotFoundError("Adjunto no encontrado.")
            if attachment.content_purged_at is not None:
                raise GoneError("El contenido del adjunto ya se eliminó (el mensaje terminó o se canceló).")
            return attachment.filename, attachment.content_type, attachment.content

    def list_attempts(self, access: Access, message_id: str) -> list[AttemptOut]:
        with self.db.begin():
            message = self.find_message(access, message_id)
            rows = self.db.execute(
                select(MessageAttempt, SmtpAccount.name)
                .outerjoin(SmtpAccount, SmtpAccount.id == MessageAttempt.smtp_account_id)
                .where(MessageAttempt.message_id == message.id)
                .order_by(MessageAttempt.attempt_number, MessageAttempt.started_at)
            )
            return [
                AttemptOut(
                    id=a.id, attempt_number=a.attempt_number, smtp_account_id=a.smtp_account_id,
                    smtp_account_name=name, started_at=a.started_at, finished_at=a.finished_at,
                    outcome=a.outcome, smtp_code=a.smtp_code, error_kind=a.error_kind,
                    smtp_response=a.smtp_response,
                )
                for a, name in rows
            ]


def summary(message: Message) -> MessageSummaryOut:
    return MessageSummaryOut(
        id=message.id, sequence=message.sequence, consumer_reference=message.consumer_reference,
        to=message.to_addresses, cc=message.cc_addresses, bcc=message.bcc_addresses, subject=message.subject,
        status=message.status, attempts_in_cycle=message.attempts_in_cycle,
        last_attempt_at=message.last_attempt_at, sent_at=message.sent_at, cancelled_at=message.cancelled_at,
    )
