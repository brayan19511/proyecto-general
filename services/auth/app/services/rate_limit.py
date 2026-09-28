"""Límite de volumen por IP con ventana fija, compartido entre réplicas.

Cuenta todas las solicitudes a una operación (registro, login, refresh) desde
una IP. Es distinto del bloqueo por contraseñas fallidas (login_throttle.py):
este frena avalanchas; aquel, adivinar la contraseña de una cuenta.

Espacio de nombres propio ("auth:ip:..."): la API central tendrá sus límites
con otras claves, así una misma solicitud no se cuenta dos veces en el mismo
contador. Estado operativo en rate_buckets: sin historial de negocio y con
actor NULL (la solicitud aún no tiene identidad validada).
"""

import hashlib
from datetime import datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.entities import RateBucket
from app.repositories.auth_repository import AuthRepository


class RateLimitExceededError(Exception):
    def __init__(self, retry_after_seconds: int):
        super().__init__()
        self.retry_after_seconds = retry_after_seconds


def ip_key(operation: str, ip: str) -> str:
    # 8 + operación + 1 + 64. La IP se guarda como hash, no en claro.
    return f"auth:ip:{operation}:{hashlib.sha256(ip.encode()).hexdigest()}"


def hit(session: Session, key: str, limit: int, window_minutes: int, now: datetime) -> None:
    """Cuenta una solicitud en su propia transacción; 429 si ya se alcanzó el límite."""
    window = timedelta(minutes=window_minutes)
    repository = AuthRepository(session)
    for attempt in range(2):
        try:
            with session.begin():
                bucket = repository.lock_bucket(key)
                if bucket is None:
                    bucket = repository.add(
                        RateBucket(
                            key=key,
                            count=0,
                            window_start=now,
                            blocked_until=None,
                            created_at=now,
                            updated_at=now,
                            created_by=None,  # Solicitud anónima.
                            updated_by=None,
                            is_active=True,
                        )
                    )
                elif bucket.window_start + window <= now:
                    bucket.count = 0  # Ventana vencida: empieza otra.
                    bucket.window_start = now

                if bucket.count >= limit:
                    retry = int((bucket.window_start + window - now).total_seconds()) + 1
                    raise RateLimitExceededError(retry_after_seconds=retry)

                bucket.count += 1
                bucket.updated_at = now
            return
        except IntegrityError:
            # Carrera al crear el contador: se reintenta una vez, ya existirá.
            if attempt == 1:
                raise
