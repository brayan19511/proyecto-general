"""Creación de envíos (POST /dispatches). Docs: docs/api.md y docs/modelo-datos.md.

Orden, pensado para no trabajar de más:
1. Validar el payload y las referencias a archivos; sanear nombres, detectar
   tipos y calcular hashes (barato, sin base).
2. Calcular request_hash y buscar la Idempotency-Key: si ya existe con el mismo
   hash se devuelve ese envío (replay) sin armar nada; con otro hash, 409.
3. Exigir una cuenta SMTP activa (su dominio va en el Message-ID).
4. Normalizar destinatarios, armar cada MIME y medir su tamaño (25 MB).
5. Guardar envío, mensajes, adjuntos e historial en UNA transacción. Los
   mensajes quedan pending: los enviará el worker.

Dos solicitudes simultáneas con la misma clave: el índice único deja pasar
una; la otra recibe IntegrityError, lee la ganadora y aplica la regla del paso 2.
"""

from dataclasses import dataclass

from platform_audit import current_trace_id, step
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.common.mixin_model import new_id, utcnow
from app.models.entities import Dispatch, Message, MessageAttachment, SmtpAccount, Template
from app.schemas.dispatches import DispatchPayload
from app.services.actors import user_actor_id
from app.services.attachment_types import detect_content_type, sanitize_filename
from app.services.errors import ConflictError, InvalidDataError
from app.services.history import record_change
from app.services.message_builder import PLACEHOLDER_FROM, Attachment, build_mime, check_size, mime_size
from app.services.recipients import normalize_address, normalize_recipients
from app.services.request_hash import compute_request_hash, sha256_hex
from app.services.template_service import render_template


@dataclass(frozen=True)
class UploadedFile:
    filename: str | None  # Tal como llegó (se sanea aquí).
    content: bytes


@dataclass(frozen=True)
class _PreparedFile:
    filename: str
    content_type: str
    sha256: str
    content: bytes


@dataclass(frozen=True)
class CreateResult:
    dispatch: Dispatch
    replayed: bool  # True: misma Idempotency-Key y mismo contenido; no se creó nada.


def parse_payload(raw: str) -> DispatchPayload:
    try:
        return DispatchPayload.model_validate_json(raw)
    except ValidationError as error:
        problems = [
            {"loc": list(e["loc"]), "msg": e["msg"]} for e in error.errors(include_url=False, include_input=False)
        ]
        raise InvalidDataError("payload no válido.", code="validation_error", extra={"errors": problems}) from None


def _prepare_files(payload: DispatchPayload, files: dict[str, UploadedFile]) -> dict[str, _PreparedFile]:
    referenced = {name for message in payload.messages for name in message.attachments}
    missing = sorted(referenced - files.keys())
    if missing:
        raise InvalidDataError(f"Adjuntos referenciados que no se enviaron: {', '.join(missing)}.")
    unused = sorted(files.keys() - referenced)
    if unused:
        raise InvalidDataError(f"Archivos enviados que ningún mensaje usa: {', '.join(unused)}.")
    prepared = {}
    for part, upload in files.items():
        filename = sanitize_filename(upload.filename)
        prepared[part] = _PreparedFile(
            filename=filename,
            content_type=detect_content_type(filename, upload.content),
            sha256=sha256_hex(upload.content),
            content=upload.content,
        )
    return prepared


