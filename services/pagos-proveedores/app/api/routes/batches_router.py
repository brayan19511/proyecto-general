from typing import Annotated, Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, ConfigDict, StringConstraints
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile

from app.api.dependencies import CompanyContext, require_permission
from app.core.db.connection import get_db
from app.core.permissions import ADMIN, CAN_SEND, CAN_VIEW
from app.schemas.batches import BatchOut, BatchSummaryOut
from app.schemas.page import Page, PageOut
from app.services.batch_service import MAX_FILES, BatchService, Upload, parse_uploads
from app.services.errors import InvalidDataError
from app.services.send_service import SendService

# Lotes de la empresa activa (X-Company-Id). Ver y descargar una constancia:
# payments.view (o superior). Crear, ZIP, quitar archivos, descartar y enviar:
# payments.send o payments.admin.
router = APIRouter(prefix="/batches", tags=["batches"])
can_view = require_permission(*CAN_VIEW)
can_send = require_permission(*CAN_SEND)

_SINGLE_LINE = r"^[^\x00-\x1f\x7f]*$"


class DiscardIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)] | None = None


def _attachment_headers(filename: str) -> dict[str, str]:
    fallback = filename.encode("ascii", "replace").decode("ascii").replace('"', "_")
    return {
        "Content-Disposition": f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(filename)}",
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "no-store",
    }


@router.post("", response_model=BatchOut, status_code=status.HTTP_201_CREATED, operation_id="createBatch")
async def create_batch(request: Request, ctx: CompanyContext = Depends(can_send), db: Session = Depends(get_db)):
    """Sube constancias (multipart): una o más partes "files" con los PDF y "reference" opcional.

    Lee cada PDF (con OCR si está habilitado y hace falta) y responde el lote con
    sus archivos, los grupos por proveedor y ready_to_send (lo que antes era la
    vista previa). Un PDF ilegible no corta el lote: queda con parse_status=error.
    422 duplicate_file si el mismo PDF viene dos veces. Auth se valida antes de leer el cuerpo.
    """
    form = await request.form(max_files=MAX_FILES + 1)
    try:
        uploads, reference = [], None
        for name, value in form.multi_items():
            if name == "files" and isinstance(value, UploadFile):
                uploads.append(Upload(value.filename, await value.read()))
            elif name == "reference" and isinstance(value, str):
                reference = value.strip() or None
            else:
                raise InvalidDataError(f"Campo no esperado: {name}. Solo 'files' (PDF) y 'reference'.")
    finally:
        await form.close()
    if reference is not None and (len(reference) > 100 or any(ord(c) < 32 for c in reference)):
        raise InvalidDataError("reference: hasta 100 caracteres, en una línea.")

    # Leer PDFs (y OCR) es trabajo de CPU: fuera del event loop y fuera de la transacción.
    parsed = await run_in_threadpool(parse_uploads, uploads)
    service = BatchService(db)
    batch = await run_in_threadpool(
        service.create, company_id=ctx.company_id, user_id=ctx.user_id, reference=reference, parsed=parsed
    )
    return await run_in_threadpool(service.get, ctx.company_id, batch.id)


@router.get("", response_model=PageOut[BatchSummaryOut], operation_id="listBatches")
def list_batches(
    status_filter: Annotated[Literal["draft", "sending", "sent"] | None, Query(alias="status")] = None,
    page: Page = Depends(),
    ctx: CompanyContext = Depends(can_view),
    db: Session = Depends(get_db),
):
    """Lotes del más nuevo al más antiguo (los descartados no aparecen)."""
    items, total = BatchService(db).list(ctx.company_id, status=status_filter, limit=page.limit, offset=page.offset)
    return PageOut[BatchSummaryOut](items=items, total=total)


@router.get("/{batch_id}", response_model=BatchOut, operation_id="getBatch")
def get_batch(batch_id: str, ctx: CompanyContext = Depends(can_view), db: Session = Depends(get_db)):
    """Borrador: grupos con el maestro actual (corregir un proveedor actualiza el lote).
    Enviado: los grupos congelados al enviar."""
    return BatchService(db).get(ctx.company_id, batch_id)


