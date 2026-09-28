from platform_audit import step
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import hash_password
from app.models.common.mixin_model import utcnow
from app.models.entities import (
    Area,
    Assignment,
    ChangeHistory,
    Company,
    Country,
    IdentityDocumentType,
    Membership,
    Permission,
    Position,
    PositionRole,
    Profile,
    Role,
    RolePermission,
    User,
)
from app.repositories.seed_repository import SeedRepository
from app.repositories.user_repository import UserRepository
from app.schemas.seed import SeedItem, SeedResponse
from app.seeds import data


class SeedConflictError(Exception):
    """El seed no pudo completarse; no se confirmó ningún cambio."""


class SeedService:
    """Crea los permisos y las empresas de data.py con su estructura, y el admin del .env.

    Idempotente: lo que ya existe, aunque esté dado de baja, no se modifica
    ni se reactiva. Todo ocurre en una sola transacción.
    """

    def __init__(self, session: Session, config: Settings):
        self.session = session
        self.config = config
        self.repository = SeedRepository(session)
        self.users = UserRepository(session)
        self.items: list[SeedItem] = []
        self.now = utcnow()  # Mismo instante para todo lo creado en esta ejecución.

    def run(self) -> SeedResponse:
        # Argon2 es lento a propósito: se calcula fuera de la transacción.
        password_hash = hash_password(
            self.config.SEED_ADMIN_PASSWORD.get_secret_value()
        )

        try:
            with self.session.begin():
                admin = self.ensure_admin_user(password_hash)
                permissions = self.ensure_permissions()
                self.ensure_catalog()

                for company_data in data.COMPANIES:
                    with step(f"seed empresa {company_data['code']}"):
                        company = self.ensure_company(company_data)
                        areas = self.ensure_areas(company, company_data["areas"])
                        positions = self.ensure_positions(
                            company, company_data["positions"], areas
                        )
                        roles = self.ensure_roles(company, company_data["roles"])
                        self.ensure_role_permissions(
                            company, company_data["role_permissions"], roles, permissions
                        )
                        self.ensure_position_roles(
                            company, company_data["position_roles"], positions, roles
                        )

                        admin_position_code = company_data["admin_position_code"]
                        if admin_position_code is not None:
                            membership = self.ensure_membership(admin, company)
                            self.ensure_assignment(
                                company, membership, positions[admin_position_code]
                            )
        except IntegrityError as exc:
            # Otro seed insertó lo mismo a la vez. El with ya revirtió todo.
            raise SeedConflictError(
                "Otro seed modificó los datos a la vez; reintentar."
            ) from exc

        return SeedResponse(items=self.items)

    def ensure_admin_user(self, password_hash: str) -> User:
        # Misma normalización que el registro.
        email = str(self.config.SEED_ADMIN_EMAIL).strip().lower()
        user = self.users.get_user_by_email(email)

        if user is not None:
            # created_by NULL solo ocurre en registros del seed. Una cuenta con
            # created_by es pública (se registró sola): promoverla daría
            # privilegios a quien la registró.
            if user.created_by is not None:
                raise SeedConflictError(
                    "SEED_ADMIN_EMAIL pertenece a una cuenta registrada públicamente; "
                    "no se promueve automáticamente."
                )
            # No se cambia la contraseña ni se reactiva.
            self._report("admin_user", user.id, "existing")
            return user

        user = self.repository.add(
            User(
                email=email,
                password_hash=password_hash,
                # Master admin: solo se otorga al crearlo. Si luego se retira,
                # volver a ejecutar el seed no lo restituye.
                is_platform_admin=True,
                **self._audit(),
            )
        )
        profile = self.repository.add(Profile(user_id=user.id, **self._audit()))
        # Sin email ni hash en el historial, igual que el registro.
        self._history(
            "seed.user.created", user.id, None, {"is_platform_admin": True}
        )
        self._history("seed.profile.created", profile.id, None, {})
        self._report("admin_user", user.id, "created")
        return user

    def ensure_company(self, company_data: dict) -> Company:
        code = company_data["code"]
        company = self.repository.get_company_by_code(code)
        if company is not None:
            # Existe, aunque esté dada de baja: no se modifica ni se reactiva.
            self._report(f"company:{code}", company.id, "existing")
            return company

        company = self.repository.add(
            Company(code=code, name=company_data["name"], **self._audit())
        )
        self._history("seed.company.created", company.id, company.id, {"code": code})
        self._report(f"company:{code}", company.id, "created")
        return company

    def ensure_areas(self, company: Company, items: list[dict]) -> dict[str, Area]:
        """Devuelve las áreas por código para que los puestos las encuentren."""
        areas: dict[str, Area] = {}
        for item in items:
            name = f"area:{company.code}:{item['code']}"
            area = self.repository.get_area(company.id, item["code"])
            if area is not None:
                self._report(name, area.id, "existing")
            else:
                area = self.repository.add(
                    Area(
                        company_id=company.id,
                        code=item["code"],
                        name=item["name"],
                        **self._audit(),
                    )
                )
                self._history(
                    "seed.area.created", area.id, company.id, {"code": area.code}
                )
                self._report(name, area.id, "created")
            areas[item["code"]] = area
        return areas

    def ensure_positions(
        self, company: Company, items: list[dict], areas: dict[str, Area]
    ) -> dict[str, Position]:
        positions: dict[str, Position] = {}
        for item in items:
            name = f"position:{company.code}:{item['code']}"
            position = self.repository.get_position(company.id, item["code"])
            if position is not None:
                self._report(name, position.id, "existing")
            else:
                position = self.repository.add(
                    Position(
                        company_id=company.id,
                        # Código de data.py → id real del área de esta empresa.
                        area_id=areas[item["area_code"]].id,
                        code=item["code"],
                        name=item["name"],
                        **self._audit(),
                    )
                )
                self._history(
                    "seed.position.created",
                    position.id,
                    company.id,
                    {"code": position.code},
                )
                self._report(name, position.id, "created")
            positions[item["code"]] = position
        return positions

    def ensure_roles(self, company: Company, items: list[dict]) -> dict[str, Role]:
        roles: dict[str, Role] = {}
        for item in items:
            name = f"role:{company.code}:{item['code']}"
            role = self.repository.get_role(company.id, item["code"])
            if role is not None:
                self._report(name, role.id, "existing")
            else:
                role = self.repository.add(
                    Role(
                        company_id=company.id,
                        code=item["code"],
                        name=item["name"],
                        **self._audit(),
                    )
                )
                self._history(
                    "seed.role.created",
                    role.id,
                    company.id,
                    {"code": role.code, "name": role.name},
                )
                self._report(name, role.id, "created")
            roles[item["code"]] = role
        return roles

    def ensure_permissions(self) -> dict[str, Permission]:
        """Catálogo global: los permisos no pertenecen a una empresa."""
        permissions: dict[str, Permission] = {}
        for code in data.PERMISSIONS:
            name = f"permission:{code}"
            permission = self.repository.get_permission(code)
            if permission is not None:
                self._report(name, permission.id, "existing")
            else:
                permission = self.repository.add(Permission(code=code, **self._audit()))
                self._history("seed.permission.created", permission.id, None, {"code": code})
                self._report(name, permission.id, "created")
            permissions[code] = permission
        return permissions

    def ensure_catalog(self) -> None:
        """Países y tipos de documento: catálogos globales, sin empresa."""
        for item in data.COUNTRIES:
            name = f"country:{item['code']}"
            country = self.repository.get_country(item["code"])
            if country is not None:
                self._report(name, country.id, "existing")
                continue
            country = self.repository.add(
                Country(code=item["code"], name=item["name"], **self._audit())
            )
            self._history("seed.country.created", country.id, None, {"code": country.code})
            self._report(name, country.id, "created")

        for item in data.DOCUMENT_TYPES:
            name = f"document_type:{item['country']}:{item['code']}"
            doc_type = self.repository.get_document_type(item["country"], item["code"])
            if doc_type is not None:
                self._report(name, doc_type.id, "existing")
                continue
            doc_type = self.repository.add(
                IdentityDocumentType(
                    issuing_country_code=item["country"],
                    code=item["code"],
                    name=item["name"],
                    category=item["category"],
                    pattern=item["pattern"],
                    **self._audit(),
                )
            )
            self._history(
                "seed.document_type.created",
                doc_type.id,
                None,
                {"country": item["country"], "code": item["code"]},
            )
            self._report(name, doc_type.id, "created")

    def ensure_role_permissions(
        self,
        company: Company,
        role_permissions: dict[str, list[tuple[str, str]]],
        roles: dict[str, Role],
        permissions: dict[str, Permission],
    ) -> None:
        for role_code, grants in role_permissions.items():
            role = roles[role_code]
            for permission_code, scope in grants:
                # Un scope solo se acepta si el permiso lo admite (data.PERMISSIONS).
                if scope not in data.PERMISSIONS[permission_code]:
                    raise SeedConflictError(
                        f"data.py: {permission_code} no admite scope '{scope}'."
                    )
                permission = permissions[permission_code]
                name = f"role_permission:{company.code}:{role_code}:{permission_code}:{scope}"
                link = self.repository.get_role_permission(role.id, permission.id, scope)
                if link is not None:
                    # Si fue retirado, sigue retirado: no se restituye el permiso.
                    self._report(name, link.id, "existing")
                    continue
                link = self.repository.add(
                    RolePermission(
                        role_id=role.id,
                        permission_id=permission.id,
                        scope=scope,
                        **self._audit(),
                    )
                )
                self._history(
                    "seed.role_permission.created",
                    link.id,
                    company.id,
                    {"role": role_code, "permission": permission_code, "scope": scope},
                )
                self._report(name, link.id, "created")

    def ensure_position_roles(
        self,
        company: Company,
        position_roles: dict[str, list[str]],
        positions: dict[str, Position],
        roles: dict[str, Role],
    ) -> None:
        for position_code, role_codes in position_roles.items():
            position = positions[position_code]
            for role_code in role_codes:
                role = roles[role_code]
                name = f"position_role:{company.code}:{position_code}:{role_code}"
                link = self.repository.get_position_role(position.id, role.id)
                if link is not None:
                    # Si fue dada de baja, sigue de baja: no se restituye el rol.
                    self._report(name, link.id, "existing")
                    continue
                link = self.repository.add(
                    PositionRole(
                        company_id=company.id,
                        position_id=position.id,
                        role_id=role.id,
                        **self._audit(),
                    )
                )
                self._history(
                    "seed.position_role.created",
                    link.id,
                    company.id,
                    {"position": position_code, "role": role_code},
                )
                self._report(name, link.id, "created")

    def ensure_membership(self, user: User, company: Company) -> Membership:
        name = f"membership:{company.code}"
        membership = self.repository.get_membership(user.id, company.id)
        if membership is not None:
            # Si fue dada de baja, sigue de baja: no se reactiva.
            self._report(name, membership.id, "existing")
            return membership

        membership = self.repository.add(
            Membership(user_id=user.id, company_id=company.id, **self._audit())
        )
        self._history("seed.membership.created", membership.id, company.id, {})
        self._report(name, membership.id, "created")
        return membership

    def ensure_assignment(
        self, company: Company, membership: Membership, position: Position
    ) -> None:
        name = f"assignment:{company.code}:{position.code}"
        assignment = self.repository.get_assignment(membership.id, position.id)
        if assignment is not None:
            self._report(name, assignment.id, "existing")
            return

        assignment = self.repository.add(
            Assignment(
                company_id=company.id,
                membership_id=membership.id,
                position_id=position.id,
                **self._audit(),
            )
        )
        self._history(
            "seed.assignment.created",
            assignment.id,
            company.id,
            {"position": position.code},
        )
        self._report(name, assignment.id, "created")

    def _audit(self) -> dict:
        """Campos comunes de un alta del seed: único caso con actor NULL."""
        return {
            "created_at": self.now,
            "updated_at": self.now,
            "created_by": None,
            "updated_by": None,
            "is_active": True,
        }

    def _history(
        self, action: str, resource_id: str, company_id: str | None, after: dict
    ) -> None:
        # company_id es None para recursos globales como el usuario y su perfil.
        self.repository.add_history(
            ChangeHistory(
                action=action,
                resource_id=resource_id,
                company_id=company_id,
                before={},
                after={**after, "is_active": True},
                **self._audit(),
            )
        )

    def _report(self, resource: str, resource_id: str, status: str) -> None:
        self.items.append(SeedItem(resource=resource, id=resource_id, status=status))
