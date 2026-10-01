from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import Code, Name


class RoleCreate(BaseModel):
    # La empresa sale del header X-Company-Id, nunca del body.
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    code: Code
    name: Name


class RoleUpdate(BaseModel):
    """Solo el nombre: el código es el identificador estable del rol."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: Name


class RolePermissionCreate(BaseModel):
    """Otorga un permiso del catálogo (app/core/permissions.py) al rol."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    permission: str = Field(min_length=1, max_length=100)
    scope: Literal["company", "area", "own"]


class RolePermissionOut(BaseModel):
    id: str  # Id de la concesión: se usa para retirarla.
    permission: str
    scope: str


class RoleOut(BaseModel):
    id: str
    code: str
    name: str
    is_active: bool
    deleted_at: datetime | None  # Con valor: dado de baja (solo con include_deleted).
    permissions: list[RolePermissionOut]  # Solo concesiones vigentes.
    created_at: datetime
    updated_at: datetime


class PermissionCatalogOut(BaseModel):
    """Un permiso del catálogo: qué alcances admite y si ya está cargado en la base."""

    code: str
    scopes: list[str]  # company, area u own
    loaded: bool  # false: falta ejecutar el seed para poder concederlo
