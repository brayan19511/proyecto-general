"""Cambios de SKU de lastmiller con su historial.

Ofisis (los SKU) y la base propia (historial y cargas) son bases distintas: no
hay una transacción común. Orden en cada cambio:
1. Se abre la transacción propia y se agregan los eventos (flush: si fallan,
   no se toca Ofisis).
2. Se escribe en Ofisis en una transacción corta y se confirma.
3. Se confirma la transacción propia.
Si Ofisis falla, se revierten los eventos. El único hueco es que falle el
paso 3 después del 2 (la base propia cae justo en ese instante): el cambio
queda en Ofisis sin evento, y se registra en el log del proceso.

Las cargas masivas se aplican por lotes (LASTMILLER_WRITE_BATCH_SIZE), cada
uno con este mismo orden: un fallo deja aplicados los lotes anteriores (con su
historial) y la carga queda "failed" con el avance en applied_changes.
"""

import logging
from datetime import timedelta

from platform_audit import current_trace_id
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import CompanyContext
from app.core.config import settings
from app.external.ofisis import ofisis_write
from app.lastmiller import import_plan
from app.lastmiller import sku_repository as repo
from app.lastmiller.channels import Channel
from app.lastmiller.excel_reader import read_upload
from app.models.common.mixin_model import utcnow
from app.models.entities import Actor, SkuEvent, SkuImport
from app.services.actors import user_actor_id
from app.services.errors import ConflictError, InvalidDataError, NotFoundError, ServiceError

logger = logging.getLogger(__name__)

# Una carga "applying" sin avance en este tiempo se considera interrumpida
# (caída del proceso) y deja de bloquear el canal.
STALE_APPLYING = timedelta(minutes=15)


def channel_key(channel: Channel) -> str:
    return f"{channel.country.value}/{channel.provider.value}"


def _event(db: Session, ctx: CompanyContext, channel: Channel, actor_id: str, *, sku: str, action: str,
           before: dict, after: dict, import_id: str | None = None) -> None:
    db.add(
        SkuEvent(
            company_id=ctx.company_id,
            channel=channel_key(channel),
            sku=sku,
            action=action,
            before=before,
            after=after,
            import_id=import_id,
            trace_id=current_trace_id(),
            created_by=actor_id,
        )
    )


def _get_or_404(channel: Channel, sku: str) -> dict:
    current = repo.get_sku(channel, sku)
    if current is None:
        raise NotFoundError(f"El SKU {sku} no existe en {channel.name}.")
    return current


def _require_promotions(channel: Channel) -> None:
    if channel.promotions is None:
        raise InvalidDataError(f"{channel.name} no maneja promociones.")


# --- Cambios individuales (lastmiller.edit)


def create_sku(db: Session, ctx: CompanyContext, channel: Channel, sku: str, is_active: bool) -> dict:
    sku = sku.strip()
    if repo.get_sku(channel, sku) is not None:
        raise ConflictError(f"El SKU {sku} ya existe en {channel.name}.")
    with db.begin():
        actor_id = user_actor_id(db, ctx.user_id)
        _event(db, ctx, channel, actor_id, sku=sku, action="sku.created", before={}, after={"is_active": is_active})
        db.flush()
        with ofisis_write() as connection, connection.begin():
            repo.insert_skus(connection, channel, [(sku, is_active)])
    return _get_or_404(channel, sku)


def set_sku_active(db: Session, ctx: CompanyContext, channel: Channel, sku: str, is_active: bool) -> dict:
    current = _get_or_404(channel, sku)
    if current["is_active"] == is_active:
        return current  # Sin cambio: sin evento.
    with db.begin():
        actor_id = user_actor_id(db, ctx.user_id)
        _event(db, ctx, channel, actor_id, sku=current["sku"],
               action="sku.activated" if is_active else "sku.deactivated",
               before={"is_active": current["is_active"]}, after={"is_active": is_active})
        db.flush()
        with ofisis_write() as connection, connection.begin():
            if repo.set_active(connection, channel, [current["sku"]], is_active) == 0:
                raise NotFoundError(f"El SKU {sku} ya no existe en {channel.name}.")
    return _get_or_404(channel, sku)


