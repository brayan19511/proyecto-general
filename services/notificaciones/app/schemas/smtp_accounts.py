"""Cuerpos y respuestas de /smtp-accounts. La empresa sale de X-Company-Id, nunca del body."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints

# Texto de una línea: sin saltos ni caracteres de control (irían a headers del correo).
_SINGLE_LINE = r"^[^\x00-\x1f\x7f]*$"

# Se recortan espacios en todo menos en la contraseña: un espacio al inicio o al
# final puede ser parte de ella.
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100, pattern=_SINGLE_LINE)]
# Nombre de host o IPv4: letras, dígitos, puntos y guiones (sin esquema, ruta ni puerto).
Host = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=255,
        pattern=r"^[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?$",
    ),
]
Username = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255, pattern=_SINGLE_LINE)]
# Se cifra antes de guardarla; nunca se devuelve.
Password = Annotated[str, StringConstraints(min_length=1, max_length=1000)]
FromName = Annotated[str, StringConstraints(strip_whitespace=True, max_length=100, pattern=_SINGLE_LINE)]
Security = Literal["starttls", "ssl"]
Port = Annotated[int, Field(ge=1, le=65535)]
Priority = Annotated[int, Field(ge=0, le=1000)]
Timeout = Annotated[int, Field(ge=1, le=120)]


class SmtpAccountCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Name = Field(examples=["Office 365 principal"])
    host: Host = Field(examples=["smtp.office365.com"])
    port: Port = Field(examples=[587])
    security: Security
    username: Username | None = None
    password: Password | None = None
    from_email: EmailStr
    from_name: FromName | None = Field(default=None, examples=["Tesorería"])
    priority: Priority = Field(examples=[1])
    timeout_seconds: Timeout = 30


class SmtpAccountUpdate(BaseModel):
    """Solo cambian los campos enviados. username, password y from_name admiten
    null (lo borran); los demás no."""

    model_config = ConfigDict(extra="forbid")

    name: Name | None = None
    host: Host | None = None
    port: Port | None = None
    security: Security | None = None
    username: Username | None = None
    password: Password | None = None
    from_email: EmailStr | None = None
    from_name: FromName | None = None
    priority: Priority | None = None
    timeout_seconds: Timeout | None = None


# Campos de SmtpAccountUpdate que no admiten null.
NOT_NULL_FIELDS = ("name", "host", "port", "security", "from_email", "priority", "timeout_seconds")


class SmtpAccountTestOut(BaseModel):
    """Resultado de probar una cuenta (conexión, TLS y autenticación; no envía correo).

    error_kind (solo si ok es false):
    - blocked_address: puerto o dirección no permitidos por la configuración.
    - connection: no se pudo conectar o el servidor cortó.
    - timeout: el servidor no respondió dentro de timeout_seconds.
    - tls: falló el cifrado o la verificación del certificado, o no ofrece STARTTLS.
    - auth: usuario o contraseña rechazados.
    - credentials_unreadable: la contraseña guardada no se puede descifrar (clave retirada).
    - unknown: otro error.
    """

    ok: bool
    error_kind: str | None = None


class SmtpAccountOut(BaseModel):
    """Nunca incluye la contraseña: solo si hay una guardada."""

    id: str
    name: str
    host: str
    port: int
    security: str
    username: str | None
    has_password: bool
    from_email: str
    from_name: str | None
    priority: int
    timeout_seconds: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None
