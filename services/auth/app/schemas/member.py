from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.schemas.common import Ref


class MemberCreate(BaseModel):
    """Agrega a la empresa un usuario YA registrado, por su email exacto.

    No crea cuentas: el registro es público (POST /users). Tampoco hay búsqueda
    abierta de usuarios: solo se agrega a quien se conoce por su email.
    """

    model_config = ConfigDict(extra="forbid")

    email: EmailStr


class AssignmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    position_id: str = Field(min_length=1, max_length=36)


class MemberPositionOut(BaseModel):
    id: str  # Id del puesto.
    code: str
    name: str
    area: Ref


class MemberOut(BaseModel):
    id: str  # Id de la membresía: se usa en las rutas /members/{id}.
    user_id: str
    email: str
    first_names: str | None
    last_names: str | None
    is_active: bool
    positions: list[MemberPositionOut]
    created_at: datetime


class MemberStatusUpdate(BaseModel):
    """Suspender (false) o reactivar (true) a un miembro.

    Suspendido pierde el acceso a la empresa de inmediato, pero conserva sus
    puestos: al reactivarlo vuelve tal como estaba (vacaciones, licencia).
    Para quien deja la empresa se usa DELETE, que retira también sus puestos.
    """

    model_config = ConfigDict(extra="forbid")

    is_active: bool
