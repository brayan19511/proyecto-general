from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    MetaData,
    String,
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.models.common.mixin_model import AuditMixin


class Base(DeclarativeBase):
    """Base compartida por todos los modelos del servicio."""

    # Todas las tablas que hereden de Base se ubican en auth.
    # Las referencias locales como "users.id" también se resuelven en auth.
    metadata = MetaData(schema="auth")


class User(AuditMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(254))
    normalized_email: Mapped[str] = mapped_column(
        String(254),
        unique=True,
    )
    password_hash: Mapped[str] = mapped_column(String(512))

    # NULL significa utilizar el máximo predeterminado del servicio.
    max_sessions: Mapped[int | None] = mapped_column(Integer)

    __table_args__ = (
        CheckConstraint(
            "max_sessions IS NULL OR max_sessions > 0",
        ),
    )


class Profile(AuditMixin, Base):
    __tablename__ = "user_profiles"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id"),
        unique=True,
    )
    first_names: Mapped[str | None] = mapped_column(String(100))
    last_names: Mapped[str | None] = mapped_column(String(100))


class Company(AuditMixin, Base):
    __tablename__ = "companies"

    code: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(150))


class Membership(AuditMixin, Base):
    __tablename__ = "memberships"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"))

    __table_args__ = (
        UniqueConstraint("user_id", "company_id"),
        UniqueConstraint("id", "company_id"),
    )


class Area(AuditMixin, Base):
    __tablename__ = "areas"

    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"))
    code: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(150))

    __table_args__ = (
        UniqueConstraint("company_id", "code"),
        UniqueConstraint("id", "company_id"),
    )


class Position(AuditMixin, Base):
    __tablename__ = "positions"

    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"))
    area_id: Mapped[str] = mapped_column(String(36))
    code: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(150))

    # La FK compuesta impide asignar un área de otra empresa.
    __table_args__ = (
        UniqueConstraint("company_id", "code"),
        UniqueConstraint("id", "company_id"),
        ForeignKeyConstraint(
            ["area_id", "company_id"],
            ["areas.id", "areas.company_id"],
        ),
    )


class Assignment(AuditMixin, Base):
    __tablename__ = "position_assignments"

    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"))
    membership_id: Mapped[str] = mapped_column(String(36))
    position_id: Mapped[str] = mapped_column(String(36))

    # Membresía y puesto deben pertenecer a la misma empresa.
    __table_args__ = (
        UniqueConstraint("membership_id", "position_id"),
        ForeignKeyConstraint(
            ["membership_id", "company_id"],
            ["memberships.id", "memberships.company_id"],
        ),
        ForeignKeyConstraint(
            ["position_id", "company_id"],
            ["positions.id", "positions.company_id"],
        ),
    )


class Role(AuditMixin, Base):
    __tablename__ = "roles"

    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"))
    code: Mapped[str] = mapped_column(String(50))

    __table_args__ = (
        UniqueConstraint("company_id", "code"),
        UniqueConstraint("id", "company_id"),
    )


class Permission(AuditMixin, Base):
    __tablename__ = "permissions"

    code: Mapped[str] = mapped_column(String(100), unique=True)


class PositionRole(AuditMixin, Base):
    __tablename__ = "position_roles"

    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"))
    position_id: Mapped[str] = mapped_column(String(36))
    role_id: Mapped[str] = mapped_column(String(36))

    __table_args__ = (
        UniqueConstraint("position_id", "role_id"),
        ForeignKeyConstraint(
            ["position_id", "company_id"],
            ["positions.id", "positions.company_id"],
        ),
        ForeignKeyConstraint(
            ["role_id", "company_id"],
            ["roles.id", "roles.company_id"],
        ),
    )


class RolePermission(AuditMixin, Base):
    __tablename__ = "role_permissions"

    role_id: Mapped[str] = mapped_column(ForeignKey("roles.id"))
    permission_id: Mapped[str] = mapped_column(ForeignKey("permissions.id"))
    scope: Mapped[str] = mapped_column(String(16), default="company")

    __table_args__ = (
        UniqueConstraint("role_id", "permission_id", "scope"),
        CheckConstraint("scope IN ('own', 'area', 'company')"),
    )


