from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.common import Code, Name, Ref


class PositionCreate(BaseModel):
    # La empresa sale del header X-Company-Id; el área debe ser de esa empresa.
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    code: Code
    name: Name
    # Id UUID en texto: String(36) en la base.
    area_id: str = Field(min_length=1, max_length=36)


class PositionUpdate(BaseModel):
    """Cambiar el nombre y/o mover a otra área. El código no se modifica.

    Mover de área exige positions.manage con alcance company: un admin de área
    no puede sacar un puesto de su área (dejaría de controlarlo).
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: Name | None = None
    area_id: str | None = Field(default=None, min_length=1, max_length=36)

    @model_validator(mode="after")
    def at_least_one_field(self):
        if self.name is None and self.area_id is None:
            raise ValueError("Envía al menos name o area_id.")
        return self


class PositionOut(BaseModel):
    id: str
    code: str
    name: str
    is_active: bool
    deleted_at: datetime | None  # Con valor: dado de baja (solo con include_deleted).
    area: Ref
    created_at: datetime
    updated_at: datetime


class PositionRoleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role_id: str = Field(min_length=1, max_length=36)


class PositionRoleOut(BaseModel):
    """Un rol vinculado al puesto."""

    role_id: str
    code: str
    name: str
    is_active: bool  # false si el vínculo o el rol están suspendidos.
