"""Estado de los servicios publicados por la central (habilitar / deshabilitar).

Solo para el administrador de plataforma. Un cambio se guarda junto con su
evento de historial en una misma transacción y aplica de inmediato en esta
réplica; en las demás, en ≤ GATEWAY_STATE_TTL_SECONDS. Ver app/core/services.py.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from platform_audit import current_trace_id
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import AdminUser, require_platform_admin
from app.core import services
from app.core.db.connection import get_db
from app.models.common.mixin_model import utcnow
from app.models.entities import ChangeHistory, ServiceState
from app.schemas.page import Page
from app.schemas.services import HistoryEventOut, ServiceStateOut, ServiceStateUpdate

router = APIRouter(
    prefix="/gateway/admin",
    tags=["admin"],
    dependencies=[Depends(require_platform_admin)],
)


def _state_out(info: services.ServiceInfo, row: ServiceState | None) -> ServiceStateOut:
    return ServiceStateOut(
        service=info.name,
        enabled=services.is_enabled(info.name),
        enabled_by_config=info.enabled_by_config,
        panel_managed=info.panel_managed,
        db_enabled=row.is_enabled if row else None,
        reason=row.reason if row else None,
        updated_at=row.updated_at if row else None,
        updated_by=row.updated_by if row else None,
    )


@router.get("/services", response_model=list[ServiceStateOut], operation_id="gatewayListServices")
def list_services(db: Session = Depends(get_db)):
    with db.begin():
        rows = {
            row.service: row
            for row in db.scalars(select(ServiceState).where(ServiceState.is_active.is_(True)))
        }
        return [_state_out(info, rows.get(name)) for name, info in services.SERVICES.items()]


@router.patch("/services/{service}", response_model=ServiceStateOut, operation_id="gatewayUpdateService")
def update_service(
    service: str,
    body: ServiceStateUpdate,
    admin: AdminUser = Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    info = services.SERVICES.get(service)
    if info is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Servicio no encontrado.")
    if not info.panel_managed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"El servicio {service} solo se habilita o deshabilita por configuración.",
        )

    try:
        with db.begin():
            # with_for_update: dos administradores a la vez no pisan el historial.
            row = db.scalar(
                select(ServiceState)
                .where(ServiceState.service == service, ServiceState.is_active.is_(True))
                .with_for_update()
            )
            before = {"is_enabled": row.is_enabled, "reason": row.reason} if row else {}
            now = utcnow()
            if row is None:
                row = ServiceState(
                    service=service, created_at=now, created_by=admin.id, updated_at=now, updated_by=admin.id,
                    is_enabled=body.is_enabled, reason=body.reason,
                )
                db.add(row)
                db.flush()  # Asigna el id para el historial.
            else:
                row.is_enabled = body.is_enabled
                row.reason = body.reason
                row.updated_at = now
                row.updated_by = admin.id
            db.add(
                ChangeHistory(
                    action="service_state.enable" if body.is_enabled else "service_state.disable",
                    resource_type="service_state",
                    resource_id=row.id,
                    trace_id=current_trace_id(),
                    before=before,
                    after={"is_enabled": body.is_enabled, "reason": body.reason},
                    created_at=now, created_by=admin.id, updated_at=now, updated_by=admin.id,
                )
            )
    except IntegrityError:
        # Otro administrador creó la fila al mismo tiempo (service es único).
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cambio simultáneo; vuelve a intentarlo.")

    services.load_states()  # Esta réplica aplica el cambio ya; las demás en ≤ TTL.
    return _state_out(info, row)


@router.get("/history", response_model=list[HistoryEventOut], operation_id="gatewayListHistory")
def list_history(
    resource_type: str | None = None,
    resource_id: str | None = None,
    page: Page = Depends(),
    db: Session = Depends(get_db),
):
    """Historial de cambios de la central (más recientes primero)."""
    with db.begin():
        statement = select(ChangeHistory)
        if resource_type:
            statement = statement.where(ChangeHistory.resource_type == resource_type)
        if resource_id:
            statement = statement.where(ChangeHistory.resource_id == resource_id)
        statement = statement.order_by(ChangeHistory.created_at.desc()).limit(page.limit).offset(page.offset)
        return list(db.scalars(statement))
