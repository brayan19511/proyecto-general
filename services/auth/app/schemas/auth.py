from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    # Solo máximo: el mínimo es política del registro. Si la política cambia,
    # las contraseñas antiguas deben seguir pudiendo iniciar sesión.
    password: SecretStr = Field(min_length=1, max_length=100)


class RefreshRequest(BaseModel):
    """También se usa para logout: el refresh identifica la sesión."""

    model_config = ConfigDict(extra="forbid")

    refresh_token: str = Field(min_length=1, max_length=200)


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int  # Segundos de vida del access token.
    refresh_token: str
