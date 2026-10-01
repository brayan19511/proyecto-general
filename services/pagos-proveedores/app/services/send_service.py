"""Envío de un lote por notificaciones (acuerdo 2 del modelo: dos fases).

Fase 1 (una transacción, lote bloqueado): solo un borrador listo
(ready_to_send). Congela un BatchDelivery por proveedor con la copia de sus
datos, asigna cada constancia a su entrega, fija plantilla, asunto y mensaje,
y pasa el lote a "sending".

Fase 2 (fuera de la transacción): POST /notificaciones/dispatches con el token
del usuario, Idempotency-Key = id del lote y el contenido CONGELADO. Un mensaje
por entrega: to = correos de pago, consumer_reference = id de la entrega,
parámetros de la plantilla como en proyecto-05 (proveedor, pagos, totales…)
más asunto y mensaje, y sus constancias renombradas como adjuntos.

Resultado:
- 200/202 → "sent" con el id del envío.
- 4xx (validación, permisos, plantilla o cuenta SMTP): notificaciones no creó
  nada → el lote vuelve a "draft" (entregas dadas de baja) y se devuelve el
  mismo error. Se corrige y se vuelve a enviar.
- Timeout, 5xx o caída: no se sabe si se creó → el lote queda "sending".
  Reintentar reenvía exactamente lo mismo: notificaciones devuelve el envío
  existente (200) o lo crea. Nunca duplica correos.
"""

import json
import logging

import httpx
from platform_audit import step
from platform_audit.context import current_operation
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import CompanyContext
from app.clients.notifications_client import notifications_client
from app.models.common.mixin_model import utcnow
from app.models.entities import Batch, BatchDelivery, BatchFile
from app.services.settings_service import SettingsService
from app.services.actors import user_actor_id
from app.services.batch_service import BatchService, ready_to_send, unique_filename
from app.services.errors import ConflictError, ServiceError
from app.services.history import record_change

logger = logging.getLogger("pagos_proveedores.send")


class UpstreamError(ServiceError):
    """Notificaciones no respondió o respondió algo inesperado (mensaje seguro)."""

    status_code = 502


class UpstreamRejected(ServiceError):
    """Notificaciones rechazó el envío: se devuelve su status y su mensaje."""

    def __init__(self, status_code: int, body: dict):
        super().__init__(body.get("detail") if isinstance(body.get("detail"), str) else "Notificaciones rechazó el envío.",
                         code=body.get("code"), extra={k: v for k, v in body.items() if k not in ("detail", "code")})
        self.status_code = status_code


