from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.entities import AuthSession, ChangeHistory, RateBucket, RefreshToken, User


class AuthRepository:
    """Consultas de login y sesiones.

    Los métodos lock_* usan SELECT ... FOR UPDATE: bloquean la fila hasta que
    termine la transacción, y populate_existing hace que se relea de la base
    aunque SQLAlchemy ya tenga el objeto en memoria.
    """

    def __init__(self, session: Session):
        self.session = session

    def lock_user(self, user_id: str) -> User | None:
        """Dos logins simultáneos del mismo usuario esperan uno al otro aquí,
        así ninguno cuenta sesiones mientras el otro crea la suya."""
        return self.session.scalar(
            select(User)
            .where(User.id == user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    def count_active_sessions(self, user_id: str, now: datetime) -> int:
        """Sesiones que cuentan para el límite: activas, sin baja, sin revocar y vigentes."""
        return self.session.scalar(
            select(func.count())
            .select_from(AuthSession)
            .where(
                AuthSession.user_id == user_id,
                AuthSession.is_active.is_(True),
                AuthSession.deleted_at.is_(None),
                AuthSession.revoked_at.is_(None),
                AuthSession.expires_at > now,
            )
        )

    def list_active_sessions(
        self, user_id: str, now: datetime, lock: bool = False
    ) -> list[AuthSession]:
        """Sesiones vigentes del usuario, la más reciente primero.
        lock=True las bloquea para revocarlas sin carreras."""
        statement = (
            select(AuthSession)
            .where(
                AuthSession.user_id == user_id,
                AuthSession.is_active.is_(True),
                AuthSession.deleted_at.is_(None),
                AuthSession.revoked_at.is_(None),
                AuthSession.expires_at > now,
            )
            .order_by(AuthSession.created_at.desc())
        )
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return list(self.session.scalars(statement))

    def lock_refresh_token(self, token_hash: str) -> RefreshToken | None:
        """Dos renovaciones con el mismo token no pueden consumirlo a la vez:
        la segunda espera y luego ve que ya fue consumido."""
        return self.session.scalar(
            select(RefreshToken)
            .where(RefreshToken.token_hash == token_hash)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    def lock_session(self, session_id: str) -> AuthSession | None:
        return self.session.scalar(
            select(AuthSession)
            .where(AuthSession.id == session_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    def get_bucket(self, key: str) -> RateBucket | None:
        return self.session.scalar(select(RateBucket).where(RateBucket.key == key))

    def lock_bucket(self, key: str) -> RateBucket | None:
        """Bloquea el contador: dos fallos simultáneos no pierden un incremento."""
        return self.session.scalar(
            select(RateBucket)
            .where(RateBucket.key == key)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    def add(self, entity):
        """Añade una entidad preparada por el service; el flush genera su id."""
        self.session.add(entity)
        self.session.flush()
        return entity

    def add_history(self, event: ChangeHistory) -> None:
        self.session.add(event)