def delete_sku(db: Session, ctx: CompanyContext, channel: Channel, sku: str) -> None:
    current = _get_or_404(channel, sku)
    if current["has_promotion"]:
        raise ConflictError(f"El SKU {current['sku']} tiene promoción: quítala antes de eliminarlo.")
    with db.begin():
        actor_id = user_actor_id(db, ctx.user_id)
        _event(db, ctx, channel, actor_id, sku=current["sku"], action="sku.deleted",
               before={"is_active": current["is_active"]}, after={})
        db.flush()
        with ofisis_write() as connection, connection.begin():
            if repo.delete_sku(connection, channel, current["sku"]) == 0:
                raise NotFoundError(f"El SKU {sku} ya no existe en {channel.name}.")


def set_promotion(db: Session, ctx: CompanyContext, channel: Channel, sku: str, enabled: bool) -> dict:
    _require_promotions(channel)
    current = _get_or_404(channel, sku)
    if current["has_promotion"] == enabled:
        return current
    with db.begin():
        actor_id = user_actor_id(db, ctx.user_id)
        _event(db, ctx, channel, actor_id, sku=current["sku"],
               action="promotion.added" if enabled else "promotion.removed",
               before={"promotion": not enabled}, after={"promotion": enabled})
        db.flush()
        with ofisis_write() as connection, connection.begin():
            if enabled:
                repo.add_promotions(connection, channel, [current["sku"]])
            else:
                repo.remove_promotions(connection, channel, [current["sku"]])
    return _get_or_404(channel, sku)


# --- Cargas masivas (lastmiller.import)

# Qué columna on/off exige cada tipo de carga (ver excel_reader.read_upload).
ACTIVE_COLUMN = {"sku_full": "optional", "sku_partial": "required", "promotions": "none"}


def _compute_plan(channel: Channel, kind: str, rows: list[dict], create_missing: bool) -> dict:
    current = repo.current_states(channel)
    if kind == "promotions":
        return import_plan.plan_promotions(rows, current, repo.promotion_skus(channel))
    return import_plan.plan_skus(kind, rows, current, create_missing)


def preview_import(db: Session, ctx: CompanyContext, channel: Channel, *, kind: str, create_missing: bool,
                   content: bytes, filename: str | None) -> SkuImport:
    """Lee el archivo, calcula qué cambiaría y lo guarda. No toca Ofisis."""
    if kind == "promotions":
        _require_promotions(channel)
        create_missing = False
    parsed = read_upload(content, filename, active_column=ACTIVE_COLUMN[kind])
    plan = {} if parsed.errors else _compute_plan(channel, kind, parsed.rows, create_missing)
    with db.begin():
        actor_id = user_actor_id(db, ctx.user_id)
        record = SkuImport(
            company_id=ctx.company_id,
            channel=channel_key(channel),
            kind=kind,
            create_missing=create_missing,
            filename=parsed.filename,
            file_sha256=parsed.sha256,
            rows=parsed.rows,
            errors=parsed.errors,
            plan=plan,
            plan_hash=import_plan.plan_hash(plan),
            status="invalid" if parsed.errors else "previewed",
            total_changes=len(import_plan.steps(plan)),
            applied_changes=0,
            trace_id=current_trace_id(),
            created_by=actor_id,
        )
        db.add(record)
    return record


def get_import(db: Session, ctx: CompanyContext, channel: Channel, import_id: str) -> SkuImport:
    with db.begin():
        record = db.get(SkuImport, import_id)
    if record is None or record.company_id != ctx.company_id or record.channel != channel_key(channel):
        raise NotFoundError("Carga no encontrada.")
    return record


