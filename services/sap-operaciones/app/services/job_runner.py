"""Ejecución de trabajos (lo usa el worker, app/worker.py).

Reglas (acuerdo del usuario, 2026-10-04):
- Un ítem por vez. Antes de llamar a SAP se guarda "running"; el resultado se
  guarda apenas llega. Así, si el proceso cae, se sabe exactamente qué ítem
  quedó en el aire.
- Sin reintentos automáticos de llamadas que modifican SAP:
  - SAP responde error → ítem "failed" con el mensaje de SAP; se sigue.
  - Se cortó después de enviar → ítem "uncertain" (revisar en SAP); se sigue.
  - No hubo conexión o la sesión no se pudo abrir → el ítem vuelve a "pending"
    y el trabajo queda "failed" (detenido): se puede reanudar después.
- Varios workers pueden correr a la vez: cada uno toma un trabajo distinto
  (SKIP LOCKED) y lo mantiene con un bloqueo que renueva en cada ítem. Si un
  worker cae, al vencer su bloqueo otro retoma el trabajo y el ítem que estaba
  en "running" pasa a "uncertain".
"""

import logging
from datetime import timedelta

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.crypto import SecretDecryptionError, decrypt_secret
from app.models.common.mixin_model import utcnow
from app.models.entities import Job, JobItem
from app.sap.service_layer import (
    SapAuthError,
    SapConnectionError,
    SapRequestError,
    SapUnavailableError,
    ServiceLayerClient,
    document_action_path,
)
from app.services.actors import WORKER, system_actor_id
from app.services.job_service import add_event

logger = logging.getLogger("sap-operaciones.worker")

UNCERTAIN_CRASH = "El worker se detuvo durante la llamada a SAP: revisar en SAP si se aplicó."
CHUNK = 500  # Ítems pendientes que se leen por vez (un trabajo puede tener decenas de miles).


class Released(Exception):
    """El worker se detiene: devolvió el trabajo a la cola."""


class LockLost(Exception):
    """El bloqueo del trabajo venció y otro worker lo tomó: este no debe seguir."""


def _lease():
    return utcnow() + timedelta(seconds=settings.WORKER_LOCK_SECONDS)


def recover_stale(db: Session) -> int:
    """Trabajos "running" con el bloqueo vencido (worker caído): el ítem en curso
    pasa a "uncertain" y el trabajo vuelve a la cola para seguir con los pendientes."""
    now = utcnow()
    with db.begin():
        stale = db.scalars(
            select(Job).where(Job.status == "running", Job.locked_until < now).with_for_update(skip_locked=True)
        ).all()
        actor_id = system_actor_id(db, WORKER) if stale else None
        for job in stale:
            uncertain = db.execute(
                update(JobItem).where(JobItem.job_id == job.id, JobItem.status == "running")
                .values(status="uncertain", sap_error=UNCERTAIN_CRASH, finished_at=now, updated_at=now, updated_by=actor_id)
            ).rowcount
            job.uncertain_items += uncertain
            job.status = "queued"
            job.locked_by = None
            job.locked_until = None
            add_event(db, job, actor_id, "job.recovered", {"uncertain_items": uncertain})
            logger.warning("Trabajo %s retomado: worker caído, %s ítems inciertos.", job.id, uncertain)
    return len(stale)


def claim(db: Session, worker_id: str) -> str | None:
    """Toma el trabajo en cola más antiguo que nadie tenga tomado."""
    now = utcnow()
    with db.begin():
        job = db.scalars(
            select(Job).where(Job.status == "queued").order_by(Job.queued_at).limit(1).with_for_update(skip_locked=True)
        ).first()
        if job is None:
            return None
        job.status = "running"
        job.locked_by = worker_id
        job.locked_until = _lease()
        job.started_at = job.started_at or now
        job.updated_at = now
        return job.id


def run(db: Session, job_id: str, worker_id: str, should_stop=lambda: False) -> None:
    with db.begin():
        job = db.get(Job, job_id)
        company_db, sap_user, encrypted = job.company_db, job.sap_user, job.sap_password_encrypted
        base_url = job.service_layer_url
    try:
        password = decrypt_secret(encrypted or "")
    except SecretDecryptionError:
        _stop(db, job_id, "No se pudo descifrar la clave SAP guardada: reanuda con usuario y clave.")
        return

    try:
        with ServiceLayerClient(base_url, company_db, sap_user, password) as client:
            client.login()
            stopped = _process_items(db, job_id, worker_id, client, should_stop)
    except SapAuthError as exc:
        _stop(db, job_id, exc.message)
        return
    except SapUnavailableError as exc:
        _stop(db, job_id, f"{exc.message} Reanuda el trabajo cuando se resuelva.")
        return
    except LockLost:
        logger.warning("Trabajo %s: bloqueo perdido; lo continúa otro worker.", job_id)
        return
    except Released:
        logger.info("Trabajo %s devuelto a la cola (el worker se detiene).", job_id)
        return
    if stopped is not None:
        _stop(db, job_id, stopped)
        return
    _finish(db, job_id)


