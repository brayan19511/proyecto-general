"""Bloqueo de login tras contraseñas fallidas, por email + IP.

Por qué en auth y no en el API gateway: el gateway solo ve IPs y volumen de
solicitudes; no sabe si una contraseña fue incorrecta. Además auth debe
protegerse aunque alguien llegue sin pasar por el gateway.

Por qué email + IP y no solo email: con solo email, cualquiera podría fallar 5
veces a propósito y dejar sin acceso a otra persona. Con la combinación, un
atacante solo se bloquea a sí mismo desde su IP. El gateway limitará además el
volumen total por IP (otra capa, otro contador).

Contador en rate_buckets (tabla, no memoria): todas las réplicas del servicio
comparten el mismo conteo. Es estado operativo, no historial de negocio: no
genera eventos en change_history.

Atribución: created_by/updated_by quedan en NULL. La solicitud es anónima
(todavía no hay identidad validada) y no se inventa un usuario para ella.
"""

import hashlib
from datetime import datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.entities import RateBucket
from app.repositories.auth_repository import AuthRepository


class LoginBlockedError(Exception):
    """Demasiados fallos: la combinación email + IP está bloqueada."""

    def __init__(self, retry_after_seconds: int):
        super().__init__()
        self.retry_after_seconds = retry_after_seconds


def bucket_key(email: str, ip: str) -> str:
    """Clave del contador. El email no se guarda en claro: solo el hash de
    email + IP. No es anonimización fuerte (se puede probar por diccionario),
    pero evita tener correos legibles en una tabla operativa."""
    digest = hashlib.sha256(f"{email}|{ip}".encode()).hexdigest()
    return f"login_fail:{digest}"  # 11 + 64 = 75 caracteres (columna de 100).


class LoginThrottle:
    def __init__(self, session: Session):
        self.session = session
        self.repository = AuthRepository(session)

    def check(self, key: str, now: datetime) -> None:
        """Se llama dentro de una transacción, antes de verificar la contraseña:
        durante el bloqueo ni siquiera se prueba (tampoco la correcta)."""
        bucket = self.repository.get_bucket(key)
        if bucket is not None and bucket.blocked_until is not None and bucket.blocked_until > now:
            seconds = int((bucket.blocked_until - now).total_seconds()) + 1
            raise LoginBlockedError(retry_after_seconds=seconds)

    def record_failure(self, key: str, now: datetime) -> None:
        """Cuenta un fallo en su propia transacción: debe quedar guardado aunque
        el login termine en error."""
        for attempt in range(2):
            try:
                with self.session.begin():
                    self._increment(key, now)
                return
            except IntegrityError:
                # Carrera: otra solicitud creó el contador a la vez. Se reintenta
                # una vez; ahora existirá y se bloqueará para incrementarlo.
                if attempt == 1:
                    raise

    def reset(self, key: str, now: datetime) -> None:
        """Login correcto: vuelve a cero. Se llama dentro de la transacción del login."""
        bucket = self.repository.lock_bucket(key)
        if bucket is not None and (bucket.count or bucket.blocked_until is not None):
            bucket.count = 0
            bucket.blocked_until = None
            bucket.window_start = now
            bucket.updated_at = now

    def _increment(self, key: str, now: datetime) -> None:
        window = timedelta(minutes=settings.LOGIN_WINDOW_MINUTES)
        bucket = self.repository.lock_bucket(key)
        if bucket is None:
            bucket = self.repository.add(
                RateBucket(
                    key=key,
                    count=0,
                    window_start=now,
                    blocked_until=None,
                    created_at=now,
                    updated_at=now,
                    created_by=None,  # Solicitud anónima (ver docstring del módulo).
                    updated_by=None,
                    is_active=True,
                )
            )
        elif bucket.window_start + window <= now:
            # La ventana anterior venció: se empieza a contar de nuevo.
            bucket.count = 0
            bucket.window_start = now
            bucket.blocked_until = None

        bucket.count += 1
        bucket.updated_at = now
        if bucket.count >= settings.LOGIN_MAX_FAILURES:
            bucket.blocked_until = now + timedelta(minutes=settings.LOGIN_BLOCK_MINUTES)
