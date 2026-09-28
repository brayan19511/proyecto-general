"""Tablas del schema `audit`: el contrato común de logs de la plataforma.

Las define este paquete, no un servicio: cualquier servicio que lo use escribe
aquí sus propias filas (columna `service`) y nunca modifica las de otro.

No llevan created_by/updated_by ni FK a usuarios: son telemetría técnica, con
ciclo de vida propio, y deben servir a servicios que no comparten base con
auth. user_id y company_id son referencias en texto, validadas por quien las
registra.

Cambios futuros: solo compatibles (columnas nuevas opcionales), porque varios
servicios con versiones distintas del paquete pueden escribir a la vez.
"""

from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, MetaData, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

SCHEMA = "audit"


class Base(DeclarativeBase):
    metadata = MetaData(schema=SCHEMA)


class Log(Base):
    """Cabecera: una operación (solicitud HTTP o proceso) de un servicio."""

    __tablename__ = "logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)  # operation_id
    trace_id: Mapped[str] = mapped_column(String(36), index=True)
    parent_operation_id: Mapped[str | None] = mapped_column(String(36))
    service: Mapped[str] = mapped_column(String(50))
    service_version: Mapped[str] = mapped_column(String(30))
    method: Mapped[str] = mapped_column(String(10))
    path: Mapped[str] = mapped_column(String(300))
    status_code: Mapped[int | None] = mapped_column(Integer)
    # success (<400), warning (4xx), error (5xx o excepción). NULL: aún en curso
    # o el proceso cayó antes de cerrarla (no prueba que siga ejecutándose).
    outcome: Mapped[str | None] = mapped_column(String(10))
    ip_address: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(256))
    user_id: Mapped[str | None] = mapped_column(String(36), index=True)
    company_id: Mapped[str | None] = mapped_column(String(36))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[float | None] = mapped_column(Float)  # Reloj monotónico.

    __table_args__ = (
        Index("ix_audit_logs_service_started_at", "service", "started_at"),
        CheckConstraint("outcome IS NULL OR outcome IN ('success', 'warning', 'error')"),
    )


class LogDetail(Base):
    """Detalle de una operación: request, response, error o mensaje manual.
    Solo anexado."""

    __tablename__ = "logs_detail"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    log_id: Mapped[str] = mapped_column(ForeignKey("logs.id"), index=True)
    level: Mapped[str] = mapped_column(String(10))  # info, success, warning, error
    kind: Mapped[str] = mapped_column(String(20))  # request, response, error, message
    message: Mapped[str | None] = mapped_column(String(1000))
    # Parámetros, headers permitidos y body ya enmascarados y truncados.
    data: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("level IN ('info', 'success', 'warning', 'error')"),
    )


class LogStep(Base):
    """Paso manual dentro de una operación. Inicio y fin son filas distintas con
    el mismo step_id: un inicio sin fin solo indica que no se registró el cierre."""

    __tablename__ = "logs_steps"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    log_id: Mapped[str] = mapped_column(ForeignKey("logs.id"), index=True)
    step_id: Mapped[str] = mapped_column(String(36))
    name: Mapped[str] = mapped_column(String(150))
    phase: Mapped[str] = mapped_column(String(10))  # start, end, error
    message: Mapped[str | None] = mapped_column(String(1000))
    duration_ms: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("phase IN ('start', 'end', 'error')"),
    )
