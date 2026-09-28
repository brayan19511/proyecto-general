"""Login, renovación y cierre de sesión.

Flujo:
  login   → valida credenciales, crea AuthSession + RefreshToken, devuelve tokens.
  refresh → consume el refresh (rotación), crea otro y un access nuevo.
  logout  → revoca la sesión del refresh presentado.

Decisiones aplicadas (docs/requisitos.md, sección Sesiones): sesión absoluta
de SESSION_HOURS, access de ACCESS_TOKEN_MINUTES, máximo de sesiones con 409,
refresh en el body y revocación de la sesión si se reutiliza un refresh.
"""

from datetime import datetime, timedelta

from platform_audit import set_actor, step
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import DUMMY_PASSWORD_HASH, verify_password
from app.core.tokens import (
    InvalidTokenError,
    create_access_token,
    decode_access_token,
    hash_refresh_token,
    new_refresh_token,
)
from app.models.common.mixin_model import utcnow
from app.models.entities import AuthSession, ChangeHistory, RefreshToken, User
from app.repositories.auth_repository import AuthRepository
from app.repositories.user_repository import UserRepository
from app.schemas.auth import LoginRequest, TokenResponse
from app.services.login_throttle import LoginThrottle, bucket_key


class InvalidCredentialsError(Exception):
    """Email inexistente, contraseña incorrecta o cuenta inhabilitada: mismo error."""


class SessionLimitError(Exception):
    """El usuario ya tiene el máximo de sesiones activas."""


class InvalidRefreshTokenError(Exception):
    """Refresh inexistente, consumido, o de una sesión que ya no es válida."""


class InvalidAccessTokenError(Exception):
    """Access token con firma/vencimiento inválido, o de una sesión o usuario inhabilitados."""


def user_can_login(user: User) -> bool:
    return user.is_active and user.deleted_at is None


def session_is_usable(auth_session: AuthSession, now: datetime) -> bool:
    return (
        auth_session.is_active
        and auth_session.deleted_at is None
        and auth_session.revoked_at is None
        and auth_session.expires_at > now
    )