class AuthSession(AuditMixin, Base):
    """Una sesión iniciada por un usuario."""

    __tablename__ = "sessions"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id"),
        index=True,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )

    csrf_hash: Mapped[str] = mapped_column(String(64))
    initial_ip: Mapped[str] = mapped_column(String(64))
    last_ip: Mapped[str] = mapped_column(String(64))
    client_description: Mapped[str] = mapped_column(String(256))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RefreshToken(AuditMixin, Base):
    """Credencial de renovación; se conserva el hash, nunca el secreto."""

    __tablename__ = "refresh_tokens"

    session_id: Mapped[str] = mapped_column(
        ForeignKey("sessions.id"),
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )


class RateBucket(AuditMixin, Base):
    """Contador de solicitudes o intentos para una política concreta."""

    __tablename__ = "rate_buckets"

    key: Mapped[str] = mapped_column(String(100), unique=True)
    count: Mapped[int] = mapped_column(Integer, default=0)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    blocked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )


class ChangeHistory(AuditMixin, Base):
    """Historial de negocio; el responsable se guarda en created_by."""

    __tablename__ = "change_history"

    action: Mapped[str] = mapped_column(String(100))
    resource_id: Mapped[str] = mapped_column(String(36))
    company_id: Mapped[str | None] = mapped_column(
        ForeignKey("companies.id"),
    )
    trace_id: Mapped[str | None] = mapped_column(String(36))

    # Solo campos permitidos; nunca contraseñas, hashes ni tokens.
    before: Mapped[dict] = mapped_column(JSON, default=dict)
    after: Mapped[dict] = mapped_column(JSON, default=dict)


class Log(AuditMixin, Base):
    """Cabecera técnica de una operación."""

    __tablename__ = "logs"

    trace_id: Mapped[str] = mapped_column(String(36), index=True)
    parent_operation_id: Mapped[str | None] = mapped_column(String(36))

    service: Mapped[str] = mapped_column(String(50))
    version: Mapped[str] = mapped_column(String(30))
    action: Mapped[str] = mapped_column(String(150))
    status: Mapped[str] = mapped_column(String(20), default="started")

    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )
    duration_ms: Mapped[float | None] = mapped_column(Float)
    http_status: Mapped[int | None] = mapped_column(Integer)

    # Usuario autenticado asociado a la operación.
    # Puede conocerse después de crear la cabecera, o permanecer desconocido.
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    company_id: Mapped[str | None] = mapped_column(
        ForeignKey("companies.id"),
    )


class LogDetail(AuditMixin, Base):
    """Información técnica permitida de una operación."""

    __tablename__ = "logs_detail"

    log_id: Mapped[str] = mapped_column(ForeignKey("logs.id"), index=True)
    data: Mapped[dict] = mapped_column(JSON)


class LogStep(AuditMixin, Base):
    """Evento de inicio, finalización o fallo de un paso."""

    __tablename__ = "logs_steps"

    log_id: Mapped[str] = mapped_column(ForeignKey("logs.id"), index=True)
    step_id: Mapped[str] = mapped_column(String(36))
    name: Mapped[str] = mapped_column(String(100))
    phase: Mapped[str] = mapped_column(String(16))
    duration_ms: Mapped[float | None] = mapped_column(Float)


def reject_change(*_):
    """Impide modificar o eliminar estos objetos durante el flush del ORM."""
    raise ValueError("Los eventos históricos son de solo anexado")


# Permite insertar eventos nuevos, pero no modificar los existentes
# mediante el ciclo habitual del ORM. No protege contra SQL directo.
for immutable in (ChangeHistory, LogDetail, LogStep):
    event.listen(immutable, "before_update", reject_change)
    event.listen(immutable, "before_delete", reject_change)
