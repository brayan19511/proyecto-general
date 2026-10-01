from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile

from app.api.dependencies import Access, require_permission
from app.core.db.connection import get_db
from app.core.permissions import CAN_RETRY, CAN_SEND, CAN_VIEW
from app.schemas.dispatches import DispatchOut, DispatchStatus
from app.schemas.messages import ActionIn, MessageSummaryOut, RequeuedOut
from app.services.message_actions import MessageActions
from app.schemas.page import Page, PageOut
from app.services import dispatch_progress
from app.services.dispatch_queries import DispatchFilters, DispatchQueries
from app.services.dispatch_service import DispatchService, UploadedFile
from app.services.errors import InvalidDataError

router = APIRouter(prefix="/dispatches", tags=["dispatches"])
can_send = require_permission(*CAN_SEND)
can_view = require_permission(*CAN_VIEW)
can_retry = require_permission(*CAN_RETRY)

MessageStatus = Literal["pending", "sending", "retrying", "sent", "failed", "uncertain", "cancelled"]


@router.get("", response_model=PageOut[DispatchOut], operation_id="listDispatches")
def list_dispatches(
    status_filter: Annotated[DispatchStatus | None, Query(alias="status")] = None,
    consumer: str | None = None,
    consumer_reference: str | None = None,
    kind: Literal["standard", "failure_notice"] | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    requested_by_user_id: Annotated[str | None, Query(max_length=36)] = None,
    requester_email: Annotated[str | None, Query(min_length=1, max_length=320)] = None,
    page: Page = Depends(),
    access: Access = Depends(can_view),
    db: Session = Depends(get_db),
):
    """Envíos del más nuevo al más antiguo. Con alcance own, solo los que solicitó el usuario.

    status: pending · in_progress · completed · completed_with_errors (calculado).
    created_to es exclusivo. requested_by_user_id: id de auth del solicitante;
    requester_email: parte de su correo (sin distinguir mayúsculas).
    """
    filters = DispatchFilters(
        status=status_filter, consumer=consumer, consumer_reference=consumer_reference, kind=kind,
        created_from=created_from, created_to=created_to,
        requested_by_user_id=requested_by_user_id, requester_email=requester_email,
    )
    queries = DispatchQueries(db)
    dispatches, total = queries.list_dispatches(access, filters, limit=page.limit, offset=page.offset)
    with db.begin():
        items = dispatch_progress.to_out(db, dispatches)
    return PageOut[DispatchOut](items=items, total=total)


@router.get("/{dispatch_id}", response_model=DispatchOut, operation_id="getDispatch")
def get_dispatch(dispatch_id: str, access: Access = Depends(can_view), db: Session = Depends(get_db)):
    """Estado y progreso calculados en el momento. 404 fuera del alcance."""
    dispatch = DispatchQueries(db).get_dispatch(access, dispatch_id)
    return _out(db, dispatch)


@router.get("/{dispatch_id}/messages", response_model=PageOut[MessageSummaryOut], operation_id="listDispatchMessages")
def list_dispatch_messages(
    dispatch_id: str,
    status_filter: Annotated[MessageStatus | None, Query(alias="status")] = None,
    page: Page = Depends(),
    access: Access = Depends(can_view),
    db: Session = Depends(get_db),
):
    """Mensajes del envío en orden (sin cuerpo ni adjuntos)."""
    items, total = DispatchQueries(db).list_messages(
        access, dispatch_id, status=status_filter, limit=page.limit, offset=page.offset
    )
    return PageOut[MessageSummaryOut](items=items, total=total)

# Límites del parser multipart de Starlette. El borde ya corta solicitudes de
# más de 100 MB; aquí se amplían los defaults (1 MB por campo de texto, 1000
# archivos) para que entre un payload de 500 mensajes con sus adjuntos.
MAX_PAYLOAD_PART_BYTES = 100 * 1024 * 1024
MAX_FILES = 10_000

IdempotencyKey = Annotated[
    str, Header(alias="Idempotency-Key", min_length=1, max_length=100, pattern=r"^[\x21-\x7e]+$")
]


@router.post(
    "",
    response_model=DispatchOut,
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="createDispatch",
    responses={200: {"model": DispatchOut, "description": "Repetición idempotente: el envío ya existía"}},
)
async def create_dispatch(
    request: Request,
    response: Response,
    idempotency_key: IdempotencyKey,
    access: Access = Depends(can_send),
    db: Session = Depends(get_db),
):
    """Crea un envío (multipart/form-data, docs/api.md).

    - Parte `payload`: JSON con consumer, consumer_reference y messages.
    - Una parte de archivo por adjunto ("f1", "f2"…), referenciada por nombre
      desde messages[].attachments.

    202: creado; los mensajes quedan pendientes para el worker. 200: misma
    Idempotency-Key y mismo contenido (devuelve el existente). 409
    idempotency_conflict · 422 validation_error, attachment_type_not_allowed,
    message_too_large, no_smtp_account.

    La identidad y los permisos se validan ANTES de leer el cuerpo: una
    solicitud sin permiso no llega a subir sus archivos.
    """
    form = await request.form(max_files=MAX_FILES, max_part_size=MAX_PAYLOAD_PART_BYTES)
    try:
        raw_payload, files = None, {}
        for name, value in form.multi_items():
            if isinstance(value, UploadFile):
                if name in files:
                    raise InvalidDataError(f"Parte de archivo repetida: {name}.")
                files[name] = UploadedFile(filename=value.filename, content=await value.read())
            elif name == "payload":
                raw_payload = value
            else:
                raise InvalidDataError(f"Campo no esperado: {name}. Solo 'payload' y archivos.")
        if raw_payload is None:
            raise InvalidDataError("Falta la parte 'payload' (JSON).")
    finally:
        await form.close()  # Libera los temporales en disco del multipart.

    ctx = access.ctx
    service = DispatchService(db)
    # Validar, armar MIME y guardar es trabajo síncrono (CPU y base): fuera del event loop.
    result = await run_in_threadpool(
        service.create,
        company_id=ctx.company_id, user_id=ctx.user_id, requester_email=ctx.email,
        idempotency_key=idempotency_key, raw_payload=raw_payload, files=files,
    )
    if result.replayed:
        response.status_code = status.HTTP_200_OK
    return (await run_in_threadpool(_out, db, result.dispatch))


def _out(db: Session, dispatch) -> DispatchOut:
    with db.begin():
        return dispatch_progress.to_out(db, [dispatch])[0]


@router.post("/{dispatch_id}/retry", response_model=RequeuedOut, operation_id="retryDispatch")
def retry_dispatch(
    dispatch_id: str,
    body: ActionIn | None = None,
    access: Access = Depends(can_retry),
    db: Session = Depends(get_db),
):
    """Reprocesa todos los mensajes failed y uncertain del envío. requeued = 0 si no había."""
    requeued = MessageActions(db).retry_dispatch(access, dispatch_id, reason=body.reason if body else None)
    return RequeuedOut(requeued=requeued)
