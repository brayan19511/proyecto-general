"""Lotes de constancias (docs/modelo-datos.md, acuerdos 1 a 5).

- Crear: se leen los PDFs (fuera de la transacción: el OCR puede tardar), y
  después se guardan el lote y sus archivos con lo extraído en UNA transacción.
- Ver: en un borrador los grupos se calculan con el maestro ACTUAL (si se
  corrige un proveedor, el lote se actualiza solo); en un lote sending/sent son
  los congelados al enviar (batch_deliveries).
- Quitar un archivo o descartar el lote: baja lógica, solo en borrador.
"""

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace
from zipfile import ZIP_DEFLATED, ZipFile

from platform_audit import step
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.common.mixin_model import utcnow
from app.models.entities import Batch, BatchDelivery, BatchFile, Provider
from app.schemas.batches import (
    BatchCounts,
    BatchFileOut,
    BatchOut,
    BatchSummaryOut,
    GroupOut,
    GroupPayment,
    GroupTotal,
)
from app.services.actors import user_actor_id
from app.services.errors import ConflictError, InvalidDataError, NotFoundError
from app.services.grouping import PaymentProviderProcessor
from app.services.history import record_change
from app.services.pdf_reader import PaymentPdfParser

MAX_FILES = 100  # Acuerdo 5.
MAX_FILE_BYTES = 25 * 1024 * 1024  # Ningún PDF puede superar el límite de un correo en notificaciones.
_DATE = re.compile(r"(?P<d>\d{1,2})[/-](?P<m>\d{1,2})[/-](?P<y>\d{4})")


@dataclass(frozen=True)
class Upload:
    filename: str | None
    content: bytes


@dataclass(frozen=True)
class _Parsed:
    filename: str
    content: bytes
    sha256: str
    result: dict


def _clean_filename(raw: str | None, index: int) -> str:
    """Nombre seguro para mostrar: sin rutas ni caracteres de control."""
    name = unicodedata.normalize("NFC", raw or "").replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(ch for ch in name if unicodedata.category(ch)[0] != "C").strip()
    return (name or f"constancia_{index}.pdf")[:255]


