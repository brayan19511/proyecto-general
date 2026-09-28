from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr

# Límites de contraseña del registro. config.py repite los mismos para el admin del seed.
Password = Annotated[SecretStr, Field(min_length=3, max_length=100)]


class UserCreate(BaseModel):
    """Datos que el cliente puede enviar para registrarse."""

    # Rechaza campos adicionales, como is_active o created_by.
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: Password


class UserResponse(BaseModel):
    """Datos públicos que devolvemos del usuario."""

    # Permite construir la respuesta desde un objeto SQLAlchemy.
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr


class PasswordChange(BaseModel):
    """Cambio de la contraseña propia: exige la actual."""

    model_config = ConfigDict(extra="forbid")

    # Solo máximo: la actual pudo crearse con una política anterior.
    current_password: SecretStr = Field(min_length=1, max_length=100)
    new_password: Password


class PasswordReset(BaseModel):
    """Contraseña nueva asignada por el master admin."""

    model_config = ConfigDict(extra="forbid")

    new_password: Password
