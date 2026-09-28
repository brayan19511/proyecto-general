from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.identity import DocumentOut


class ProfileOut(BaseModel):
    first_names: str | None
    last_names: str | None
    birth_date: date | None
    nationality_country_code: str | None  # ISO 3166-1 alfa-2 (catálogo /catalog/countries).


class CompanyOut(BaseModel):
    id: str
    code: str
    name: str


class AreaOut(BaseModel):
    id: str
    code: str
    name: str


class PositionOut(BaseModel):
    id: str
    code: str
    name: str
    area: AreaOut
    roles: list[str]  # Códigos de rol heredados por el puesto.


class MembershipOut(BaseModel):
    company: CompanyOut
    positions: list[PositionOut]


class SessionOut(BaseModel):
    id: str
    expires_at: datetime  # Fin absoluto de la sesión: después hay que volver a iniciar sesión.


class PermissionGrantOut(BaseModel):
    code: str
    company: bool  # true: vale en toda la empresa.
    area_ids: list[str]  # Áreas donde vale, si el alcance es de área.
    own: bool  # true: vale solo sobre recursos propios.


class CompanyPermissionsResponse(BaseModel):
    """Permisos efectivos en la empresa del header X-Company-Id."""

    company: CompanyOut
    is_platform_admin: bool
    permissions: list[PermissionGrantOut]


class MeResponse(BaseModel):
    """Quién eres y a qué empresas perteneces. No incluye datos sensibles."""

    id: str
    email: str
    # Master admin: accede a todas las empresas aunque no tenga membresías.
    is_platform_admin: bool
    profile: ProfileOut | None
    session: SessionOut
    memberships: list[MembershipOut]


class ProfileUpdate(BaseModel):
    """Datos personales propios. Solo se modifican los campos enviados;
    enviar null borra el valor."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    first_names: str | None = Field(default=None, max_length=100)
    last_names: str | None = Field(default=None, max_length=100)
    birth_date: date | None = None
    # Debe existir en el catálogo; nacionalidad no es país de residencia ni emisor.
    nationality_country_code: str | None = Field(default=None, min_length=2, max_length=2)


class SessionDetailOut(BaseModel):
    """Una sesión vigente del usuario, para verla y cerrarla."""

    id: str
    created_at: datetime
    expires_at: datetime
    last_seen_at: datetime
    initial_ip: str
    last_ip: str
    client_description: str  # Declarado por el navegador: orientativo.
    current: bool  # true: la sesión de esta solicitud.


class RevokedSessionsOut(BaseModel):
    revoked: int


class MyProfileOut(BaseModel):
    """GET /auth/me/profile: datos personales y documentos vigentes."""

    profile: ProfileOut | None
    documents: list[DocumentOut]
