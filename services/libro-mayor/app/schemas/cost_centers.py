from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AreaRef(BaseModel):
    """Área de auth por su código (VENTAS, CONT…) o su id. Se valida contra auth."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    area_code: str | None = Field(default=None, max_length=50, examples=["VENTAS"])
    area_id: str | None = Field(default=None, max_length=36)

    @model_validator(mode="after")
    def one_of(self):
        if bool(self.area_code) == bool(self.area_id):
            raise ValueError("Indique area_code o area_id (uno de los dos).")
        return self


class CostCenterMappingCreate(AreaRef):
    cost_center_code: str = Field(min_length=1, max_length=100, examples=["V1141177"])
    # exact = el código completo; prefix = todo centro que empiece así (V114 → tiendas V114…).
    match_mode: Literal["exact", "prefix"] = "exact"


class CostCenterMappingUpdate(AreaRef):
    """Cambia el área. Código y modo no se editan: dar de baja y crear otra."""


class CostCenterMappingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    cost_center_code: str
    match_mode: str
    auth_area_id: str
    area_code: str
    area_name: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


class CostCenterMappingImportItem(AreaRef):
    cost_center_code: str = Field(min_length=1, max_length=100)
    match_mode: Literal["exact", "prefix"] = "exact"


class CostCenterMappingImport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # replace = da de baja las homologaciones activas que no vengan aquí; append = solo agrega o actualiza.
    mode: Literal["append", "replace"] = "append"
    dry_run: bool = False
    mappings: list[CostCenterMappingImportItem] = Field(min_length=1, max_length=5000)


class CostCenterMappingImportResult(BaseModel):
    mode: str
    dry_run: bool
    created: int
    updated: int
    unchanged: int
    deactivated: int


class CostCenterOut(BaseModel):
    """Centro de costo visto en las líneas sincronizadas. cost_center_code null = líneas sin centro."""

    cost_center_code: str | None
    sap_name: str | None
    lines: int
    last_posting_date: date | None
    area_id: str | None  # null = sin homologar
    area_name: str | None
    match_mode: str | None  # Cómo se resolvió: exact | prefix.
    mapping_code: str | None  # Código o prefijo de la homologación que aplica (p. ej. V114).