def _process_items(db: Session, job_id: str, worker_id: str, client: ServiceLayerClient, should_stop) -> str | None:
    """Ejecuta los pendientes. Devuelve un mensaje si el trabajo debe detenerse."""
    while True:
        with db.begin():
            items = db.execute(
                select(JobItem.id, JobItem.reference, JobItem.payload)
                .where(JobItem.job_id == job_id, JobItem.status == "pending").order_by(JobItem.seq).limit(CHUNK)
            ).all()
            job = db.get(Job, job_id)
            kind, entity, action = job.kind, job.entity, job.action
        if not items:
            return None
        for item_id, reference, payload in items:
            # Cancelación pedida y renovación del bloqueo, antes de cada ítem.
            with db.begin():
                job = db.get(Job, job_id, populate_existing=True)
                if job.locked_by != worker_id:
                    raise LockLost()  # Otro worker lo retomó (este se demoró más que el bloqueo).
                if job.cancel_requested_at is not None:
                    return None
                if should_stop():
                    # SIGTERM: vuelve a la cola con sus pendientes; lo sigue otro worker.
                    job.status = "queued"
                    job.locked_by = None
                    job.locked_until = None
                    raise Released()
                if kind == "document_action":
                    path, body = document_action_path(entity, action, reference), None
                else:
                    path, body = "InternalReconciliations", payload
                now = utcnow()
                job.locked_until = _lease()
                # Lo que se envía queda guardado antes de enviarlo (también si luego es incierto).
                db.execute(update(JobItem).where(JobItem.id == item_id).values(
                    status="running", started_at=now, updated_at=now,
                    request={"method": "POST", "path": path, "body": body}))
            try:
                status_code, answer = client.post(path, body)
                _save_item(db, job_id, item_id, "succeeded", status_code, None, answer)
            except SapRequestError as exc:
                _save_item(db, job_id, item_id, "failed", exc.http_status, exc.message, exc.body)
            except SapConnectionError as exc:
                _save_item(db, job_id, item_id, "uncertain", None, exc.message, None)
            except (SapUnavailableError, SapAuthError) as exc:
                # No llegó a SAP: el ítem vuelve a pendiente y el trabajo se detiene.
                with db.begin():
                    db.execute(update(JobItem).where(JobItem.id == item_id)
                               .values(status="pending", started_at=None, updated_at=utcnow()))
                return exc.message if isinstance(exc, SapAuthError) else f"{exc.message} Reanuda el trabajo cuando se resuelva."


COUNTER = {"succeeded": Job.succeeded_items, "failed": Job.failed_items, "uncertain": Job.uncertain_items}


def _save_item(db: Session, job_id: str, item_id: str, status: str, http_status: int | None, error: str | None,
               answer) -> None:
    now = utcnow()
    with db.begin():
        db.execute(update(JobItem).where(JobItem.id == item_id).values(
            status=status, http_status=http_status, sap_error=error, finished_at=now, updated_at=now,
            response={"status": http_status, "body": answer} if http_status is not None else None))
        counter = COUNTER[status]
        db.execute(update(Job).where(Job.id == job_id).values({counter.key: counter + 1, "updated_at": now}))


def _stop(db: Session, job_id: str, message: str) -> None:
    """Trabajo detenido ("failed"): los pendientes siguen pendientes; se puede reanudar."""
    with db.begin():
        job = db.get(Job, job_id, populate_existing=True)
        cancel = job.cancel_requested_at is not None
        if not cancel:
            job.status = "failed"
            job.error_message = message[:500]
            job.locked_by = None
            job.locked_until = None
            job.updated_at = utcnow()
            add_event(db, job, system_actor_id(db, WORKER), "job.stopped", {"reason": message[:500]})
            logger.warning("Trabajo %s detenido.", job_id)
    if cancel:
        _finish(db, job_id)  # Si además se pidió cancelar, se cancela en lugar de detenerse.


def _finish(db: Session, job_id: str) -> None:
    now = utcnow()
    with db.begin():
        job = db.get(Job, job_id, populate_existing=True)
        actor_id = system_actor_id(db, WORKER)
        if job.cancel_requested_at is not None:
            cancelled = db.execute(
                update(JobItem).where(JobItem.job_id == job_id, JobItem.status == "pending")
                .values(status="cancelled", finished_at=now, updated_at=now, updated_by=actor_id)
            ).rowcount
            job.cancelled_items += cancelled
        counts = dict(db.execute(
            select(JobItem.status, func.count()).where(JobItem.job_id == job_id).group_by(JobItem.status)
        ).all())
        if job.cancel_requested_at is not None:
            job.status = "cancelled"
        elif counts.get("failed", 0) or counts.get("uncertain", 0):
            job.status = "completed_with_errors"
        else:
            job.status = "completed"
        job.finished_at = now
        job.locked_by = None
        job.locked_until = None
        job.updated_at = now
        add_event(db, job, actor_id, "job.finished", {"status": job.status, **counts})
    logger.info("Trabajo %s terminó: %s.", job_id, job.status)
