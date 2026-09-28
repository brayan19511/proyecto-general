"""Lista negra de IPs de la central (gateway.ip_blocks).

Solo para el administrador de plataforma. Cada alta y cada baja se guardan con
su evento de historial en una misma transacción. Aplican de inmediato en esta
réplica y en ≤ GATEWAY_STATE_TTL_SECONDS en las demás.

Protección: no se puede bloquear un rango que contenga la IP de quien lo pide
(se quedaría fuera, incluida la administración). Recuperación si aun así se
bloquea a quien no debía: IP_BLOCKS_ENABLED=false y reiniciar la central.
"""

from ipaddress import ip_address, ip_network

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from platform_audit import current_trace_id
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.dependencies import AdminUser, require_platform_admin
from app.core import ip_blocks
from app.core.client_ip import client_ip
from app.core.db.connection import get_db
from app.models.common.mixin_model import utcnow
from app.models.entities import ChangeHistory, IpBlock
from app.schemas.page import Page
from app.schemas.services import IpBlockCreate, IpBlockOut

router = APIRouter(
    prefix="/gateway/admin/ip-blocks",
    tags=["admin"],
    dependencies=[Depends(require_platform_admin)],
)


def _snapshot(block: IpBlock) -> dict:
    return {
        "network": block.network,
        "reason": block.reason,
        "expires_at": block.expires_at.isoformat() if block.expires_at else None,
    }


def _history(action: str, block: IpBlock, before: dict, after: dict, admin: AdminUser, now) -> ChangeHistory:
    return ChangeHistory(
        action=action, resource_type="ip_block", resource_id=block.id, trace_id=current_trace_id(),
        before=before, after=after,
        created_at=now, created_by=admin.id, updated_at=now, updated_by=admin.id,
    )


@router.get("", response_model=list[IpBlockOut], operation_id="gatewayListIpBlocks")
def list_ip_blocks(
    include_inactive: bool = False,
    page: Page = Depends(),
    db: Session = Depends(get_db),
):
    """Bloqueos, más recientes primero. Por defecto solo los activos (incluye vencidos)."""
    with db.begin():
        statement = select(IpBlock)
        if not include_inactive:
            statement = statement.where(IpBlock.is_active.is_(True))
        statement = statement.order_by(IpBlock.created_at.desc()).limit(page.limit).offset(page.offset)
        return list(db.scalars(statement))


@router.post("", response_model=IpBlockOut, status_code=status.HTTP_201_CREATED, operation_id="gatewayCreateIpBlock")
def create_ip_block(
    body: IpBlockCreate,
    request: Request,
    admin: AdminUser = Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    try:
        network = ip_network(body.network.strip(), strict=False)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="IP o rango CIDR inválido.")
    now = utcnow()
    if body.expires_at is not None and (body.expires_at.tzinfo is None or body.expires_at <= now):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="expires_at debe ser una fecha futura con zona horaria.",
        )

    own_ip = client_ip(request.client.host if request.client else None, request.headers.get("x-forwarded-for", ""))
    try:
        own = ip_address(own_ip) if own_ip else None
    except ValueError:
        own = None
    if own is not None and own in network:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="El rango incluye tu propia IP.")

    with db.begin():
        duplicate = db.scalar(
            select(IpBlock.id).where(
                IpBlock.network == str(network),
                IpBlock.is_active.is_(True),
                or_(IpBlock.expires_at.is_(None), IpBlock.expires_at > now),
            )
        )
        if duplicate is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ese rango ya está bloqueado.")
        block = IpBlock(
            network=str(network), reason=body.reason, expires_at=body.expires_at,
            created_at=now, created_by=admin.id, updated_at=now, updated_by=admin.id,
        )
        db.add(block)
        db.flush()  # Asigna el id para el historial.
        db.add(_history("ip_block.create", block, {}, _snapshot(block), admin, now))

    ip_blocks.load_blocks()  # Esta réplica aplica el bloqueo ya; las demás en ≤ TTL.
    return block


@router.delete("/{block_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response, operation_id="gatewayDeleteIpBlock")
def delete_ip_block(
    block_id: str,
    admin: AdminUser = Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    """Desbloquea: baja lógica (la fila y su historial se conservan)."""
    with db.begin():
        block = db.scalar(
            select(IpBlock).where(IpBlock.id == block_id, IpBlock.is_active.is_(True)).with_for_update()
        )
        if block is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bloqueo no encontrado.")
        now = utcnow()
        block.is_active = False
        block.deleted_at = now
        block.deleted_by = admin.id
        block.updated_at = now
        block.updated_by = admin.id
        db.add(_history("ip_block.delete", block, _snapshot(block), {}, admin, now))

    ip_blocks.load_blocks()
