"""Reproceso y cancelación manuales (docs/api.md, acuerdo 5 del contrato).

- Reprocesar: solo failed o uncertain → pending, con attempts_in_cycle en 0
  (vuelve a tener sus 3 reintentos automáticos) y sin aviso previo registrado
  (notice_dispatch_id en NULL: el plazo de 2 y 3 días vuelve a empezar cuando
  falle de nuevo). El contenido no se edita: para corregir, otro envío.
- Cancelar: pending, retrying, failed o uncertain → cancelled (manual) y se
  purgan sus adjuntos. No se puede cancelar un mensaje en sending (el worker
  lo está enviando), sent ni cancelled: 409.
- Cada acción queda en change_history con el estado anterior y el nuevo, y el
  motivo opcional (reason) de quien actúa.

Concurrencia con el worker: el mensaje se relee con FOR UPDATE. Si el worker
lo estaba tomando, se espera a que confirme y se ve ya en sending (409).
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import Access
from app.models.common.mixin_model import utcnow
from app.models.entities import Message
from app.schemas.messages import MessageSummaryOut
from app.services.actors import user_actor_id
from app.services.attachment_purge import purge_attachments
from app.services.dispatch_queries import DispatchQueries, summary
from app.services.errors import ConflictError
from app.services.history import record_change

RETRYABLE = ("failed", "uncertain")
CANCELLABLE = ("pending", "retrying", "failed", "uncertain")


class MessageActions:
    def __init__(self, db: Session):
        self.db = db
        self.queries = DispatchQueries(db)

    def retry(self, access: Access, message_id: str, *, reason: str | None) -> MessageSummaryOut:
        with self.db.begin():
            message = self._locked(access, message_id)
            if message.status not in RETRYABLE:
                raise ConflictError(
                    f"Solo se reprocesan mensajes failed o uncertain (este está {message.status}).",
                    code="invalid_status",
                )
            self._requeue(access, message, reason=reason)
            return summary(message)

    def cancel(self, access: Access, message_id: str, *, reason: str | None) -> MessageSummaryOut:
        with self.db.begin():
            message = self._locked(access, message_id)
            if message.status not in CANCELLABLE:
                raise ConflictError(
                    f"No se puede cancelar un mensaje {message.status}.", code="invalid_status"
                )
            actor_id = user_actor_id(self.db, access.ctx.user_id)
            now = utcnow()
            before = message.status
            message.status, message.cancelled_at, message.cancel_reason = "cancelled", now, "manual"
            message.next_attempt_at = None
            message.updated_at, message.updated_by = now, actor_id
            purge_attachments(self.db, message.id, now=now, actor_id=actor_id)
            record_change(
                self.db, action="message.cancel", resource_type="message", resource_id=message.id,
                company_id=message.company_id, actor_id=actor_id, now=now,
                before={"status": before}, after={"status": "cancelled", "cancel_reason": "manual"}, reason=reason,
            )
            return summary(message)

    def retry_dispatch(self, access: Access, dispatch_id: str, *, reason: str | None) -> int:
        """Reprocesa todos los failed y uncertain del envío; devuelve cuántos."""
        with self.db.begin():
            dispatch = self.queries.find_dispatch(access, dispatch_id)
            messages = list(self.db.scalars(
                select(Message)
                .where(Message.dispatch_id == dispatch.id, Message.status.in_(RETRYABLE))
                .order_by(Message.sequence)
                .with_for_update()
            ))
            for message in messages:
                self._requeue(access, message, reason=reason)
            return len(messages)

    def _locked(self, access: Access, message_id: str) -> Message:
        """Mensaje dentro del alcance (404 si no), releído con FOR UPDATE."""
        message = self.queries.find_message(access, message_id)
        return self.db.get(Message, message.id, with_for_update=True, populate_existing=True)

    def _requeue(self, access: Access, message: Message, *, reason: str | None) -> None:
        actor_id = user_actor_id(self.db, access.ctx.user_id)
        now = utcnow()
        before = message.status
        message.status, message.next_attempt_at = "pending", now
        message.attempts_in_cycle = 0
        message.notice_dispatch_id = None
        message.updated_at, message.updated_by = now, actor_id
        record_change(
            self.db, action="message.retry", resource_type="message", resource_id=message.id,
            company_id=message.company_id, actor_id=actor_id, now=now,
            before={"status": before}, after={"status": "pending"}, reason=reason,
        )