@router.get(
    "/{batch_id}/files/{file_id}",
    response_class=Response,
    operation_id="downloadBatchFile",
    responses={200: {"content": {"application/pdf": {}}}},
)
def download_file(batch_id: str, file_id: str, ctx: CompanyContext = Depends(can_view), db: Session = Depends(get_db)):
    """La constancia tal como se subió (también las de lotes enviados: son la evidencia)."""
    filename, content = BatchService(db).file_content(ctx.company_id, batch_id, file_id)
    return Response(content=content, media_type="application/pdf", headers=_attachment_headers(filename))


@router.get(
    "/{batch_id}/zip",
    response_class=Response,
    operation_id="downloadBatchZip",
    responses={200: {"content": {"application/zip": {}}}},
)
def download_zip(batch_id: str, ctx: CompanyContext = Depends(can_send), db: Session = Depends(get_db)):
    """Constancias leídas con el nombre titular + fecha (como /payments/renamed-zip de proyecto-05)."""
    content = BatchService(db).zip(ctx.company_id, batch_id)
    return Response(content=content, media_type="application/zip",
                    headers=_attachment_headers("constancias_renombradas.zip"))


@router.delete(
    "/{batch_id}/files/{file_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    operation_id="removeBatchFile",
)
def remove_file(batch_id: str, file_id: str, ctx: CompanyContext = Depends(can_send), db: Session = Depends(get_db)):
    """Quita una constancia del borrador (baja lógica). 409 si el lote ya se envió."""
    BatchService(db).remove_file(company_id=ctx.company_id, user_id=ctx.user_id, batch_id=batch_id, file_id=file_id)


@router.delete("/{batch_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response, operation_id="discardBatch")
def discard_batch(
    batch_id: str, body: DiscardIn | None = None, ctx: CompanyContext = Depends(can_send), db: Session = Depends(get_db)
):
    """Descarta un borrador (baja lógica). 409 si el lote está sending o sent: es evidencia."""
    BatchService(db).discard(
        company_id=ctx.company_id, user_id=ctx.user_id, batch_id=batch_id, reason=body.reason if body else None
    )


class SendIn(BaseModel):
    """Opciones del envío (antes mailing_parameter, subject_override y message_override de proyecto-05)."""

    model_config = ConfigDict(extra="forbid")

    # Plantilla de notificaciones; vacío = DEFAULT_TEMPLATE_CODE (payment_provider_summary).
    # Elegir otra solo con payments.admin (acuerdo 2026-10-01).
    template_code: Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9_.-]{0,99}$")] | None = None
    # Llegan a la plantilla como parámetros "asunto" y "mensaje": se usan si la plantilla los usa.
    subject: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=998, pattern=_SINGLE_LINE)] | None = None
    message: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)] | None = None


@router.post("/{batch_id}/send", response_model=BatchOut, operation_id="sendBatch")
def send_batch(
    batch_id: str, body: SendIn | None = None, ctx: CompanyContext = Depends(can_send), db: Session = Depends(get_db)
):
    """Envía el lote por notificaciones: un correo por proveedor con sus constancias.

    Requiere además notifications.send en notificaciones (se usa tu token).
    409 not_ready si no está listo. 4xx de notificaciones (plantilla, cuenta SMTP,
    tamaño, permisos): el lote vuelve a borrador y se devuelve ese error. 502/504:
    el lote queda "sending" y se puede volver a enviar sin duplicar correos. Un lote
    "sending" se reenvía con las opciones del primer intento; uno "sent" no hace nada.
    Elegir template_code exige payments.admin (403): quien envía usa la
    plantilla configurada (DEFAULT_TEMPLATE_CODE).
    """
    options = body or SendIn()
    if options.template_code is not None and not ctx.has_any((ADMIN,)):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo un administrador de pagos puede elegir la plantilla.")
    SendService(db).send(
        ctx, batch_id, template_code=options.template_code, subject=options.subject, message=options.message
    )
    return BatchService(db).get(ctx.company_id, batch_id)


@router.get("/{batch_id}/delivery-status", operation_id="getBatchDeliveryStatus")
def delivery_status(batch_id: str, ctx: CompanyContext = Depends(can_view), db: Session = Depends(get_db)):
    """Estado del envío en notificaciones (progreso y estado de cada proveedor).
    Requiere notifications.view; 409 not_sent si el lote aún no se envió."""
    return SendService(db).delivery_status(ctx, batch_id)
