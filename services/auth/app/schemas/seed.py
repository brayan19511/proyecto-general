from typing import Literal

from pydantic import BaseModel


class SeedItem(BaseModel):
    """Resultado de un recurso: creado ahora o ya existente."""

    resource: str
    id: str
    status: Literal["created", "existing"]


class SeedResponse(BaseModel):
    items: list[SeedItem]