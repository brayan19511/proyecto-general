"""Perfil del usuario: datos personales y documentos de identidad.

Ciclo de vida: el perfil es uno por cuenta. Nace con la cuenta (registro o
seed) y vive mientras ella exista; por eso no hay crear ni eliminar. Para
vaciar un dato se envía null. Los documentos sí tienen alta y baja propias
(ver identity_service.py).

Quién lo ve:
  - El propio usuario: GET/PATCH /auth/me/profile y /auth/me/documents.
  - El master admin: GET /auth/admin/users/{id} (todo el perfil y documentos).
Ningún dato del perfil concede permisos.
"""

from sqlalchemy.orm import Session

from app.models.common.mixin_model import utcnow
from app.models.entities import Profile, User
from app.repositories.identity_repository import IdentityRepository
from app.repositories.user_repository import UserRepository
from app.schemas.identity import DocumentOut
from app.schemas.me import MyProfileOut, ProfileOut, ProfileUpdate
from app.services.common import audit_create, history_event, touch
from app.services.identity_service import IdentityService, document_out


class InvalidProfileError(Exception):
    """Nacionalidad fuera del catálogo o fecha de nacimiento futura."""

    def __init__(self, detail: str):
        super().__init__(detail)
        self.detail = detail


def profile_out(profile: Profile) -> ProfileOut:
    return ProfileOut(
        first_names=profile.first_names,
        last_names=profile.last_names,
        birth_date=profile.birth_date,
        nationality_country_code=profile.nationality_country_code,
    )


def _json_safe(values: dict) -> dict:
    """El historial es JSON: las fechas se guardan como texto ISO."""
    return {k: v.isoformat() if hasattr(v, "isoformat") else v for k, v in values.items()}


class ProfileService:
    def __init__(self, session: Session):
        self.session = session
        self.users = UserRepository(session)
        self.identity = IdentityRepository(session)

    def get_mine(self, user: User) -> MyProfileOut:
        with self.session.begin():
            profile, documents = self.load(user.id)
        return MyProfileOut(profile=profile, documents=documents)

    def load(self, user_id: str) -> tuple[ProfileOut | None, list[DocumentOut]]:
        """Perfil y documentos vigentes de un usuario. Se llama dentro de una
        transacción abierta (la usan /me/profile y la vista del master admin)."""
        profile = self.users.get_profile(user_id)
        documents = [
            document_out(document, doc_type)
            for document, doc_type in self.identity.list_user_documents(user_id)
        ]
        return (profile_out(profile) if profile is not None else None), documents

    def update(self, user: User, data: ProfileUpdate) -> ProfileOut:
        """El usuario edita sus propios datos personales."""
        now = utcnow()
        # Solo los campos presentes en el body: permite borrar uno enviando null.
        changes = data.model_dump(include=data.model_fields_set)
        if changes.get("nationality_country_code"):
            changes["nationality_country_code"] = changes["nationality_country_code"].upper()
        if changes.get("birth_date") and changes["birth_date"] > now.date():
            raise InvalidProfileError("La fecha de nacimiento no puede ser futura.")

        with self.session.begin():
            code = changes.get("nationality_country_code")
            if code and not IdentityService(self.session).country_exists(code):
                raise InvalidProfileError("Nacionalidad desconocida: usa un código de /auth/catalog/countries.")
            profile = self.users.get_profile(user.id)
            if profile is None:
                # Toda cuenta nace con perfil; se crea si faltara.
                profile = self.users.add_profile(
                    Profile(user_id=user.id, **audit_create(user.id, now))
                )
            before = {field: getattr(profile, field) for field in changes}
            if before != changes:
                for field, value in changes.items():
                    setattr(profile, field, value)
                touch(profile, user.id, now)
                self.users.add_history(
                    history_event(
                        "profile.updated", profile.id, None, user.id, now,
                        before=_json_safe(before),
                        after=_json_safe(changes),
                    )
                )
            return profile_out(profile)
