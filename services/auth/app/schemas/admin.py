"""Respuestas de las vistas generales del master admin (/admin).

Igual que las respuestas por empresa, pero cada elemento indica su empresa,
porque los listados abarcan todas.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.common import Code, Name, Ref
from app.schemas.identity import DocumentOut
from app.schemas.me import MembershipOut, ProfileOut
from app.schemas.position import PositionOut
from app.schemas.role import RoleOut


class AdminCompanyOut(BaseModel):
    id: str
    code: str
    name: str
    is_active: bool
    created_at: datetime


class AdminAreaOut(BaseModel):
    id: str
    code: str
    name: str
    is_active: bool
    company: Ref


class AdminPositionOut(PositionOut):
    company: Ref


class AdminRoleOut(RoleOut):
    company: Ref



class CompanyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    code: Code
    name: Name


class CompanyUpdate(BaseModel):
    """Solo el nombre: el código es el identificador estable (lo usa data.py)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: Name


class AdminUserOut(BaseModel):
    id: str
    email: str
    is_active: bool
    is_platform_admin: bool
    created_at: datetime


class HistoryEventOut(BaseModel):
    """Un cambio de negocio: qué, sobre qué, en qué empresa, quién y cuándo."""

    id: str
    action: str
    resource_id: str
    company_id: str | None
    actor_id: str | None  # None: lo hizo el seed o una solicitud anónima.
    actor_email: str | None
    before: dict
    after: dict
    created_at: datetime



class AdminUserDetailOut(BaseModel):
    """Todo sobre un usuario, para el master admin.

    Para limitar QUÉ se ve, quita campos de este schema (FastAPI no devuelve lo
    que no está aquí). Para limitar QUIÉN lo ve, cambia la dependencia de la
    ruta (hoy require_platform_admin).
    """

    id: str
    email: str
    is_active: bool
    deleted_at: datetime | None
    is_platform_admin: bool
    max_sessions: int | None  # null = el máximo por defecto del servicio.
    created_at: datetime
    updated_at: datetime
    profile: ProfileOut | None
    documents: list[DocumentOut]
    memberships: list[MembershipOut]  # Activas, con puestos, áreas y roles.
    active_sessions: int
