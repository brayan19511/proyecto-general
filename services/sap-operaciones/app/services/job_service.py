"""Trabajos masivos: vista previa, encolar, cancelar, reanudar y consultas.

Flujo: 1) vista previa → trabajo "draft" con sus ítems (sin credenciales);
2) encolar con el usuario y la clave SAP del operador → se prueba el inicio de
sesión (no modifica nada) y queda "queued"; 3) el worker (app/worker.py) lo
ejecuta. Cada cambio de estado del trabajo deja un evento en job_events en la
misma transacción.
"""

from datetime import date

from platform_audit import current_trace_id
from sqlalchemy import func, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import CompanyContext
from app.core.config import settings
from app.core.crypto import SecretDecryptionError, decrypt_secret, encrypt_secret
from app.models.common.mixin_model import new_id, utcnow
from app.models.entities import Actor, ChangeHistory, Job, JobEvent, JobItem, SapDatabase, SapSettings
from app.sap.service_layer import (
    COMPANY_DB_PATTERN,
    RESOURCE_PATTERN,
    SapAuthError,
    SapError,
    SapUnavailableError,
    ServiceLayerClient,
)
from app.services import inputs
from app.services.actors import user_actor_id
from app.services.errors import ConflictError, ForbiddenError, InvalidDataError, NotFoundError, UpstreamError

FINISHED = ("completed", "completed_with_errors", "cancelled")


def add_event(db: Session, job: Job, actor_id: str, action: str, details: dict | None = None) -> None:
    """Evento de historial en la transacción en curso (nunca con la clave)."""
    db.add(JobEvent(job_id=job.id, company_id=job.company_id, action=action, details=details or {},
                    trace_id=current_trace_id(), created_by=actor_id))


def _validate_company_db(company_db: str) -> str:
    value = company_db.strip()
    if not COMPANY_DB_PATTERN.fullmatch(value):
        raise InvalidDataError("La base SAP solo admite letras, números y _ (máximo 100).")
    return value


# --- Vista previa (crea el trabajo en borrador)


def _create_draft(db: Session, ctx: CompanyContext, parsed: inputs.Parsed, **fields) -> dict:
    if parsed.errors:
        return {"job": None, "errors": parsed.errors, "duplicates": parsed.duplicates}
    now = utcnow()
    with db.begin():
        actor_id = user_actor_id(db, ctx.user_id)
        job = Job(id=new_id(), company_id=ctx.company_id, status="draft", total_items=len(parsed.items),
                  trace_id=current_trace_id(), created_by=actor_id, created_at=now, **fields)
        db.add(job)
        db.flush()
        # Inserción en bloque: un trabajo puede tener decenas de miles de ítems.
        db.execute(insert(JobItem), [
            {"id": new_id(), "job_id": job.id, "seq": seq, "reference": reference, "payload": payload,
             "status": "pending", "created_at": now, "created_by": actor_id, "updated_at": now,
             "updated_by": actor_id, "is_active": True}
            for seq, (reference, payload) in enumerate(parsed.items, start=1)
        ])
        add_event(db, job, actor_id, "job.created",
                  {"kind": job.kind, "company_db": job.company_db, "items": job.total_items})
    return {"job": job, "errors": [], "duplicates": parsed.duplicates}


def preview_document_action(db: Session, ctx: CompanyContext, *, company_db: str, entity: str, action: str,
                            documents: str) -> dict:
    entity, action = entity.strip(), action.strip()
    if not RESOURCE_PATTERN.fullmatch(entity) or not RESOURCE_PATTERN.fullmatch(action):
        raise InvalidDataError("Entidad y acción: solo letras, números y _, empezando con una letra.")
    parsed = inputs.parse_documents(documents, settings.JOB_MAX_ITEMS)
    return _create_draft(db, ctx, parsed, kind="document_action", company_db=_validate_company_db(company_db),
                         entity=entity, action=action, parameters={})


def preview_reconciliation(db: Session, ctx: CompanyContext, *, company_db: str, recon_date: date,
                           content: bytes, filename: str | None) -> dict:
    company_db = _validate_company_db(company_db)
    parsed = inputs.parse_reconciliations(content, filename, recon_date, settings.JOB_MAX_ITEMS)
    rows = sum(len(payload["InternalReconciliationOpenTransRows"]) for _, payload in parsed.items)
    return _create_draft(db, ctx, parsed, kind="reconciliation", company_db=company_db,
                         parameters={"recon_date": recon_date.isoformat(), "filename": (filename or "")[:255], "rows": rows})


# --- Ciclo de vida


def get_job(db: Session, ctx: CompanyContext, job_id: str) -> Job:
    with db.begin():
        job = db.get(Job, job_id)
    if job is None or job.company_id != ctx.company_id:
        raise NotFoundError("Trabajo no encontrado.")
    return job


