from dataclasses import dataclass

from fastapi import Query
from pydantic import BaseModel


@dataclass
class Page:
    """Paginación por limit/offset (docs/api.md). Uso: `page: Page = Depends()`."""

    limit: int = Query(default=50, ge=1, le=200, description="Máximo de elementos.")
    offset: int = Query(default=0, ge=0, description="Elementos a saltar.")


class PageOut[T](BaseModel):
    """Respuesta de un listado: los elementos pedidos y el total sin paginar."""

    items: list[T]
    total: int