def cancel_import(db: Session, ctx: CompanyContext, channel: Channel, import_id: str) -> SkuImport:
    """Descarta una vista previa sin aplicarla (no toca Ofisis). Solo "previewed" o
    "invalid": una carga en curso o terminada no se cancela."""
    record = get_import(db, ctx, channel, import_id)
    now = utcnow()
    with db.begin():
        actor_id = user_actor_id(db, ctx.user_id)
        # Condicional: si alguien la está aplicando en este momento, no se cancela.
        changed = db.execute(
            update(SkuImport)
            .where(SkuImport.id == record.id, SkuImport.status.in_(("previewed", "invalid")))
            .values(status="cancelled", updated_at=now, updated_by=actor_id)
        ).rowcount
        if not changed:
            raise ConflictError("Esta carga ya no se puede descartar (está en curso o terminó).")
    return get_import(db, ctx, channel, import_id)


def apply_import(db: Session, ctx: CompanyContext, channel: Channel, import_id: str) -> SkuImport:
    record = get_import(db, ctx, channel, import_id)
    if record.status != "previewed":
        raise ConflictError("Esta carga no se puede aplicar (ya se aplicó, falló o el archivo tiene errores).")
    if record.plan.get("blocking"):
        raise ConflictError("La carga tiene SKU que no existen en el canal: corrige el archivo y vuelve a previsualizar.")
    if record.total_changes == 0:
        raise ConflictError("La carga no cambia nada.")

    # El estado de Ofisis pudo cambiar desde la vista previa: se recalcula y se
    # exige que el plan sea idéntico al que vio el usuario.
    plan = _compute_plan(channel, record.kind, record.rows, record.create_missing)
    if import_plan.plan_hash(plan) != record.plan_hash:
        raise ConflictError("Los datos del canal cambiaron desde la vista previa. Vuelve a previsualizar el archivo.")

    now = utcnow()
    with db.begin():
        # Libera cargas que quedaron "applying" sin avance (caída del proceso).
        db.execute(
            update(SkuImport)
            .where(SkuImport.channel == record.channel, SkuImport.status == "applying",
                   SkuImport.updated_at < now - STALE_APPLYING)
            .values(status="interrupted", error_message="Interrumpida: quedó en curso sin avance.", updated_at=now)
        )
    try:
        with db.begin():
            actor_id = user_actor_id(db, ctx.user_id)
            # Solo desde "previewed": dos solicitudes simultáneas sobre la misma carga no la aplican dos veces.
            claimed = db.execute(
                update(SkuImport)
                .where(SkuImport.id == record.id, SkuImport.status == "previewed")
                .values(status="applying", applied_by=actor_id, updated_by=actor_id, updated_at=now)
            ).rowcount
            if claimed == 0:
                raise ConflictError("Esta carga ya se está aplicando o ya se aplicó.")
    except IntegrityError as exc:
        # Índice único: ya hay otra carga en curso en este canal.
        raise ConflictError(f"Hay otra carga en curso en {channel.name}. Espera a que termine.") from exc

    try:
        _apply_steps(db, ctx, channel, record.id, actor_id, import_plan.steps(plan))
    except Exception as exc:
        message = str(exc) if isinstance(exc, ServiceError) else "Error inesperado al aplicar la carga."
        if not isinstance(exc, ServiceError):
            logger.exception("Carga %s falló", record.id)
        with db.begin():
            db.execute(
                update(SkuImport).where(SkuImport.id == record.id)
                .values(status="failed", error_message=message[:500], updated_at=utcnow())
            )
        raise

    with db.begin():
        finished = utcnow()
        db.execute(
            update(SkuImport).where(SkuImport.id == record.id)
            .values(status="applied", applied_at=finished, updated_at=finished)
        )
    return get_import(db, ctx, channel, record.id)