def _check_login(base_url: str, company_db: str, sap_user: str, sap_password: str) -> None:
    """Prueba el inicio de sesión antes de encolar: así una clave errónea falla aquí
    y no en el worker. Login/Logout no modifican datos en SAP."""
    try:
        with ServiceLayerClient(base_url, company_db, sap_user, sap_password) as client:
            client.login()
    except SapAuthError as exc:
        raise InvalidDataError(exc.message) from exc
    except SapUnavailableError as exc:
        raise UpstreamError(f"{exc.message} No se pudo comprobar el usuario.") from exc
    except SapError as exc:
        raise UpstreamError(exc.message) from exc


def enqueue(db: Session, ctx: CompanyContext, job_id: str, sap_user: str, sap_password: str) -> Job:
    job = get_job(db, ctx, job_id)
    if job.status != "draft":
        raise ConflictError("Solo se puede ejecutar un trabajo en borrador.")
    base_url = service_layer_url(db, ctx.company_id)
    _check_login(base_url, job.company_db, sap_user, sap_password)
    now = utcnow()
    with db.begin():
        actor_id = user_actor_id(db, ctx.user_id)
        # Condicional: dos clics simultáneos no lo encolan dos veces.
        changed = db.execute(
            update(Job).where(Job.id == job.id, Job.status == "draft").values(
                status="queued", queued_at=now, sap_user=sap_user, service_layer_url=base_url,
                sap_password_encrypted=encrypt_secret(sap_password), credentials_by=actor_id,
                updated_at=now, updated_by=actor_id,
            )
        ).rowcount
        if not changed:
            raise ConflictError("El trabajo ya no está en borrador.")
        add_event(db, job, actor_id, "job.queued", {"sap_user": sap_user})
    return get_job(db, ctx, job_id)


def cancel(db: Session, ctx: CompanyContext, job_id: str) -> Job:
    """Borrador, en cola o detenido: se cancela ya (ítems pendientes → cancelled).
    En proceso: se pide la cancelación y el worker se detiene antes del próximo ítem.
    Lo ya enviado a SAP no se deshace."""
    job = get_job(db, ctx, job_id)
    now = utcnow()
    with db.begin():
        actor_id = user_actor_id(db, ctx.user_id)
        if job.status == "running":
            db.execute(update(Job).where(Job.id == job.id, Job.status == "running")
                       .values(cancel_requested_at=now, updated_at=now, updated_by=actor_id))
            add_event(db, job, actor_id, "job.cancel_requested")
        elif job.status in ("draft", "queued", "failed"):
            # Condicional: si el worker lo tomó justo ahora, no se cancela por aquí.
            changed = db.execute(
                update(Job).where(Job.id == job.id, Job.status.in_(("draft", "queued", "failed"))).values(
                    status="cancelled", cancel_requested_at=now, finished_at=now, updated_at=now, updated_by=actor_id)
            ).rowcount
            if not changed:
                raise ConflictError("El trabajo cambió de estado: recarga e intenta de nuevo.")
            cancelled = db.execute(
                update(JobItem).where(JobItem.job_id == job.id, JobItem.status == "pending")
                .values(status="cancelled", finished_at=now, updated_at=now, updated_by=actor_id)
            ).rowcount
            db.execute(update(Job).where(Job.id == job.id).values(cancelled_items=Job.cancelled_items + cancelled))
            add_event(db, job, actor_id, "job.cancelled", {"cancelled_items": cancelled})
        else:
            raise ConflictError("El trabajo ya terminó.")
    return get_job(db, ctx, job_id)


def resume(db: Session, ctx: CompanyContext, job_id: str, sap_user: str | None, sap_password: str | None) -> Job:
    """Vuelve a encolar un trabajo detenido ("failed"): sigue con los ítems pendientes.
    Los "uncertain" no se repiten. Con usuario y clave nuevos (p. ej. si la clave
    cambió) se prueban y reemplazan; si no, usa los guardados."""
    job = get_job(db, ctx, job_id)
    if job.status != "failed":
        raise ConflictError("Solo se puede reanudar un trabajo detenido.")
    # Se reanuda con la URL vigente de la empresa (quizá corregida tras el fallo).
    base_url = service_layer_url(db, ctx.company_id)
    values: dict = {"service_layer_url": base_url}
    if sap_user and sap_password:
        _check_login(base_url, job.company_db, sap_user, sap_password)
        values |= {"sap_user": sap_user, "sap_password_encrypted": encrypt_secret(sap_password)}
    elif not job.sap_password_encrypted:
        raise InvalidDataError("Ingresa el usuario y la clave SAP.")
    now = utcnow()
    with db.begin():
        actor_id = user_actor_id(db, ctx.user_id)
        if "sap_password_encrypted" in values:
            values["credentials_by"] = actor_id  # Quien ingresa credenciales nuevas pasa a ser su dueño.
        changed = db.execute(
            update(Job).where(Job.id == job.id, Job.status == "failed").values(
                status="queued", queued_at=now, error_message=None, updated_at=now, updated_by=actor_id, **values)
        ).rowcount
        if not changed:
            raise ConflictError("El trabajo cambió de estado: recarga e intenta de nuevo.")
        add_event(db, job, actor_id, "job.resumed", {"new_credentials": bool(values)})
    return get_job(db, ctx, job_id)