class AuthService:
    def __init__(self, session: Session):
        self.session = session
        self.repository = AuthRepository(session)
        self.users = UserRepository(session)

    def login(self, data: LoginRequest, ip: str, user_agent: str) -> TokenResponse:
        email = str(data.email).strip().lower()  # Misma normalización que el registro.
        throttle = LoginThrottle(self.session)
        throttle_key = bucket_key(email, ip)
        now = utcnow()

        # 1. Lectura corta: si email + IP está bloqueado se responde 429 sin
        #    verificar la contraseña. La verificación de Argon2 (lenta) queda
        #    fuera de la transacción que bloquea filas.
        with self.session.begin():
            throttle.check(throttle_key, now)
            user = self.users.get_user_by_email(email)

        # 2. Siempre se verifica un hash, exista o no el email: mismo tiempo de respuesta.
        stored_hash = user.password_hash if user is not None else DUMMY_PASSWORD_HASH
        with step("verificar contraseña"):
            password_ok = verify_password(data.password.get_secret_value(), stored_hash)
        if user is None or not password_ok or not user_can_login(user):
            # Se cuenta igual si el email no existe: el bloqueo no revela qué cuentas existen.
            throttle.record_failure(throttle_key, now)
            raise InvalidCredentialsError()

        with step("crear sesión"), self.session.begin():
            # 3. Bloquea al usuario y vuelve a comprobarlo: pudo cambiar tras la lectura.
            user = self.repository.lock_user(user.id)
            if user is None or not user_can_login(user):
                raise InvalidCredentialsError()

            limit = user.max_sessions or settings.MAX_SESSIONS
            if self.repository.count_active_sessions(user.id, now) >= limit:
                raise SessionLimitError()

            # 4. Sesión absoluta: vence a las SESSION_HOURS del login, sin extenderse.
            auth_session = self.repository.add(
                AuthSession(
                    user_id=user.id,
                    expires_at=now + timedelta(hours=settings.SESSION_HOURS),
                    revoked_at=None,
                    initial_ip=ip[:64],
                    last_ip=ip[:64],
                    # Declarado por el navegador: sirve para mostrarlo, no para autorizar.
                    client_description=user_agent[:256],
                    last_seen_at=now,
                    **self._audit(user.id, now),
                )
            )
            refresh_token = self._issue_refresh_token(auth_session, now)
            self._history("session.created", auth_session, now, {}, {"is_active": True})
            # Login correcto: el contador de fallos de esta combinación vuelve a cero.
            throttle.reset(throttle_key, now)

        set_actor(user.id)  # Credenciales ya verificadas: el log registra quién entró.
        access_token, expires_in = create_access_token(
            user.id, auth_session.id, now, auth_session.expires_at
        )
        return TokenResponse(
            access_token=access_token,
            expires_in=expires_in,
            refresh_token=refresh_token,
        )

    def refresh(self, token: str, ip: str) -> TokenResponse:
        now = utcnow()
        reused = False

        with self.session.begin():
            stored = self.repository.lock_refresh_token(hash_refresh_token(token))
            if stored is None:
                raise InvalidRefreshTokenError()

            auth_session = self.repository.lock_session(stored.session_id)
            if auth_session is None or not session_is_usable(auth_session, now):
                raise InvalidRefreshTokenError()

            if stored.consumed_at is not None:
                # Reutilización: alguien más tiene una copia del refresh.
                # Se revoca la sesión completa. No se lanza la excepción aquí
                # dentro porque revertiría la revocación; se lanza al salir.
                self._revoke(auth_session, now, reason="refresh_reused")
                reused = True
            else:
                user = self.session.get(User, auth_session.user_id)
                if user is None or not user_can_login(user):
                    raise InvalidRefreshTokenError()

                # Rotación: el refresh usado queda consumido y se entrega otro.
                stored.consumed_at = now
                stored.updated_at = now
                stored.updated_by = auth_session.user_id
                new_token = self._issue_refresh_token(auth_session, now)

                # Actividad operativa: no genera evento de historial.
                auth_session.last_seen_at = now
                auth_session.last_ip = ip[:64]
                auth_session.updated_at = now
                auth_session.updated_by = auth_session.user_id

        if reused:
            raise InvalidRefreshTokenError()

        access_token, expires_in = create_access_token(
            auth_session.user_id, auth_session.id, now, auth_session.expires_at
        )
        return TokenResponse(
            access_token=access_token,
            expires_in=expires_in,
            refresh_token=new_token,
        )

    def logout(self, token: str) -> None:
        """Revoca la sesión del refresh. No falla si el token no es válido:
        el resultado para el cliente es el mismo, la sesión no sirve."""
        now = utcnow()
        with self.session.begin():
            stored = self.repository.lock_refresh_token(hash_refresh_token(token))
            # Un refresh ya consumido no permite cerrar la sesión: evita que una
            # copia antigua robada sirva para desconectar al usuario.
            if stored is None or stored.consumed_at is not None:
                return
            auth_session = self.repository.lock_session(stored.session_id)
            if auth_session is not None and session_is_usable(auth_session, now):
                self._revoke(auth_session, now, reason="logout")

    def authenticate(self, token: str) -> tuple[User, AuthSession]:
        """Valida un access token para una ruta protegida.

        La firma y el vencimiento no bastan: también se consulta la base, así
        un logout, una revocación o la baja del usuario se aplican de inmediato,
        sin esperar a que el token venza.
        """
        try:
            claims = decode_access_token(token)
        except InvalidTokenError as exc:
            raise InvalidAccessTokenError() from exc

        now = utcnow()
        # Transacción corta de solo lectura: al terminar, la sesión ORM queda
        # libre para que la ruta abra su propia transacción con begin().
        with self.session.begin():
            auth_session = self.session.get(AuthSession, claims["sid"])
            user = self.session.get(User, claims["sub"])

        if (
            auth_session is None
            or auth_session.user_id != claims["sub"]
            or not session_is_usable(auth_session, now)
            or user is None
            or not user_can_login(user)
        ):
            raise InvalidAccessTokenError()
        return user, auth_session

    def _issue_refresh_token(self, auth_session: AuthSession, now: datetime) -> str:
        """Crea el registro con el hash y devuelve el token en claro, que solo
        conoce el cliente. Vale mientras su sesión sea válida."""
        token, token_hash = new_refresh_token()
        self.repository.add(
            RefreshToken(
                session_id=auth_session.id,
                token_hash=token_hash,
                consumed_at=None,
                **self._audit(auth_session.user_id, now),
            )
        )
        return token

    # --- Gestión de sesiones (usuario sobre las suyas, master admin sobre otras)

    def list_sessions(self, user_id: str) -> list[AuthSession]:
        """Sesiones vigentes del usuario: las que cuentan para su límite."""
        with self.session.begin():
            return self.repository.list_active_sessions(user_id, utcnow())

    def revoke_own_session(self, user_id: str, session_id: str) -> bool:
        """Cierra una sesión propia. False si no existe, no es suya o ya no vale."""
        now = utcnow()
        with self.session.begin():
            auth_session = self.repository.lock_session(session_id)
            if (
                auth_session is None
                or auth_session.user_id != user_id
                or not session_is_usable(auth_session, now)
            ):
                return False
            self._revoke(auth_session, now, reason="user_revoked")
            return True

    def revoke_user_sessions(
        self, user_id: str, actor_id: str, reason: str, except_session_id: str | None = None
    ) -> int:
        """Cierra todas las sesiones vigentes de un usuario, salvo la indicada.

        Lo usan "cerrar las demás" (actor = el propio usuario) y el master admin
        (actor = el admin). Devuelve cuántas se cerraron.
        """
        with self.session.begin():
            return self.revoke_sessions_in_transaction(
                user_id, actor_id, reason, utcnow(), except_session_id
            )

    def revoke_sessions_in_transaction(
        self,
        user_id: str,
        actor_id: str,
        reason: str,
        now: datetime,
        except_session_id: str | None = None,
    ) -> int:
        """Igual que revoke_user_sessions, pero dentro de una transacción ya
        abierta por quien llama (por ejemplo, junto con el cambio de contraseña)."""
        count = 0
        for auth_session in self.repository.list_active_sessions(user_id, now, lock=True):
            if auth_session.id == except_session_id:
                continue
            self._revoke(auth_session, now, reason=reason, actor_id=actor_id)
            count += 1
        return count

    def _revoke(
        self,
        auth_session: AuthSession,
        now: datetime,
        reason: str,
        actor_id: str | None = None,
    ) -> None:
        # Por defecto el actor es el dueño: la operación llegó con su credencial.
        # El master admin se registra como actor cuando cierra sesiones ajenas.
        actor = actor_id or auth_session.user_id
        auth_session.revoked_at = now
        auth_session.updated_at = now
        auth_session.updated_by = actor
        self._history(
            "session.revoked",
            auth_session,
            now,
            {"revoked_at": None},
            {"revoked_at": now.isoformat(), "reason": reason},
            actor_id=actor,
        )

    def _history(
        self,
        action: str,
        auth_session: AuthSession,
        now: datetime,
        before: dict,
        after: dict,
        actor_id: str | None = None,
    ) -> None:
        # Sin tokens ni hashes en el historial.
        self.repository.add_history(
            ChangeHistory(
                action=action,
                resource_id=auth_session.id,
                company_id=None,
                before=before,
                after=after,
                **self._audit(actor_id or auth_session.user_id, now),
            )
        )

    @staticmethod
    def _audit(actor_id: str, now: datetime) -> dict:
        """Campos comunes de un alta hecha por el usuario de la sesión."""
        return {
            "created_at": now,
            "updated_at": now,
            "created_by": actor_id,
            "updated_by": actor_id,
            "is_active": True,
        }