class SendService:
    def __init__(self, db: Session):
        self.db = db
        self.batches = BatchService(db)

    def send(
        self, ctx: CompanyContext, batch_id: str, *, template_code: str | None, subject: str | None, message: str | None
    ) -> Batch:
        with step("batch.send.freeze"):
            batch = self._freeze(ctx, batch_id, template_code=template_code, subject=subject, message=message)
        if batch.status == "sent":
            return batch  # Ya enviado: repetir no hace nada.
        payload, files = self._build_request(batch)
        with step("batch.send.notifications"):
            try:
                response = notifications_client.post(
                    "/notificaciones/dispatches",
                    headers=self._headers(ctx, batch),
                    data={"payload": json.dumps(payload, ensure_ascii=False)},
                    files=files,
                )
            except httpx.TimeoutException:
                raise UpstreamError(
                    "Notificaciones no respondió a tiempo. El lote quedó 'sending': vuelve a enviarlo "
                    "(no se duplicarán correos).", code="notifications_timeout",
                ) from None
            except httpx.TransportError:
                raise UpstreamError(
                    "Notificaciones no está disponible. El lote quedó 'sending': vuelve a enviarlo.",
                    code="notifications_unavailable",
                ) from None
        return self._finish(ctx, batch.id, response)

    # --- Fase 1 ------------------------------------------------------------

    def _freeze(self, ctx: CompanyContext, batch_id: str, *, template_code, subject, message) -> Batch:
        with self.db.begin():
            batch = self.batches.find(ctx.company_id, batch_id, for_update=True)
            if batch.status in ("sending", "sent"):
                return batch  # Reintento: se reenvía lo congelado (las opciones nuevas no aplican).
            files = self.batches._files(batch.id)
            groups = self.batches.groups(batch, files)
            if not ready_to_send(files, groups):
                raise ConflictError(
                    "El lote no está listo: hay constancias con error o proveedores sin identificar o sin correo.",
                    code="not_ready",
                )
            actor_id = user_actor_id(self.db, ctx.user_id)
            now = utcnow()
            by_id = {f.id: f for f in files}
            # Si un intento anterior fue rechazado, sus entregas siguen (dadas de baja):
            # se numera a continuación para no repetir (batch_id, sequence).
            last = self.db.scalar(select(func.max(BatchDelivery.sequence)).where(BatchDelivery.batch_id == batch.id)) or 0
            for sequence, group in enumerate(groups, start=last + 1):
                delivery = BatchDelivery(
                    company_id=batch.company_id, batch_id=batch.id, sequence=sequence,
                    provider_id=group["provider_id"], tax_id=group["provider_tax_id"],
                    legal_name=group["proveedor"], payment_emails=group["emails_payments"],
                    totals=group["totales"], created_at=now, created_by=actor_id,
                )
                self.db.add(delivery)
                self.db.flush()
                for payment in group["pagos"]:
                    by_id[payment["file_id"]].delivery_id = delivery.id
            batch.status = "sending"
            # La elegida al enviar (solo payments.admin), la de la empresa o la del servicio.
            batch.template_code = template_code or SettingsService(self.db).default_template(ctx.company_id)
            batch.custom_subject, batch.custom_message = subject, message
            batch.updated_at, batch.updated_by = now, actor_id
            record_change(
                self.db, action="batch.send", resource_type="batch", resource_id=batch.id,
                company_id=batch.company_id, actor_id=actor_id, now=now, before={"status": "draft"},
                after={"status": "sending", "deliveries": len(groups), "template_code": batch.template_code},
            )
            return batch

    # --- Fase 2 ------------------------------------------------------------

    def _build_request(self, batch: Batch) -> tuple[dict, list]:
        """Payload y partes de archivo desde lo CONGELADO (mismo contenido en cada reintento)."""
        with self.db.begin():
            files = self.batches._files(batch.id)
            groups = self.batches.groups(batch, files)  # sending: agrupado con las copias de las entregas.
            deliveries = list(self.db.scalars(
                select(BatchDelivery)
                .where(BatchDelivery.batch_id == batch.id, BatchDelivery.is_active.is_(True))
                .order_by(BatchDelivery.sequence)
            ))
            content = {f.id: f.content for f in files}
            messages, parts = [], []
            for delivery, group in zip(deliveries, groups, strict=True):
                used, names = set(), []
                for payment in group["pagos"]:
                    filename = unique_filename(payment["suggested_filename"], used)
                    used.add(filename)
                    part = f"f{len(parts) + 1}"
                    parts.append((part, (filename, content[payment["file_id"]], "application/pdf")))
                    names.append(part)
                messages.append({
                    "consumer_reference": delivery.id,
                    "to": delivery.payment_emails,
                    "parameters": {
                        # Mismos parámetros que mandaba proyecto-05 a su plantilla.
                        "provider_id": delivery.provider_id,
                        "provider_tax_id": delivery.tax_id,
                        "proveedor": delivery.legal_name,
                        "titular_pdf": group["titular_pdf"],
                        "cantidad_pagos": group["cantidad_pagos"],
                        "totales": group["totales"],
                        "pagos": group["pagos"],
                        # Antes subject_override / message_override: la plantilla decide cómo usarlos.
                        "asunto": batch.custom_subject,
                        "mensaje": batch.custom_message,
                    },
                    "attachments": names,
                })
            payload = {
                "consumer": "pagos-proveedores",
                "consumer_reference": batch.reference or batch.id,
                "template_code": batch.template_code,
                "messages": messages,
            }
            return payload, parts

    @staticmethod
    def _headers(ctx: CompanyContext, batch: Batch) -> dict[str, str]:
        headers = {**ctx.auth_headers, "idempotency-key": batch.id}
        operation = current_operation()
        if operation is not None:  # Enlaza el log de notificaciones con el de este envío.
            headers["x-trace-id"] = operation.trace_id
            headers["x-parent-operation-id"] = operation.log_id
        return headers

    # --- Fase 3: guardar el resultado --------------------------------------

    def _finish(self, ctx: CompanyContext, batch_id: str, response: httpx.Response) -> Batch:
        try:
            body = response.json()
        except ValueError:
            body = {}
        if response.status_code in (200, 202) and body.get("id"):
            with self.db.begin():
                batch = self.batches.find(ctx.company_id, batch_id, for_update=True)
                if batch.status == "sending":
                    actor_id = user_actor_id(self.db, ctx.user_id)
                    now = utcnow()
                    batch.status, batch.notification_dispatch_id, batch.sent_at = "sent", body["id"], now
                    batch.updated_at, batch.updated_by = now, actor_id
                    record_change(
                        self.db, action="batch.sent", resource_type="batch", resource_id=batch.id,
                        company_id=batch.company_id, actor_id=actor_id, now=now, before={"status": "sending"},
                        after={"status": "sent", "notification_dispatch_id": body["id"]},
                    )
                return batch
        if response.status_code == 409:
            # idempotency_conflict: ya existe un envío con este id de lote y otro contenido. No
            # debería pasar (se reenvía lo congelado); se deja "sending" para revisarlo.
            logger.error("Lote %s: notificaciones respondió 409 (%s).", batch_id, body.get("code"))
            raise UpstreamRejected(409, body)
        if 400 <= response.status_code < 500:
            # Notificaciones validó y rechazó: no creó nada. Vuelve a borrador para corregir.
            self._back_to_draft(ctx, batch_id, response.status_code, body)
            raise UpstreamRejected(response.status_code, body)
        logger.warning("Lote %s: notificaciones respondió %s; queda sending.", batch_id, response.status_code)
        raise UpstreamError(
            "Notificaciones falló al crear el envío. El lote quedó 'sending': vuelve a enviarlo.",
            code="notifications_error",
        )

    def _back_to_draft(self, ctx: CompanyContext, batch_id: str, status_code: int, body: dict) -> None:
        with self.db.begin():
            batch = self.batches.find(ctx.company_id, batch_id, for_update=True)
            if batch.status != "sending":
                return
            actor_id = user_actor_id(self.db, ctx.user_id)
            now = utcnow()
            deliveries = self.db.scalars(
                select(BatchDelivery).where(BatchDelivery.batch_id == batch.id, BatchDelivery.is_active.is_(True))
            )
            for delivery in deliveries:  # Baja lógica: quedan como rastro del intento.
                delivery.is_active = False
                delivery.deleted_at = delivery.updated_at = now
                delivery.deleted_by = delivery.updated_by = actor_id
            for row in self.db.scalars(select(BatchFile).where(BatchFile.batch_id == batch.id)):
                row.delivery_id = None
            batch.status = "draft"
            batch.updated_at, batch.updated_by = now, actor_id
            record_change(
                self.db, action="batch.send_rejected", resource_type="batch", resource_id=batch.id,
                company_id=batch.company_id, actor_id=actor_id, now=now, before={"status": "sending"},
                after={"status": "draft", "notifications_status": status_code, "code": body.get("code")},
            )

    # --- Estado del envío --------------------------------------------------

    def delivery_status(self, ctx: CompanyContext, batch_id: str) -> dict:
        """Estado del envío consultado en notificaciones (no se copia aquí)."""
        with self.db.begin():
            batch = self.batches.find(ctx.company_id, batch_id)
            deliveries = list(self.db.scalars(
                select(BatchDelivery)
                .where(BatchDelivery.batch_id == batch.id, BatchDelivery.is_active.is_(True))
                .order_by(BatchDelivery.sequence)
            ))
        if batch.notification_dispatch_id is None:
            raise ConflictError("El lote todavía no tiene un envío en notificaciones.", code="not_sent")
        base = f"/notificaciones/dispatches/{batch.notification_dispatch_id}"
        headers = dict(ctx.auth_headers)
        dispatch = self._get(base, headers)
        messages = self._get(f"{base}/messages", headers, params={"limit": 200})["items"]
        by_reference = {m["consumer_reference"]: m for m in messages}
        return {
            "status": dispatch["status"],
            "counts": dispatch["counts"],
            "deliveries": [
                {
                    "delivery_id": d.id, "provider_id": d.provider_id, "legal_name": d.legal_name,
                    "payment_emails": d.payment_emails,
                    "message_id": by_reference.get(d.id, {}).get("id"),
                    "status": by_reference.get(d.id, {}).get("status"),
                    "sent_at": by_reference.get(d.id, {}).get("sent_at"),
                }
                for d in deliveries
            ],
        }

    @staticmethod
    def _get(path: str, headers: dict, params: dict | None = None) -> dict:
        try:
            response = notifications_client.get(path, headers=headers, params=params, timeout=30)
        except httpx.HTTPError:
            raise UpstreamError("Notificaciones no está disponible.", code="notifications_unavailable") from None
        if response.status_code != 200:
            try:
                body = response.json()
            except ValueError:
                body = {}
            raise UpstreamRejected(response.status_code if response.status_code < 500 else 502, body)
        return response.json()