def can_reveal(db: Session, ctx: CompanyContext, job: Job) -> bool:
    """Ver la clave guardada: solo el administrador de plataforma (decisión del usuario,
    2026-10-04). El usuario SAP lo ve cualquiera que vea el trabajo (no es secreto).
    credentials_by se conserva como dato de auditoría (quién ingresó la clave)."""
    return bool(job.sap_password_encrypted) and ctx.is_platform_admin


def reveal_credentials(db: Session, ctx: CompanyContext, job_id: str) -> dict:
    """Deja evento con quién la vio. Sin permiso: 403 (la ruta exige además ver trabajos)."""
    job = get_job(db, ctx, job_id)
    if job.sap_password_encrypted and not can_reveal(db, ctx, job):
        raise ForbiddenError("Solo el administrador de plataforma puede ver la clave guardada.")
    if not job.sap_password_encrypted:
        raise NotFoundError("Este trabajo no tiene credenciales guardadas.")
    try:
        password = decrypt_secret(job.sap_password_encrypted)
    except SecretDecryptionError as exc:
        raise ConflictError("No se pudo descifrar la credencial (¿se retiró la clave de cifrado?).") from exc
    with db.begin():
        add_event(db, job, user_actor_id(db, ctx.user_id), "job.credentials_viewed", {"sap_user": job.sap_user})
    return {"sap_user": job.sap_user, "sap_password": password}


# --- Consultas


def list_jobs(db: Session, ctx: CompanyContext, *, status: str | None, kind: str | None,
              limit: int, offset: int) -> tuple[list[dict], int]:
    conditions = [Job.company_id == ctx.company_id]
    if status:
        conditions.append(Job.status == status)
    if kind:
        conditions.append(Job.kind == kind)
    with db.begin():
        total = db.scalar(select(func.count()).select_from(Job).where(*conditions))
        rows = db.execute(
            select(Job, Actor.subject_ref).join(Actor, Actor.id == Job.created_by)
            .where(*conditions).order_by(Job.created_at.desc()).limit(limit).offset(offset)
        ).all()
    return [{"job": job, "created_by_user": user} for job, user in rows], total


def list_items(db: Session, ctx: CompanyContext, job_id: str, *, status: str | None, reference: str | None,
               limit: int, offset: int) -> tuple[list[JobItem], int]:
    get_job(db, ctx, job_id)
    conditions = [JobItem.job_id == job_id]
    if status:
        conditions.append(JobItem.status == status)
    if reference:
        conditions.append(JobItem.reference == reference.strip())
    with db.begin():
        total = db.scalar(select(func.count()).select_from(JobItem).where(*conditions))
        items = db.scalars(select(JobItem).where(*conditions).order_by(JobItem.seq).limit(limit).offset(offset)).all()
    return list(items), total


def list_events(db: Session, ctx: CompanyContext, job_id: str) -> list[dict]:
    get_job(db, ctx, job_id)
    with db.begin():
        rows = db.execute(
            select(JobEvent, Actor.kind, Actor.subject_ref).join(Actor, Actor.id == JobEvent.created_by)
            .where(JobEvent.job_id == job_id).order_by(JobEvent.created_at, JobEvent.id)
        ).all()
    return [
        {"action": e.action, "details": e.details, "actor_kind": kind, "actor": ref, "created_at": e.created_at}
        for e, kind, ref in rows
    ]


# --- Bases SAP sugeridas por empresa


def list_databases(db: Session, ctx: CompanyContext) -> list[SapDatabase]:
    with db.begin():
        return list(db.scalars(
            select(SapDatabase).where(SapDatabase.company_id == ctx.company_id, SapDatabase.is_active.is_(True))
            .order_by(SapDatabase.company_db)
        ).all())


def create_database(db: Session, ctx: CompanyContext, company_db: str, label: str | None) -> SapDatabase:
    company_db = _validate_company_db(company_db)
    try:
        with db.begin():
            actor_id = user_actor_id(db, ctx.user_id)
            row = SapDatabase(id=new_id(), company_id=ctx.company_id, company_db=company_db,
                              label=(label or "").strip() or None, created_by=actor_id)
            db.add(row)
            _history(db, ctx, actor_id, "sap_database.created", row.id, {},
                     {"company_db": row.company_db, "label": row.label, "is_active": True})
    except IntegrityError as exc:
        raise ConflictError(f"La base {company_db} ya está en la lista.") from exc
    return row


