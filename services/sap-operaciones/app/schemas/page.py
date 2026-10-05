from dataclasses import dataclass

from fastapi import Query


@dataclass
class Page:
    """Paginación simple por limit/offset para los listados.

    Uso en una ruta: `page: Page = Depends()`. El cliente pide páginas
    siguientes con next_offset de la respuesta; null = no hay más.
    """

    limit: int = Query(default=100, ge=1, le=500, description="Máximo de elementos.")
    offset: int = Query(default=0, ge=0, description="Elementos a saltar.")

    def next_offset(self, total: int) -> int | None:
        following = self.offset + self.limit
        return following if following < total else None
