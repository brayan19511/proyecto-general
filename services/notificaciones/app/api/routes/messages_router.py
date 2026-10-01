from urllib.parse import quote

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.dependencies import Access, require_company_permission, require_permission
from app.core.db.connection import get_db
from app.core.permissions import CAN_ADMIN, CAN_RETRY, CAN_VIEW
from app.schemas.messages import ActionIn, AttemptOut, MessageDetailOut, MessageSummaryOut
from app.services.dispatch_queries import DispatchQueries
from app.services.message_actions import MessageActions

router = APIRouter(prefix="/messages", tags=["messages"])
can_view = require_permission(*CAN_VIEW)
can_retry = require_permission(*CAN_RETRY)
can_admin = require_company_permission(*CAN_ADMIN)


@router.post("/{message_id}/retry", response_model=MessageSummaryOut, operation_id="retryMessage")
def retry_message(
    message_id: str,
    body: ActionIn | None = None,
    access: Access = Depends(can_retry),
    db: Session = Depends(get_db),
):
    """failed o uncertain → pending, con sus 3 reintentos automáticos de nuevo.
    409 invalid_status desde otro estado. Un uncertain quizá ya llegó: el
    destinatario podría recibirlo dos veces (mismo Message-ID)."""
    return MessageActions(db).retry(access, message_id, reason=body.reason if body else None)


@router.post("/{message_id}/cancel", response_model=MessageSummaryOut, operation_id="cancelMessage")
def cancel_message(
    message_id: str,
    body: ActionIn | None = None,
    access: Access = Depends(can_retry),
    db: Session = Depends(get_db),
):
    """pending, retrying, failed o uncertain → cancelled; purga sus adjuntos.
    409 invalid_status si está sending, sent o cancelled. No se puede deshacer."""
    return MessageActions(db).cancel(access, message_id, reason=body.reason if body else None)


@router.get("/{message_id}", response_model=MessageDetailOut, operation_id="getMessage")
def get_message(message_id: str, access: Access = Depends(can_view), db: Session = Depends(get_db)):
    """Destinatarios, asunto, cuerpo, adjuntos y estado. technical solo con notifications.admin.

    body_html se devuelve tal cual: mostrarlo en un <iframe sandbox> sin scripts.
    """
    return DispatchQueries(db).get_message(access, message_id)


@router.get(
    "/{message_id}/attachments/{attachment_id}",
    response_class=Response,
    operation_id="downloadMessageAttachment",
    responses={200: {"content": {"application/octet-stream": {}}}, 410: {"description": "Contenido purgado"}},
)
def download_attachment(
    message_id: str, attachment_id: str, access: Access = Depends(can_view), db: Session = Depends(get_db)
):
    """Descarga el adjunto. 410 si ya se purgó (el mensaje se envió o se canceló)."""
    filename, content_type, content = DispatchQueries(db).get_attachment(access, message_id, attachment_id)
    # Siempre "attachment" (nunca inline) y nosniff: el navegador no lo abre en el
    # origen de la plataforma. filename* (RFC 6266/5987) admite tildes y ñ.
    fallback = filename.encode("ascii", "replace").decode("ascii").replace('"', "_")
    return Response(
        content=content,
        media_type=content_type,
        headers={
            "Content-Disposition": f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(filename)}",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )


@router.get("/{message_id}/attempts", response_model=list[AttemptOut], operation_id="listMessageAttempts")
def list_attempts(message_id: str, access: Access = Depends(can_admin), db: Session = Depends(get_db)):
    """Intentos con cuenta usada, resultado, código y respuesta SMTP. Solo notifications.admin."""
    return DispatchQueries(db).list_attempts(access, message_id)
