from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    MetaData,
    String,
    UniqueConstraint,
    event,
    false,
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

    email: Mapped[str] = mapped_column(
        String(254),
        unique=True,
    )
    password_hash: Mapped[str] = mapped_column(String(512))

    # NULL significa utilizar el máximo predeterminado del servicio.
    max_sessions: Mapped[int | None] = mapped_column(Integer)

    # Master admin: acceso a todas las empresas sin puestos ni roles.
    # Excepción documentada a la herencia por puestos. Solo el seed lo activa;
    # ningún schema de la API lo acepta. Igual requiere login y sesión válida.
    is_platform_admin: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=false(),  # Las filas existentes quedan en false.
    )

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
    birth_date: Mapped[date | None] = mapped_column(Date)
    # País de nacionalidad (código ISO de 2 letras del catálogo countries).
    # Distinto del país emisor de un documento y del país de residencia.
    nationality_country_code: Mapped[str | None] = mapped_column(
        ForeignKey("countries.code"),
    )


class Country(AuditMixin, Base):
    """Catálogo de países (ISO 3166-1 alfa-2). Lo carga el seed."""

    __tablename__ = "countries"

    code: Mapped[str] = mapped_column(String(2), unique=True)
    name: Mapped[str] = mapped_column(String(100))


class IdentityDocumentType(AuditMixin, Base):
    """Tipo de documento por país emisor: PE/DNI, CL/RUT, ES/DNI, PE/PASAPORTE...

    El mismo código en países distintos son tipos distintos. La validación es
    un patrón de datos (no código ejecutable) aplicado al número normalizado.
    """

    __tablename__ = "identity_document_types"

    issuing_country_code: Mapped[str] = mapped_column(ForeignKey("countries.code"))
    code: Mapped[str] = mapped_column(String(30))
    name: Mapped[str] = mapped_column(String(100))
    # national_identity, residence, passport u other.
    category: Mapped[str] = mapped_column(String(30))
    # Expresión regular opcional sobre el número normalizado.
    pattern: Mapped[str | None] = mapped_column(String(200))

    __table_args__ = (
        UniqueConstraint("issuing_country_code", "code"),
        CheckConstraint(
            "category IN ('national_identity', 'residence', 'passport', 'other')",
        ),
    )


class UserIdentityDocument(AuditMixin, Base):
    """Documento de identidad declarado por el usuario. Formato válido no
    significa identidad verificada."""

    __tablename__ = "user_identity_documents"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    document_type_id: Mapped[str] = mapped_column(
        ForeignKey("identity_document_types.id"),
    )
    # Tal como lo escribió el usuario, y normalizado (sin espacios, puntos ni
    # guiones, en mayúsculas). Texto: conserva ceros iniciales.
    document_number: Mapped[str] = mapped_column(String(50))
    normalized_number: Mapped[str] = mapped_column(String(50))
    expires_at: Mapped[date | None] = mapped_column(Date)

    # Un documento por tipo y usuario (unicidad permanente: volver a
    # registrarlo restaura la fila). No hay unicidad global entre personas.
    __table_args__ = (UniqueConstraint("user_id", "document_type_id"),)


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
    # Nombre visible; el código es el identificador estable.
    name: Mapped[str] = mapped_column(String(150))

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


class ApiKey(AuditMixin, Base):
    """Credencial de larga duración de un usuario para una empresa.

    Se guarda el hash del secreto, nunca el secreto. Sus scopes se intersectan
    con los permisos actuales de la membresía en cada uso: nunca da más.
    expires_at NULL = sin vencimiento (sigue siendo revocable).
    """

    __tablename__ = "api_keys"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"))
    membership_id: Mapped[str] = mapped_column(String(36))
    name: Mapped[str] = mapped_column(String(100))
    # Para qué se usa la key (texto libre, opcional). No concede nada:
    # los permisos están en scopes.
    description: Mapped[str | None] = mapped_column(String(500))
    # Parte visible del token para reconocerlo en listados ("ak_Xy12ab34").
    prefix: Mapped[str] = mapped_column(String(20))
    key_hash: Mapped[str] = mapped_column(String(64), unique=True)
    scopes: Mapped[list] = mapped_column(JSON)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # La membresía debe ser de la misma empresa.
    __table_args__ = (
        ForeignKeyConstraint(
            ["membership_id", "company_id"],
            ["memberships.id", "memberships.company_id"],
        ),
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


# Los logs técnicos (logs, logs_detail, logs_steps) ya no son de auth: viven en el
# schema audit del paquete compartido platform_audit (packages/platform-audit).


def reject_change(*_):
    """Impide modificar o eliminar estos objetos durante el flush del ORM."""
    raise ValueError("Los eventos históricos son de solo anexado")


# Permite insertar eventos nuevos, pero no modificar los existentes
# mediante el ciclo habitual del ORM. No protege contra SQL directo.
for immutable in (ChangeHistory,):
    event.listen(immutable, "before_update", reject_change)
    event.listen(immutable, "before_delete", reject_change)
