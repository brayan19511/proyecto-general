from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

_amount = {"default": None, "max_digits": 19, "decimal_places": 4}


class CategoryCreate(BaseModel):
    """Sin parent_id: categoría ("codigo" en las consultas). Con parent_id: subcategoría ("subcodigo")."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=150, examples=["OPERACIONES GV08"])
    parent_id: str | None = Field(default=None, max_length=36)


class CategoryUpdate(BaseModel):
    """Renombra. No cambia de nivel ni de padre."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=150)


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    parent_id: str | None
    name: str
    is_active: bool
    created_at: datetime
    deleted_at: datetime | None


class RuleFields(BaseModel):
    """Condiciones (vacía = no filtra; todas las llenas deben cumplirse) y resultado."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    account_code: str | None = Field(default=None, max_length=50, examples=["959005993"])
    counter_account_code: str | None = Field(default=None, max_length=100)
    cost_center_code: str | None = Field(default=None, max_length=100, examples=["V1141177"])
    include_text: str | None = Field(default=None, max_length=255, examples=["alquiler"])
    exclude_text: str | None = Field(default=None, max_length=255)
    amount_min: Decimal | None = Field(**_amount)
    amount_max: Decimal | None = Field(**_amount)
    # Nombre de la línea en reportes ("nombre_cuenta" de proyecto-05); vacío = nombre de la cuenta SAP.
    report_name: str | None = Field(default=None, max_length=150, alias="nombre_cuenta")


class RuleCreate(RuleFields):
    priority: int = Field(ge=0, le=1_000_000, examples=[10])  # Menor = se evalúa antes.
    category_id: str = Field(min_length=1, max_length=36)


class RuleUpdate(RuleFields):
    """Solo cambian los campos enviados; null borra una condición opcional."""

    priority: int | None = Field(default=None, ge=0, le=1_000_000)
    category_id: str | None = Field(default=None, min_length=1, max_length=36)


class RuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    priority: int
    account_code: str | None
    counter_account_code: str | None
    cost_center_code: str | None
    include_text: str | None
    exclude_text: str | None
    amount_min: Decimal | None
    amount_max: Decimal | None
    category_id: str
    report_name: str | None = Field(serialization_alias="nombre_cuenta")
    is_active: bool
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


class ClassificationRunCreate(BaseModel):
    """Sin fechas: todas las líneas de la empresa; con fechas: ese rango de contabilización."""

    model_config = ConfigDict(extra="forbid")

    date_from: date | None = None
    date_to: date | None = None


class ClassificationRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    reason: str  # rule_change | manual
    rule_id: str | None
    date_from: date | None
    date_to: date | None
    status: str  # pending | running | succeeded | failed
    rows_checked: int
    rows_changed: int
    safe_error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class RuleImportItem(RuleFields):
    """Una regla de la carga masiva, con los nombres de proyecto-05: codigo (categoría) y
    subcodigo (subcategoría) por nombre; se crean si no existen."""

    priority: int = Field(ge=0, le=1_000_000)
    category: str = Field(min_length=1, max_length=150, alias="codigo", examples=["OPERACIONES GV08"])
    subcategory: str | None = Field(
        default=None, max_length=150, alias="subcodigo", examples=["DIFERENCIA EN UNIDADES DE COSTEO"]
    )


class RuleImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # replace = da de baja las reglas activas y crea estas; append = solo agrega.
    mode: Literal["replace", "append"] = "append"
    # true = valida y muestra qué pasaría, sin guardar nada.
    dry_run: bool = False
    rules: list[RuleImportItem] = Field(min_length=1, max_length=5000)


class ImportedCategoryOut(BaseModel):
    name: str
    parent: str | None  # Nombre de la categoría (codigo) si es una subcategoría (subcodigo).


class RuleImportResult(BaseModel):
    mode: str
    dry_run: bool
    rules_created: int
    rules_deactivated: int
    categories_created: list[ImportedCategoryOut]
    warnings: list[str]
    classification_run_id: str | None  # null con dry_run.
