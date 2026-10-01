"""Configuración de la empresa en pagos-proveedores (/settings)."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

TemplateCode = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[a-z0-9][a-z0-9_.-]{0,99}$")]


class SettingsOut(BaseModel):
    default_template_code: str | None  # Elegida por la empresa; null = la del servicio.
    effective_template_code: str  # La que usará el próximo envío.
    service_template_code: str  # DEFAULT_TEMPLATE_CODE del servicio.


class SettingsUpdate(BaseModel):
    """Reemplaza la configuración. default_template_code null = volver a la del servicio."""

    model_config = ConfigDict(extra="forbid")

    default_template_code: TemplateCode | None