def delete_database(db: Session, ctx: CompanyContext, database_id: str) -> None:
    """Baja lógica: deja de sugerirse; los trabajos que la usaron no cambian."""
    now = utcnow()
    with db.begin():
        row = db.get(SapDatabase, database_id)
        if row is None or row.company_id != ctx.company_id or not row.is_active:
            raise NotFoundError("Base SAP no encontrada.")
        actor_id = user_actor_id(db, ctx.user_id)
        row.is_active = False
        row.deleted_at = now
        row.deleted_by = actor_id
        row.updated_at = now
        row.updated_by = actor_id
        _history(db, ctx, actor_id, "sap_database.deleted", row.id,
                 {"company_db": row.company_db, "is_active": True}, {"is_active": False})


def _history(db: Session, ctx: CompanyContext, actor_id: str, action: str, resource_id: str,
             before: dict, after: dict) -> None:
    db.add(ChangeHistory(company_id=ctx.company_id, action=action, resource_type="sap_database",
                         resource_id=resource_id, before=before, after=after,
                         trace_id=current_trace_id(), created_by=actor_id))


# --- Configuración SAP de la empresa (URL del Service Layer)


def _company_settings(db: Session, company_id: str) -> SapSettings | None:
    return db.scalar(select(SapSettings).where(SapSettings.company_id == company_id, SapSettings.is_active.is_(True)))


def service_layer_url(db: Session, company_id: str) -> str:
    """URL vigente: la de la empresa o, si no tiene, la del despliegue."""
    with db.begin():
        row = _company_settings(db, company_id)
    url = row.service_layer_url if row else settings.SAP_SERVICE_LAYER_URL
    if not url:
        raise ConflictError("El Service Layer de SAP no está configurado para esta empresa.")
    return url


def get_settings(db: Session, ctx: CompanyContext) -> dict:
    with db.begin():
        row = _company_settings(db, ctx.company_id)
    return {
        "service_layer_url": row.service_layer_url if row else settings.SAP_SERVICE_LAYER_URL,
        "source": "company" if row else "default",
        "verify_tls": settings.SAP_VERIFY_TLS,
        "updated_at": row.updated_at if row else None,
    }


def update_settings(db: Session, ctx: CompanyContext, url: str | None) -> dict:
    """Solo administrador de plataforma (lo exige la ruta). url vacía = volver a la
    del despliegue. La fila anterior se da de baja (no se edita) y queda historial."""
    now = utcnow()
    with db.begin():
        actor_id = user_actor_id(db, ctx.user_id)
        current = _company_settings(db, ctx.company_id)
        before = {"service_layer_url": current.service_layer_url} if current else {}
        if current:
            if url and current.service_layer_url == url:
                return get_settings_after(db, ctx)
            current.is_active = False
            current.deleted_at = now
            current.deleted_by = actor_id
            current.updated_at = now
            current.updated_by = actor_id
            db.flush()  # Libera el índice único antes de insertar la nueva.
        row_id = None
        if url:
            row = SapSettings(id=new_id(), company_id=ctx.company_id, service_layer_url=url, created_by=actor_id)
            db.add(row)
            row_id = row.id
        db.add(ChangeHistory(company_id=ctx.company_id, action="sap_settings.updated", resource_type="sap_settings",
                             resource_id=row_id or (current.id if current else ctx.company_id), before=before,
                             after={"service_layer_url": url} if url else {"service_layer_url": None},
                             trace_id=current_trace_id(), created_by=actor_id))
    return get_settings(db, ctx)


def get_settings_after(db: Session, ctx: CompanyContext) -> dict:
    """Sin cambios: devuelve lo vigente (se llama dentro de una transacción ya abierta)."""
    row = _company_settings(db, ctx.company_id)
    return {"service_layer_url": row.service_layer_url, "source": "company", "verify_tls": settings.SAP_VERIFY_TLS,
            "updated_at": row.updated_at}


def get_item(db: Session, ctx: CompanyContext, job_id: str, seq: int) -> JobItem:
    get_job(db, ctx, job_id)
    with db.begin():
        item = db.scalar(select(JobItem).where(JobItem.job_id == job_id, JobItem.seq == seq))
    if item is None:
        raise NotFoundError("Ítem no encontrado.")
    return item


def all_items(db: Session, ctx: CompanyContext, job_id: str) -> list:
    """Todos los ítems para la descarga (solo columnas livianas, sin JSON)."""
    get_job(db, ctx, job_id)
    with db.begin():
        return db.execute(
            select(JobItem.seq, JobItem.reference, JobItem.status, JobItem.http_status, JobItem.sap_error,
                   JobItem.started_at, JobItem.finished_at).where(JobItem.job_id == job_id).order_by(JobItem.seq)
        ).all()
