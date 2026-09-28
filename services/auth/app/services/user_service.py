from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.common.mixin_model import utcnow
from app.models.entities import AuthSession, ChangeHistory, Profile, User
from app.repositories.user_repository import UserRepository
from app.schemas.me import (
    AreaOut,
    CompanyOut,
    MembershipOut,
    MeResponse,
    PositionOut,
    SessionOut,
)
from app.schemas.user import UserCreate
from app.services.profile_service import profile_out


class EmailAlreadyExistsError(Exception):
    """El correo ya está reservado por una cuenta."""


class UserService:
    def __init__(self, session: Session):
        self.session = session
        self.repository = UserRepository(session)

    def register_user(self, data: UserCreate) -> User:
        """Registra una cuenta y su perfil sin conceder acceso empresarial."""
        email = str(data.email).strip().lower()

        # Se calcula antes de abrir la transacción de base de datos.
        password_hash = hash_password(
            data.password.get_secret_value()
        )

        try:
            # Confirma todo al terminar o revierte todo si ocurre una excepción.
            with self.session.begin():
                # Camino habitual: detecta el duplicado sin intentar insertar.
                existing_user = self.repository.get_user_by_email(email)

                if existing_user is not None:
                    raise EmailAlreadyExistsError(
                        "El correo ya está registrado."
                    )

                now = utcnow()

                user = User(
                    email=email,
                    password_hash=password_hash,
                    is_active=True,
                    created_at=now,
                    updated_at=now,
                )

                # El flush del repository genera el ID y comprueba restricciones.
                self.repository.add(user)

                # Autorregistro: vinculamos la acción con la cuenta creada.
                # Esto no significa que el correo esté verificado.
                user.created_by = user.id
                user.updated_by = user.id

                profile = Profile(
                    user_id=user.id,
                    created_by=user.id,
                    updated_by=user.id,
                    created_at=now,
                    updated_at=now,
                    is_active=True,
                )
                self.repository.add_profile(profile)

                # Cada recurso creado tiene su evento.
                # No copiamos contraseñas ni hashes al historial.
                for action, resource_id in (
                    ("user.registered", user.id),
                    ("profile.created", profile.id),
                ):
                    self.repository.add_history(
                        ChangeHistory(
                            action=action,
                            resource_id=resource_id,
                            before={},
                            after={"is_active": True},
                            created_by=user.id,
                            updated_by=user.id,
                            created_at=now,
                            updated_at=now,
                            is_active=True,
                        )
                    )
        except IntegrityError as exc:
            # Carrera: otra solicitud registró el mismo email entre la consulta
            # y el INSERT. El UNIQUE de users.email lo rechaza y el with ya
            # revirtió la transacción. Supuesto: es la única restricción que
            # puede fallar aquí. Si se añaden otras, distinguirlas por nombre
            # del constraint (ver naming_convention en base-de-datos.md).
            raise EmailAlreadyExistsError(
                "El correo ya está registrado."
            ) from exc

        return user

    def get_me(self, user: User, auth_session: AuthSession) -> MeResponse:
        """Arma la respuesta de /me: el usuario, su sesión, su perfil y sus empresas."""
        with self.session.begin():
            profile = self.repository.get_profile(user.id)
            memberships = self.memberships_of(user.id)

        return MeResponse(
            id=user.id,
            email=user.email,
            is_platform_admin=user.is_platform_admin,
            profile=profile_out(profile) if profile is not None else None,
            session=SessionOut(id=auth_session.id, expires_at=auth_session.expires_at),
            memberships=memberships,
        )

    def memberships_of(self, user_id: str) -> list[MembershipOut]:
        """Membresías activas con sus puestos, áreas y roles. Se llama dentro de
        una transacción abierta (la usan /me y la vista del master admin).

        Tres consultas simples (membresías, puestos, roles) que luego se
        agrupan en Python, en lugar de una sola consulta con muchos joins.
        """
        memberships = self.repository.get_memberships(user_id)
        positions = self.repository.get_positions([membership.id for membership, _ in memberships])
        role_codes = self.repository.get_role_codes([position.id for _, position, _ in positions])

        # position_id → [códigos de rol]
        roles_by_position: dict[str, list[str]] = {}
        for position_id, role_code in role_codes:
            roles_by_position.setdefault(position_id, []).append(role_code)

        # membership_id → [puestos con su área y roles]
        positions_by_membership: dict[str, list[PositionOut]] = {}
        for membership_id, position, area in positions:
            positions_by_membership.setdefault(membership_id, []).append(
                PositionOut(
                    id=position.id,
                    code=position.code,
                    name=position.name,
                    area=AreaOut(id=area.id, code=area.code, name=area.name),
                    roles=roles_by_position.get(position.id, []),
                )
            )

        return [
            MembershipOut(
                company=CompanyOut(id=company.id, code=company.code, name=company.name),
                positions=positions_by_membership.get(membership.id, []),
            )
            for membership, company in memberships
        ]