class DispatchService:
    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        *,
        company_id: str,
        user_id: str,
        requester_email: str | None,
        idempotency_key: str,
        raw_payload: str,
        files: dict[str, UploadedFile],
    ) -> CreateResult:
        payload = parse_payload(raw_payload)
        prepared = _prepare_files(payload, files)
        request_hash = compute_request_hash(
            payload.model_dump(mode="json"), {part: (f.filename, f.sha256) for part, f in prepared.items()}
        )
        try:
            with step("dispatch.create"), self.db.begin():
                actor_id = user_actor_id(self.db, user_id)
                existing = self._find_by_key(company_id, actor_id, idempotency_key)
                if existing is not None:
                    return self._replay(existing, request_hash)
                dispatch = self._insert(
                    company_id=company_id, actor_id=actor_id, requester_email=requester_email,
                    idempotency_key=idempotency_key, request_hash=request_hash, payload=payload, prepared=prepared,
                )
                return CreateResult(dispatch=dispatch, replayed=False)
        except IntegrityError:
            # Otra solicitud con la misma clave ganó la carrera: se aplica la regla del replay.
            with self.db.begin():
                actor_id = user_actor_id(self.db, user_id)
                existing = self._find_by_key(company_id, actor_id, idempotency_key)
                if existing is None:
                    raise
                return self._replay(existing, request_hash)

    def _find_by_key(self, company_id: str, actor_id: str, idempotency_key: str) -> Dispatch | None:
        return self.db.scalar(
            select(Dispatch).where(
                Dispatch.company_id == company_id,
                Dispatch.created_by == actor_id,
                Dispatch.idempotency_key == idempotency_key,
            )
        )

    @staticmethod
    def _replay(existing: Dispatch, request_hash: str) -> CreateResult:
        if existing.request_hash != request_hash:
            raise ConflictError(
                "La Idempotency-Key ya se usó con un contenido distinto.", code="idempotency_conflict"
            )
        return CreateResult(dispatch=existing, replayed=True)

    def _sender_domain(self, company_id: str) -> str:
        """Dominio del remitente de la primera cuenta activa (acuerdo A del Message-ID)."""
        from_email = self.db.scalar(
            select(SmtpAccount.from_email)
            .where(SmtpAccount.company_id == company_id, SmtpAccount.is_active.is_(True))
            .order_by(SmtpAccount.priority, SmtpAccount.created_at)
            .limit(1)
        )
        if from_email is None:
            raise InvalidDataError(
                "La empresa no tiene una cuenta SMTP activa: el envío no podría salir.", code="no_smtp_account"
            )
        return from_email.rsplit("@", 1)[1]

    def _insert(
        self,
        *,
        company_id: str,
        actor_id: str,
        requester_email: str | None,
        idempotency_key: str,
        request_hash: str,
        payload: DispatchPayload,
        prepared: dict[str, _PreparedFile],
    ) -> Dispatch:
        domain = self._sender_domain(company_id)
        now = utcnow()
        dispatch = Dispatch(
            company_id=company_id, kind="standard", idempotency_key=idempotency_key, request_hash=request_hash,
            consumer=payload.consumer, consumer_reference=payload.consumer_reference,
            requester_email=requester_email, trace_id=current_trace_id(), created_at=now, created_by=actor_id,
        )
        self.db.add(dispatch)
        self.db.flush()  # Id del envío; aquí falla una Idempotency-Key repetida en carrera.

        templates = self._templates(company_id, payload)
        for index, message_in in enumerate(payload.messages, start=1):
            content = _resolve_content(payload, message_in, templates, index)
            recipients = normalize_recipients(content.to, content.cc, content.bcc)
            reply_to = normalize_address(content.reply_to) if content.reply_to else None
            files = [prepared[part] for part in message_in.attachments]
            message_id_header = f"<{new_id()}@{domain}>"
            mime = build_mime(
                from_header=PLACEHOLDER_FROM, recipients=recipients, reply_to=reply_to,
                subject=content.subject, body_html=content.body_html, body_text=content.body_text,
                message_id=message_id_header,
                attachments=[Attachment(f.filename, f.content_type, f.content) for f in files],
            )
            size = mime_size(mime)
            check_size(size, message_index=index)
            message = Message(
                company_id=company_id, dispatch_id=dispatch.id, sequence=index,
                consumer_reference=message_in.consumer_reference,
                to_addresses=recipients.to, cc_addresses=recipients.cc, bcc_addresses=recipients.bcc,
                reply_to=reply_to, subject=content.subject,
                body_html=content.body_html, body_text=content.body_text,
                message_id_header=message_id_header, size_bytes=size, template_id=content.template_id,
                status="pending", attempts_in_cycle=0, next_attempt_at=now,
                created_at=now, created_by=actor_id,
            )
            self.db.add(message)
            self.db.flush()
            # Una copia por mensaje (acuerdo): cada uno se purga por su cuenta al terminar.
            for sequence, f in enumerate(files, start=1):
                self.db.add(
                    MessageAttachment(
                        company_id=company_id, message_id=message.id, sequence=sequence,
                        filename=f.filename, content_type=f.content_type, size_bytes=len(f.content),
                        sha256=f.sha256, content=f.content, created_at=now, created_by=actor_id,
                    )
                )

        record_change(
            self.db, action="dispatch.create", resource_type="dispatch", resource_id=dispatch.id,
            company_id=company_id, actor_id=actor_id, now=now, before={},
            after={
                "consumer": payload.consumer, "consumer_reference": payload.consumer_reference,
                "messages": len(payload.messages), "attachments": sum(len(m.attachments) for m in payload.messages),
                "templates": sorted(templates),
            },
        )
        return dispatch

    def _templates(self, company_id: str, payload: DispatchPayload) -> dict[str, Template]:
        """Plantillas activas que usa el envío, en una consulta. 422 si alguna no existe."""
        codes = {code for m in payload.messages if (code := payload.template_for(m)) is not None}
        if not codes:
            return {}
        found = {
            t.code: t
            for t in self.db.scalars(
                select(Template).where(
                    Template.company_id == company_id, Template.code.in_(codes), Template.is_active.is_(True)
                )
            )
        }
        missing = sorted(codes - found.keys())
        if missing:
            raise InvalidDataError(
                f"Plantilla no encontrada o dada de baja: {', '.join(missing)}.", code="template_not_found"
            )
        return found


@dataclass(frozen=True)
class _Content:
    """Lo que se guarda y se envía de un mensaje, ya armado."""

    to: list[str]
    cc: list[str]
    bcc: list[str]
    reply_to: str | None
    subject: str
    body_html: str | None
    body_text: str | None
    template_id: str | None


def _resolve_content(payload: DispatchPayload, message_in, templates: dict[str, Template], index: int) -> _Content:
    """Contenido armado: el del consumidor, o la plantilla con sus parámetros y
    los destinatarios fijos sumados a los del consumidor (acuerdo del paso 2)."""
    code = payload.template_for(message_in)
    if code is None:
        return _Content(
            message_in.to, message_in.cc, message_in.bcc, message_in.reply_to,
            message_in.subject, message_in.body_html, message_in.body_text, None,
        )
    template = templates[code]
    try:
        rendered = render_template(template, message_in.parameters or {})
    except InvalidDataError as error:
        # Se indica qué mensaje falló: con 500 mensajes no se adivina.
        raise InvalidDataError(
            f"Mensaje {index}: {error}", code=error.code, extra={"message_index": index, **error.extra}
        ) from None
    return _Content(
        # Primero los del consumidor; los fijos se suman y normalize_recipients quita duplicados.
        to=[*message_in.to, *template.to_addresses],
        cc=[*message_in.cc, *template.cc_addresses],
        bcc=[*message_in.bcc, *template.bcc_addresses],
        reply_to=message_in.reply_to or template.reply_to,
        subject=rendered.subject, body_html=rendered.body_html, body_text=rendered.body_text,
        template_id=template.id,
    )
