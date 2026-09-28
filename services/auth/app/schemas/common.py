from typing import Annotated

from pydantic import BaseModel, Field

# Código estable de áreas, puestos y roles: mayúsculas, dígitos y guion bajo.
# Es el identificador que usa data.py; por eso no se modifica tras crearlo.
Code = Annotated[str, Field(min_length=1, max_length=50, pattern=r"^[A-Z0-9_]+$")]

# Nombre visible. Los límites coinciden con las columnas String(150).
Name = Annotated[str, Field(min_length=1, max_length=150)]


class Ref(BaseModel):
    """Referencia breve a otro recurso (empresa, área) dentro de una respuesta."""

    id: str
    code: str
    name: str
