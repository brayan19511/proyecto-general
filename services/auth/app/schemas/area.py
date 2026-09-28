from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.common import Code, Name


class AreaCreate(BaseModel):
    # extra="forbid": rechaza company_id, is_active, created_by u otros campos.
    # La empresa sale del header X-Company-Id validado, nunca del body.
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    code: Code
    name: Name


class AreaUpdate(BaseModel):
    """Solo el nombre: el código es el identificador estable del área."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: Name


class AreaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    code: str
    name: str
    is_active: bool
    deleted_at: datetime | None  # Con valor: dada de baja (solo con include_deleted).
    created_at: datetime
    updated_at: datetime