EVENTS = {
    "create": ("sku.created", lambda active: ({}, {"is_active": active})),
    "activate": ("sku.activated", lambda _: ({"is_active": False}, {"is_active": True})),
    "deactivate": ("sku.deactivated", lambda _: ({"is_active": True}, {"is_active": False})),
    "promotion_add": ("promotion.added", lambda _: ({"promotion": False}, {"promotion": True})),
    "promotion_remove": ("promotion.removed", lambda _: ({"promotion": True}, {"promotion": False})),
}


def _apply_steps(db: Session, ctx: CompanyContext, channel: Channel, import_id: str, actor_id: str,
                 all_steps: list[tuple[str, str, bool | None]]) -> None:
    size = settings.LASTMILLER_WRITE_BATCH_SIZE
    # Una conexión para toda la carga (se cierra al terminar); una transacción por lote.
    with ofisis_write() as connection:
        for start in range(0, len(all_steps), size):
            lot = all_steps[start:start + size]
            with db.begin():
                for action, sku, active in lot:
                    name, values = EVENTS[action]
                    before, after = values(active)
                    _event(db, ctx, channel, actor_id, sku=sku, action=name, before=before, after=after,
                           import_id=import_id)
                # Avance y "latido": una carga con updated_at reciente sigue viva.
                db.execute(
                    update(SkuImport).where(SkuImport.id == import_id)
                    .values(applied_changes=start + len(lot), updated_at=utcnow())
                )
                db.flush()
                with connection.begin():
                    _write_lot(connection, channel, lot)


def _write_lot(connection, channel: Channel, lot: list[tuple[str, str, bool | None]]) -> None:
    by_action: dict[str, list] = {}
    for action, sku, active in lot:
        by_action.setdefault(action, []).append((sku, active))
    repo.insert_skus(connection, channel, by_action.get("create", []))
    repo.set_active(connection, channel, [sku for sku, _ in by_action.get("activate", [])], True)
    repo.set_active(connection, channel, [sku for sku, _ in by_action.get("deactivate", [])], False)
    repo.remove_promotions(connection, channel, [sku for sku, _ in by_action.get("promotion_remove", [])])
    repo.add_promotions(connection, channel, [sku for sku, _ in by_action.get("promotion_add", [])])


# --- Consultas (lastmiller.view)


def list_imports(db: Session, ctx: CompanyContext, channel: Channel, limit: int, offset: int) -> tuple[list[SkuImport], int]:
    conditions = (SkuImport.company_id == ctx.company_id, SkuImport.channel == channel_key(channel))
    with db.begin():
        total = db.scalar(select(func.count()).select_from(SkuImport).where(*conditions))
        items = db.scalars(
            select(SkuImport).where(*conditions).order_by(SkuImport.created_at.desc()).limit(limit).offset(offset)
        ).all()
    return list(items), total


def list_events(db: Session, ctx: CompanyContext, channel: Channel, *, sku: str | None, import_id: str | None,
                limit: int, offset: int) -> tuple[list[dict], int]:
    conditions = [SkuEvent.company_id == ctx.company_id, SkuEvent.channel == channel_key(channel)]
    if sku:
        conditions.append(func.lower(SkuEvent.sku) == sku.strip().lower())
    if import_id:
        conditions.append(SkuEvent.import_id == import_id)
    with db.begin():
        total = db.scalar(select(func.count()).select_from(SkuEvent).where(*conditions))
        rows = db.execute(
            select(SkuEvent, Actor.subject_ref)
            .join(Actor, Actor.id == SkuEvent.created_by)
            .where(*conditions)
            .order_by(SkuEvent.created_at.desc(), SkuEvent.id.desc())
            .limit(limit)
            .offset(offset)
        ).all()
    items = [
        {
            "id": event.id,
            "sku": event.sku,
            "action": event.action,
            "before": event.before,
            "after": event.after,
            "import_id": event.import_id,
            "user_id": user_id,
            "created_at": event.created_at,
        }
        for event, user_id in rows
    ]
    return items, total
