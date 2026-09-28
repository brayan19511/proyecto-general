from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, MetaData, String, event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.models.common.mixin_model import AuditMixin


class Base(DeclarativeBase):
    """Base de los modelos de la central. Todas sus tablas van en el schema gateway."""

    metadata = MetaData(schema="gateway")


class ServiceState(AuditMixin, Base):
    """Estado de un servicio decidido desde la administración (panel).

    Sin fila = vale la configuración (<SERVICIO>_ENABLED). La configuración
    manda: con false, esta fila no lo habilita. is_enabled no es is_active:
    deshabilitar un servicio no es dar de baja la fila.
    """

    __tablename__ = "service_states"

    service: Mapped[str] = mapped_column(String(50), unique=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean)
    reason: Mapped[str | None] = mapped_column(String(300))


class IpBlock(AuditMixin, Base):
    """IP o rango bloqueado en la central (todas las rutas salvo /health y /ready).

    Desbloquear = baja lógica (is_active=false, deleted_at/by), con historial.
    Vencido (expires_at en el pasado) deja de aplicarse sin cambiar la fila.
    """

    __tablename__ = "ip_blocks"

    # Normalizado con ipaddress: "10.0.0.5/32", "172.30.0.0/24", "2001:db8::/32".
    network: Mapped[str] = mapped_column(String(50), index=True)
    reason: Mapped[str | None] = mapped_column(String(300))
    # NULL = sin vencimiento.
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ChangeHistory(AuditMixin, Base):
    """Historial de negocio de la central, de solo anexado. El responsable va en created_by."""

    __tablename__ = "change_history"

    action: Mapped[str] = mapped_column(String(100))
    resource_type: Mapped[str] = mapped_column(String(50))  # "service_state", "ip_block"
    resource_id: Mapped[str] = mapped_column(String(36))
    trace_id: Mapped[str | None] = mapped_column(String(36))
    # Solo campos permitidos; nunca secretos ni tokens.
    before: Mapped[dict] = mapped_column(JSON, default=dict)
    after: Mapped[dict] = mapped_column(JSON, default=dict)


def reject_change(*_):
    """Impide modificar o eliminar estos objetos durante el flush del ORM."""
    raise ValueError("Los eventos históricos son de solo anexado")


# Permite insertar eventos nuevos, pero no modificarlos ni eliminarlos mediante
# el ORM. No protege contra SQL directo.
event.listen(ChangeHistory, "before_update", reject_change)
event.listen(ChangeHistory, "before_delete", reject_change)
