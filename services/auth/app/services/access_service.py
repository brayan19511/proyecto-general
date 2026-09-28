"""Contexto de empresa y permisos efectivos.

Cada solicitud empresarial indica su empresa con el header X-Company-Id. El
cliente solo la propone: aquí se comprueba en la base que el usuario tenga
acceso y se calculan sus permisos en esa empresa.

Permisos efectivos = unión de los permisos de todos sus puestos activos en la
empresa, conservando el alcance de cada uno:
  company → toda la empresa.
  area    → solo el área del puesto que lo concede.
  own     → solo recursos propios.
El master admin (is_platform_admin) tiene todos los permisos con alcance company.
"""

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.core.permissions import PERMISSIONS
from app.models.entities import Company, Membership, User
from app.repositories.access_repository import AccessRepository


class CompanyAccessDeniedError(Exception):
    """La empresa no existe, está inhabilitada o el usuario no pertenece a ella."""


class PermissionDeniedError(Exception):
    """El usuario no tiene el permiso con el alcance que exige el recurso."""


@dataclass
class Grant:
    """Alcance acumulado de un permiso para el usuario en la empresa."""

    company: bool = False
    area_ids: set[str] = field(default_factory=set)
    own: bool = False


@dataclass
class CompanyContext:
    """Quién actúa, en qué empresa y con qué permisos. Lo usan las rutas empresariales."""

    user: User
    company: Company
    membership: Membership | None  # None para el master admin sin membresía.
    is_platform_admin: bool
    grants: dict[str, Grant]

    def can(
        self,
        permission: str,
        area_id: str | None = None,
        owner_id: str | None = None,
    ) -> bool:
        """¿Puede ejercer este permiso sobre un recurso concreto?

        - area_id: área del recurso, si pertenece a una.
        - owner_id: usuario dueño del recurso, si aplica el scope own.
        Sin area_id ni owner_id solo alcanza un permiso con scope company.
        """
        if self.is_platform_admin:
            return True
        grant = self.grants.get(permission)
        if grant is None:
            return False
        if grant.company:
            return True
        if area_id is not None and area_id in grant.area_ids:
            return True
        return grant.own and owner_id is not None and owner_id == self.user.id

    def has_any(self, permission: str) -> bool:
        """¿Tiene el permiso con algún alcance? Sirve para decidir si una ruta
        se puede usar; luego cada recurso se comprueba con can()."""
        return self.is_platform_admin or permission in self.grants


class LastAdminError(Exception):
    """La operación dejaría a la empresa sin ningún administrador efectivo."""


# Administrador efectivo: puede gestionar miembros en toda la empresa, así que
# puede recuperar la administración (asignar puestos, agregar personas).
ADMIN_PERMISSION = "memberships.manage"


class LastAdminGuard:
    """Protege al último admin de una empresa (docs/requisitos.md).

    Uso, dentro de la transacción de una operación que quita privilegios:
        guard = LastAdminGuard(session, company_id)   # bloquea la empresa y cuenta
        ...cambios...
        guard.check()                                 # vuelve a contar; si quedó en 0, error

    El bloqueo de la empresa hace que dos operaciones así se ejecuten en fila:
    dos admins no pueden quitarse el puesto a la vez y dejarla vacía. Si la
    empresa ya no tenía admins (solo la gestiona el master), no bloquea nada.
    """

    def __init__(self, session: Session, company_id: str):
        self.session = session
        self.company_id = company_id
        self.repository = AccessRepository(session)
        self.repository.lock_company(company_id)
        self.before = self.repository.count_company_admins(company_id, ADMIN_PERMISSION)

    def check(self) -> None:
        self.session.flush()  # Para que el conteo vea los cambios de esta transacción.
        after = self.repository.count_company_admins(self.company_id, ADMIN_PERMISSION)
        if self.before > 0 and after == 0:
            raise LastAdminError()


def ensure_can_delegate(
    ctx: CompanyContext, grants: list[tuple[str, str]], area_id: str
) -> None:
    """Regla de delegación para lo que se otorga dentro de un área.

    Al vincular un rol a un puesto, o asignar un puesto a una persona, se
    otorgan los permisos `grants` en el área `area_id` del puesto. Quien actúa
    debe tener cada uno con al menos ese alcance:
      company → lo necesita en toda la empresa.
      area    → lo necesita en esa área (o en toda la empresa).
      own     → lo necesita con cualquier alcance.
    Así nadie concede más de lo que él mismo tiene. Quitar no exige esta regla:
    reduce privilegios.
    """
    for code, scope in grants:
        if scope not in PERMISSIONS.get(code, []):
            continue  # No lo admite el catálogo: no concede nada, no hay que delegarlo.
        if scope == "company":
            allowed = ctx.can(code)
        elif scope == "area":
            allowed = ctx.can(code, area_id=area_id)
        else:
            allowed = ctx.has_any(code)
        if not allowed:
            raise PermissionDeniedError()


class AccessService:
    def __init__(self, session: Session):
        self.session = session
        self.repository = AccessRepository(session)

    def build_context(
        self, user: User, company_id: str, as_platform_admin: bool = True
    ) -> CompanyContext:
        """as_platform_admin=False calcula los permisos solo por sus puestos,
        aunque el usuario sea master admin. Lo usan las API keys: una key nunca
        hereda los poderes de plataforma de su dueño."""
        with self.session.begin():
            company = self.repository.get_active_company(company_id)
            if company is None:
                raise CompanyAccessDeniedError()

            if user.is_platform_admin and as_platform_admin:
                # Solo los que siguen en el catálogo del código.
                codes = [
                    code
                    for code in self.repository.get_all_permission_codes()
                    if code in PERMISSIONS
                ]
                return CompanyContext(
                    user=user,
                    company=company,
                    membership=self.repository.get_active_membership(user.id, company.id),
                    is_platform_admin=True,
                    grants={code: Grant(company=True) for code in codes},
                )

            membership = self.repository.get_active_membership(user.id, company.id)
            if membership is None:
                raise CompanyAccessDeniedError()

            grants: dict[str, Grant] = {}
            for code, scope, area_id in self.repository.get_grants(membership.id):
                # El catálogo manda: un rol-permiso con un scope que el permiso
                # ya no admite (o un permiso retirado del código) no concede nada.
                if scope not in PERMISSIONS.get(code, []):
                    continue
                grant = grants.setdefault(code, Grant())
                if scope == "company":
                    grant.company = True
                elif scope == "area":
                    grant.area_ids.add(area_id)
                elif scope == "own":
                    grant.own = True

        return CompanyContext(
            user=user,
            company=company,
            membership=membership,
            is_platform_admin=False,
            grants=grants,
        )
