from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ApiKeyCreate(BaseModel):
    """Crea una API key propia para la empresa activa (X-Company-Id).

    Vencimiento: expires_at (fecha), expires_in_days (duración) o ninguno.
    Sin ninguno de los dos, la key no vence (expires_at queda en null). No se
    aceptan ambos. Sin vencimiento no significa irrevocable: revocarla,
    suspender la membresía o perder los permisos la anula.

    name y description son solo para reconocerla; no conceden nada.
    scopes es la lista de permisos (códigos del catálogo) que podrá usar.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    # Permisos que podrá usar la key; nunca más de los que tienes ahora.
    scopes: list[str] = Field(min_length=1, max_length=20)
    expires_at: datetime | None = None
    expires_in_days: int | None = Field(default=None, ge=1, le=3650)

    @model_validator(mode="after")
    def one_expiration(self):
        if self.expires_at is not None and self.expires_in_days is not None:
            raise ValueError("Usa expires_at o expires_in_days, no ambos.")
        return self


class ApiKeyOut(BaseModel):
    id: str
    name: str
    description: str | None
    prefix: str  # Parte visible para reconocerla; el secreto no se vuelve a mostrar.
    scopes: list[str]
    company_id: str
    expires_at: datetime | None  # None: sin vencimiento.
    revoked_at: datetime | None
    last_used_at: datetime | None
    created_at: datetime


class ApiKeyCreated(ApiKeyOut):
    # Se muestra UNA sola vez. Guárdala: en la base solo queda su hash.
    key: str
