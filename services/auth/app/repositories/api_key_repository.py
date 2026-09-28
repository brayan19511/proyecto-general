from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.entities import ApiKey, ChangeHistory


class ApiKeyRepository:
    def __init__(self, session: Session):
        self.session = session

    def count_valid_for_user(self, user_id: str, now: datetime) -> int:
        """Keys que cuentan para el máximo: activas, sin revocar y vigentes,
        sumando todas las empresas del usuario."""
        return self.session.scalar(
            select(func.count())
            .select_from(ApiKey)
            .where(
                ApiKey.user_id == user_id,
                ApiKey.is_active.is_(True),
                ApiKey.deleted_at.is_(None),
                ApiKey.revoked_at.is_(None),
                or_(ApiKey.expires_at.is_(None), ApiKey.expires_at > now),
            )
        )

    def list_for_user(self, user_id: str, company_id: str) -> list[ApiKey]:
        """Keys propias en la empresa, incluidas revocadas y vencidas (para verlas)."""
        return list(
            self.session.scalars(
                select(ApiKey)
                .where(
                    ApiKey.user_id == user_id,
                    ApiKey.company_id == company_id,
                    ApiKey.deleted_at.is_(None),
                )
                .order_by(ApiKey.created_at.desc())
            )
        )

    def get_own(self, user_id: str, company_id: str, key_id: str) -> ApiKey | None:
        return self.session.scalar(
            select(ApiKey).where(
                ApiKey.id == key_id,
                ApiKey.user_id == user_id,
                ApiKey.company_id == company_id,
                ApiKey.deleted_at.is_(None),
            )
        )

    def get_by_hash(self, key_hash: str) -> ApiKey | None:
        return self.session.scalar(select(ApiKey).where(ApiKey.key_hash == key_hash))

    def add(self, entity):
        self.session.add(entity)
        self.session.flush()
        return entity

    def add_history(self, event: ChangeHistory) -> None:
        self.session.add(event)
