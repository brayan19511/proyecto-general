"""Cambio de contraseña: por el propio usuario o por el master admin.

Propio (PATCH /me/password):
  - Exige la contraseña actual. Si alguien roba un access token, no puede
    cambiar la contraseña sin conocerla.
  - Los fallos cuentan en el mismo bloqueo del login (email + IP): no sirve
    para adivinar la contraseña actual.
  - Cierra las demás sesiones; la actual sigue abierta.

Por el master admin (POST /admin/users/{id}/password):
  - Es la recuperación de cuenta asistida mientras no exista un canal propio
    (correo o SMS) para que el usuario la recupere solo.
  - Cierra TODAS las sesiones del usuario.

En ambos casos el historial registra el cambio, nunca la contraseña ni su hash.
"""

from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.models.common.mixin_model import utcnow
from app.models.entities import User
from app.repositories.auth_repository import AuthRepository
from app.repositories.user_repository import UserRepository
from app.services.auth_service import AuthService, user_can_login
from app.services.common import history_event, touch
from app.services.login_throttle import LoginThrottle, bucket_key


class WrongCurrentPasswordError(Exception):
    """La contraseña actual no coincide."""


class SamePasswordError(Exception):
    """La nueva contraseña es igual a la actual."""


class UserNotFoundError(Exception):
    """No existe, está dado de baja o inhabilitado."""


class PasswordService:
    def __init__(self, session: Session):
        self.session = session
        self.auth_repository = AuthRepository(session)
        self.users = UserRepository(session)
        self.auth = AuthService(session)

    def change_own(
        self,
        user: User,
        current_session_id: str,
        current_password: str,
        new_password: str,
        ip: str,
    ) -> int:
        """Devuelve cuántas otras sesiones se cerraron."""
        throttle = LoginThrottle(self.session)
        key = bucket_key(user.email, ip)
        now = utcnow()

        with self.session.begin():
            throttle.check(key, now)  # 429 si esa combinación está bloqueada.

        # Argon2 fuera de la transacción.
        if not verify_password(current_password, user.password_hash):
            throttle.record_failure(key, now)
            raise WrongCurrentPasswordError()
        if verify_password(new_password, user.password_hash):
            raise SamePasswordError()
        new_hash = hash_password(new_password)

        with self.session.begin():
            locked = self.auth_repository.lock_user(user.id)
            self._set_password(locked, new_hash, user.id, now, "user.password_changed")
            # Las demás sesiones pudieron abrirse con la contraseña anterior.
            return self.auth.revoke_sessions_in_transaction(
                user.id, user.id, "password_changed", now, except_session_id=current_session_id
            )

    def reset_by_admin(self, admin: User, user_id: str, new_password: str) -> int:
        """Devuelve cuántas sesiones se cerraron."""
        new_hash = hash_password(new_password)
        now = utcnow()
        with self.session.begin():
            user = self.auth_repository.lock_user(user_id)
            if user is None or not user_can_login(user):
                raise UserNotFoundError()
            self._set_password(user, new_hash, admin.id, now, "user.password_reset")
            return self.auth.revoke_sessions_in_transaction(
                user.id, admin.id, "password_reset", now
            )

    def _set_password(self, user: User, new_hash: str, actor_id: str, now, action: str) -> None:
        user.password_hash = new_hash
        touch(user, actor_id, now)
        self.users.add_history(
            history_event(
                action, user.id, None, actor_id, now,
                before={},
                after={"password_changed": True},  # Nunca la contraseña ni su hash.
            )
        )