def _json_safe(value):
    """El lector devuelve Decimal: en JSON se guardan como texto."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    return value


def _operation_date(operation: dict) -> date | None:
    for value in (operation.get("fecha_proceso"), operation.get("fecha_envio")):
        match = _DATE.search(value or "")
        if match:
            try:
                return date(int(match["y"]), int(match["m"]), int(match["d"]))
            except ValueError:
                continue
    return None


def _payment_key(f: BatchFile) -> tuple:
    """Datos que identifican un pago para el aviso de repetido."""
    return (f.beneficiary_tax_id, f.account, f.currency, f.amount, f.operation_date)


def _operation_number(f: BatchFile) -> str | None:
    value = ((f.extracted or {}).get("datos_operacion") or {}).get("numero_operacion")
    if not value:
        return None
    return re.sub(r"\s+", "", str(value)) or None


def parse_uploads(uploads: list[Upload]) -> list[_Parsed]:
    """Valida cantidad, tamaño y duplicados, y lee cada PDF (sin base de datos)."""
    if not 1 <= len(uploads) <= MAX_FILES:
        raise InvalidDataError(f"Un lote lleva entre 1 y {MAX_FILES} constancias.")
    parser = PaymentPdfParser()
    parsed, seen = [], {}
    for index, upload in enumerate(uploads, start=1):
        filename = _clean_filename(upload.filename, index)
        if len(upload.content) > MAX_FILE_BYTES:
            raise InvalidDataError(f"{filename}: supera {MAX_FILE_BYTES // (1024 * 1024)} MB.")
        digest = hashlib.sha256(upload.content).hexdigest()
        if digest in seen:
            raise InvalidDataError(f"{filename} es el mismo archivo que {seen[digest]}.", code="duplicate_file")
        seen[digest] = filename
        parsed.append(_Parsed(filename, upload.content, digest, parser.parse(filename, upload.content)))
    return parsed


class BatchService:
    def __init__(self, db: Session):
        self.db = db

    # --- Crear -------------------------------------------------------------

    def create(self, *, company_id: str, user_id: str, reference: str | None, parsed: list[_Parsed]) -> Batch:
        with step("batch.create"), self.db.begin():
            actor_id = user_actor_id(self.db, user_id)
            now = utcnow()
            batch = Batch(company_id=company_id, reference=reference, status="draft", created_at=now, created_by=actor_id)
            self.db.add(batch)
            self.db.flush()
            sent_before = self._already_sent(company_id, [p.sha256 for p in parsed])
            rows = [
                self._file_row(batch, item, sequence, sent_before.get(item.sha256), actor_id, now)
                for sequence, item in enumerate(parsed, start=1)
            ]
            self._mark_same_payment_sent(company_id, [r for r in rows if r.already_sent_in_batch_id is None])
            self.db.add_all(rows)
            record_change(
                self.db, action="batch.create", resource_type="batch", resource_id=batch.id, company_id=company_id,
                actor_id=actor_id, now=now, before={},
                after={"reference": reference, "files": len(parsed),
                       "errors": sum(1 for p in parsed if not p.result["procesado"])},
            )
        return batch

    def _already_sent(self, company_id: str, digests: list[str]) -> dict[str, str]:
        """sha256 → lote enviado que ya tenía ese PDF (aviso, acuerdo 3)."""
        rows = self.db.execute(
            select(BatchFile.sha256, BatchFile.batch_id)
            .join(Batch, Batch.id == BatchFile.batch_id)
            .where(BatchFile.company_id == company_id, BatchFile.sha256.in_(digests),
                   BatchFile.is_active.is_(True), Batch.status == "sent")
            .order_by(Batch.sent_at)
        )
        found: dict[str, str] = {}
        for digest, batch_id in rows:
            found.setdefault(digest, batch_id)
        return found

    def _mark_same_payment_sent(self, company_id: str, rows: list[BatchFile]) -> None:
        """Aviso por datos (acuerdo 2026-10-01): otro PDF (reescaneado, exportado
        de nuevo) con el mismo pago ya enviado. Mismo RUC/DNI, cuenta, moneda,
        monto y fecha; si ambos tienen número de operación, también debe
        coincidir. Solo avisa: no impide enviar."""
        keyed = [r for r in rows if r.parse_status == "parsed" and None not in _payment_key(r)]
        if not keyed:
            return
        candidates = self.db.scalars(
            select(BatchFile)
            .join(Batch, Batch.id == BatchFile.batch_id)
            .where(
                BatchFile.company_id == company_id, BatchFile.is_active.is_(True), Batch.status == "sent",
                BatchFile.beneficiary_tax_id.in_({r.beneficiary_tax_id for r in keyed}),
                BatchFile.amount.in_({r.amount for r in keyed}),
            )
            .order_by(Batch.sent_at)
        )
        sent: dict[tuple, list[BatchFile]] = {}
        for c in candidates:
            sent.setdefault(_payment_key(c), []).append(c)
        for row in keyed:
            for c in sent.get(_payment_key(row), []):
                ours, theirs = _operation_number(row), _operation_number(c)
                if ours and theirs and ours != theirs:
                    continue
                row.already_sent_in_batch_id, row.already_sent_match = c.batch_id, "data"
                break

    @staticmethod
    def _file_row(batch: Batch, item: _Parsed, sequence: int, sent_in: str | None, actor_id: str, now) -> BatchFile:
        result = item.result
        row = BatchFile(
            company_id=batch.company_id, batch_id=batch.id, sequence=sequence, original_filename=item.filename,
            size_bytes=len(item.content), sha256=item.sha256, content=item.content,
            parse_status="parsed" if result["procesado"] else "error",
            parse_error=(result["error"] or "")[:500] or None, used_ocr=result["used_ocr"],
            already_sent_in_batch_id=sent_in, already_sent_match="file" if sent_in else None,
            created_at=now, created_by=actor_id,
        )
        if result["procesado"]:
            destination, operation = result["datos_destino"], result["datos_operacion"]
            row.beneficiary_name = (destination.get("titular") or "")[:255] or None
            row.beneficiary_tax_id = (destination.get("ruc") or "")[:30] or None
            row.account = (destination.get("cuenta") or "")[:60] or None
            row.currency = destination.get("moneda")
            row.amount = destination.get("monto_decimal")
            row.operation_date = _operation_date(operation)
            row.extracted = _json_safe({"datos_destino": destination, "datos_operacion": operation})
        return row

    # --- Consultar ---------------------------------------------------------

    def list(self, company_id: str, *, status: str | None, limit: int, offset: int) -> tuple[list[BatchSummaryOut], int]:
        with self.db.begin():
            condition = [Batch.company_id == company_id, Batch.is_active.is_(True)]
            if status:
                condition.append(Batch.status == status)
            total = self.db.scalar(select(func.count()).select_from(Batch).where(*condition))
            file_count = (
                select(func.count()).where(BatchFile.batch_id == Batch.id, BatchFile.is_active.is_(True))
                .correlate(Batch).scalar_subquery()
            )
            rows = self.db.execute(
                select(Batch, file_count).where(*condition)
                .order_by(Batch.created_at.desc(), Batch.id.desc()).limit(limit).offset(offset)
            )
            return [_summary(batch, count) for batch, count in rows], total

    def get(self, company_id: str, batch_id: str) -> BatchOut:
        with self.db.begin():
            batch = self.find(company_id, batch_id)
            files = self._files(batch.id)
            groups = self.groups(batch, files)
            return _detail(batch, files, groups)

    def find(self, company_id: str, batch_id: str, *, for_update: bool = False) -> Batch:
        query = select(Batch).where(Batch.id == batch_id, Batch.company_id == company_id, Batch.is_active.is_(True))
        if for_update:
            query = query.with_for_update()
        batch = self.db.scalar(query)
        if batch is None:
            raise NotFoundError("Lote no encontrado.")
        return batch

    def _files(self, batch_id: str) -> list[BatchFile]:
        """Archivos activos del lote, sin leer sus bytes (content es deferred)."""
        return list(self.db.scalars(
            select(BatchFile).where(BatchFile.batch_id == batch_id, BatchFile.is_active.is_(True))
            .order_by(BatchFile.sequence)
        ))

    def groups(self, batch: Batch, files: list[BatchFile]) -> list[dict]:
        """Grupos del lote en el formato del agrupamiento (claves de proyecto-05)."""
        parsed = [f for f in files if f.parse_status == "parsed"]
        if batch.status == "draft":
            providers = list(self.db.scalars(
                select(Provider).where(Provider.company_id == batch.company_id, Provider.is_active.is_(True))
            ))
            return PaymentProviderProcessor(providers).group([_payment(f) for f in parsed])
        # sending / sent: lo congelado. Cada entrega se agrupa con la copia del proveedor.
        deliveries = self.db.scalars(
            select(BatchDelivery)
            .where(BatchDelivery.batch_id == batch.id, BatchDelivery.is_active.is_(True))
            .order_by(BatchDelivery.sequence)
        )
        groups = []
        for delivery in deliveries:
            mine = [_payment(f) for f in parsed if f.delivery_id == delivery.id]
            groups.extend(_FrozenProcessor(delivery).group(mine))
        return groups

    def file_content(self, company_id: str, batch_id: str, file_id: str) -> tuple[str, bytes]:
        with self.db.begin():
            batch = self.find(company_id, batch_id)
            row = self.db.scalar(
                select(BatchFile).where(BatchFile.id == file_id, BatchFile.batch_id == batch.id)
            )
            if row is None:
                raise NotFoundError("Constancia no encontrada.")
            return row.original_filename, row.content

    def zip(self, company_id: str, batch_id: str) -> bytes:
        """Constancias leídas, con el nombre titular + fecha (como proyecto-05)."""
        with self.db.begin():
            batch = self.find(company_id, batch_id)
            files = {f.id: f for f in self._files(batch.id)}
            names = {
                payment["file_id"]: payment["suggested_filename"]
                for group in self.groups(batch, list(files.values()))
                for payment in group["pagos"]
            }
            if not names:
                raise ConflictError("El lote no tiene constancias leídas para descargar.")
            buffer, used = BytesIO(), set()
            with ZipFile(buffer, mode="w", compression=ZIP_DEFLATED) as archive:
                for file_id, name in names.items():
                    arcname = unique_filename(name, used)
                    used.add(arcname)
                    archive.writestr(arcname, files[file_id].content)
            return buffer.getvalue()

    # --- Corregir un borrador ----------------------------------------------

    def remove_file(self, *, company_id: str, user_id: str, batch_id: str, file_id: str) -> None:
        """Quita una constancia del borrador (p. ej. una ilegible que bloquea el envío)."""
        with step("batch.file.delete"), self.db.begin():
            batch = self._draft(company_id, batch_id)
            row = self.db.scalar(
                select(BatchFile).where(BatchFile.id == file_id, BatchFile.batch_id == batch.id,
                                        BatchFile.is_active.is_(True))
            )
            if row is None:
                raise NotFoundError("Constancia no encontrada.")
            actor_id = user_actor_id(self.db, user_id)
            now = utcnow()
            row.is_active = False
            row.deleted_at = row.updated_at = now
            row.deleted_by = row.updated_by = actor_id
            record_change(
                self.db, action="batch.file.delete", resource_type="batch_file", resource_id=row.id,
                company_id=company_id, actor_id=actor_id, now=now,
                before={"batch_id": batch.id, "original_filename": row.original_filename}, after={},
            )

    def discard(self, *, company_id: str, user_id: str, batch_id: str, reason: str | None) -> None:
        """Baja lógica del borrador (acuerdo 4). Un lote sending/sent es evidencia: 409."""
        with step("batch.delete"), self.db.begin():
            batch = self._draft(company_id, batch_id)
            actor_id = user_actor_id(self.db, user_id)
            now = utcnow()
            batch.is_active = False
            batch.deleted_at = batch.updated_at = now
            batch.deleted_by = batch.updated_by = actor_id
            record_change(
                self.db, action="batch.delete", resource_type="batch", resource_id=batch.id, company_id=company_id,
                actor_id=actor_id, now=now, before={"status": batch.status}, after={}, reason=reason,
            )

    def _draft(self, company_id: str, batch_id: str) -> Batch:
        batch = self.find(company_id, batch_id, for_update=True)
        if batch.status != "draft":
            raise ConflictError(f"El lote está {batch.status}: ya no se puede modificar.", code="invalid_status")
        return batch


class _FrozenProcessor(PaymentProviderProcessor):
    """Agrupa las constancias de una entrega con la copia del proveedor al enviar
    (no con el maestro actual, que pudo cambiar después)."""

    def __init__(self, delivery: BatchDelivery):
        super().__init__([])
        self._provider = SimpleNamespace(
            id=delivery.provider_id, tax_id=delivery.tax_id, legal_name=delivery.legal_name,
            payment_emails=delivery.payment_emails,
        )

    def _find_provider(self, ruc, titular):
        return self._provider


def _payment(row: BatchFile) -> dict:
    """Constancia guardada → entrada del agrupamiento (formato del lector)."""
    destination = dict(row.extracted["datos_destino"])
    destination["monto_decimal"] = row.amount  # Decimal desde la columna, no el texto del JSON.
    return {"file_id": row.id, "archivo": row.original_filename,
            "datos_destino": destination, "datos_operacion": row.extracted["datos_operacion"]}


def unique_filename(filename: str, used: set[str]) -> str:
    """Como _deduplicate_filename de proyecto-05: nombre_2.pdf, nombre_3.pdf…"""
    if filename not in used:
        return filename
    stem, extension = filename.rsplit(".", 1)
    counter = 2
    while f"{stem}_{counter}.{extension}" in used:
        counter += 1
    return f"{stem}_{counter}.{extension}"


def ready_to_send(files: list[BatchFile], groups: list[dict]) -> bool:
    return (
        bool(groups)
        and not any(f.parse_status == "error" for f in files)
        and all(g["status"] == "READY" for g in groups)
    )


def _summary(batch: Batch, file_count: int) -> BatchSummaryOut:
    return BatchSummaryOut(
        id=batch.id, reference=batch.reference, status=batch.status, file_count=file_count,
        notification_dispatch_id=batch.notification_dispatch_id, created_at=batch.created_at, sent_at=batch.sent_at,
    )


def _detail(batch: Batch, files: list[BatchFile], groups: list[dict]) -> BatchOut:
    return BatchOut(
        **_summary(batch, len(files)).model_dump(),
        ready_to_send=batch.status == "draft" and ready_to_send(files, groups),
        counts=BatchCounts(
            files=len(files), parsed=sum(1 for f in files if f.parse_status == "parsed"),
            errors=sum(1 for f in files if f.parse_status == "error"), groups=len(groups),
            missing_provider=sum(1 for g in groups if g["status"] == "MISSING_PROVIDER"),
            missing_email=sum(1 for g in groups if g["status"] == "MISSING_PAYMENT_EMAIL"),
        ),
        files=[
            BatchFileOut(
                id=f.id, sequence=f.sequence, original_filename=f.original_filename, size_bytes=f.size_bytes,
                parse_status=f.parse_status, parse_error=f.parse_error, used_ocr=f.used_ocr,
                beneficiary_name=f.beneficiary_name, beneficiary_tax_id=f.beneficiary_tax_id, account=f.account,
                currency=f.currency, amount=str(f.amount) if f.amount is not None else None,
                operation_date=f.operation_date, already_sent_in_batch_id=f.already_sent_in_batch_id,
                already_sent_match=f.already_sent_match,
            )
            for f in files
        ],
        groups=[_group_out(g) for g in groups],
    )


def _group_out(group: dict) -> GroupOut:
    return GroupOut(
        status=group["status"], provider_id=group["provider_id"], provider_name=group["proveedor"],
        provider_tax_id=group["provider_tax_id"], pdf_holder=group["titular_pdf"],
        payment_emails=group["emails_payments"], payment_count=group["cantidad_pagos"],
        totals=[GroupTotal(currency=t["moneda"], symbol=t["moneda_simbolo"], total=t["total"]) for t in group["totales"]],
        payments=[
            GroupPayment(
                file_id=p["file_id"], suggested_filename=p["suggested_filename"], currency=p["moneda"],
                amount=p["monto_decimal"], account=p["cuenta"], reference=p["referencia"],
                process_date=p["fecha_proceso"] or p["fecha_envio"],
            )
            for p in group["pagos"]
        ],
    )
