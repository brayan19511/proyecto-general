"""Access tokens (JWT RS256) y refresh tokens (valores aleatorios opacos).

- Access token: JWT firmado con la clave privada. Identifica usuario (sub) y
  sesión (sid). No incluye empresa, puestos ni roles: esos datos cambian y se
  consultan en la base en cada solicitud.
- Refresh token: secreto aleatorio sin estructura. Solo se guarda su hash.
"""

import hashlib
import secrets
from datetime import datetime, timedelta
from functools import lru_cache

import jwt

from app.core.config import settings

ALGORITHM = "RS256"


class InvalidTokenError(Exception):
    """El access token no es válido: firma, emisor, audiencia o vencimiento."""


@lru_cache
def _private_key() -> bytes:
    # Se lee una vez por proceso; lru_cache guarda el resultado.
    return settings.JWT_PRIVATE_KEY_FILE.read_bytes()


@lru_cache
def _public_key() -> bytes:
    return settings.JWT_PUBLIC_KEY_FILE.read_bytes()


def create_access_token(
    user_id: str,
    session_id: str,
    now: datetime,
    session_expires_at: datetime,
) -> tuple[str, int]:
    """Devuelve el token y sus segundos de vida.

    Vence a los ACCESS_TOKEN_MINUTES o al terminar la sesión, lo que ocurra
    primero: un access token nunca sobrevive a su sesión.
    """
    expires_at = min(
        now + timedelta(minutes=settings.ACCESS_TOKEN_MINUTES),
        session_expires_at,
    )
    payload = {
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
        "sub": user_id,
        "sid": session_id,
        "iat": now,
        "exp": expires_at,
    }
    token = jwt.encode(payload, _private_key(), algorithm=ALGORITHM)
    return token, int((expires_at - now).total_seconds())


def decode_access_token(token: str) -> dict:
    """Verifica firma, iss, aud y exp. No comprueba si la sesión sigue activa:
    eso lo hace quien use el token consultando la base."""
    try:
        return jwt.decode(
            token,
            _public_key(),
            # Lista fija: impide que un token diga "alg": "none" u otro algoritmo.
            algorithms=[ALGORITHM],
            audience=settings.JWT_AUDIENCE,
            issuer=settings.JWT_ISSUER,
            options={"require": ["exp", "iat", "sub", "sid"]},
        )
    except jwt.PyJWTError as exc:
        raise InvalidTokenError("Token inválido.") from exc


def new_refresh_token() -> tuple[str, str]:
    """Devuelve (token para el cliente, hash para la base)."""
    token = secrets.token_urlsafe(32)  # 256 bits aleatorios.
    return token, hash_refresh_token(token)


def hash_refresh_token(token: str) -> str:
    """SHA-256 en hexadecimal: 64 caracteres, igual que refresh_tokens.token_hash.

    No se usa Argon2 como en las contraseñas: el token ya es aleatorio y
    largo, no se puede adivinar por fuerza bruta, y necesitamos buscarlo por
    su hash (Argon2 usa sal y daría un resultado distinto cada vez).
    """
    return hashlib.sha256(token.encode()).hexdigest()
