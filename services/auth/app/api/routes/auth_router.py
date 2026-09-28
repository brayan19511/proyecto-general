from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import ip_rate_limit
from app.core.client_ip import client_ip
from app.core.db.connection import get_db
from app.schemas.auth import LoginRequest, RefreshRequest, TokenResponse
from app.services.auth_service import (
    AuthService,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    SessionLimitError,
)
from app.services.login_throttle import LoginBlockedError

# Sin prefijo propio: main.py monta todo el servicio bajo /auth (quedan /auth/login...).
router = APIRouter(tags=["auth"])


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    operation_id="login",
    # Volumen por IP; aparte está el bloqueo por contraseñas fallidas (email + IP).
    dependencies=[Depends(ip_rate_limit("login", "LOGIN_IP_LIMIT", "LOGIN_IP_WINDOW_MINUTES"))],
)
def login(data: LoginRequest, request: Request, db: Session = Depends(get_db)):
    try:
        return AuthService(db).login(
            data,
            ip=client_ip(request),
            user_agent=request.headers.get("user-agent", ""),
        )
    except LoginBlockedError as exc:
        # 429 + Retry-After: el cliente sabe cuántos segundos esperar.
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Demasiados intentos fallidos. Intenta más tarde.",
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc
    except InvalidCredentialsError as exc:
        # Mismo mensaje para email inexistente, contraseña incorrecta o cuenta inhabilitada.
        raise _unauthorized("Credenciales inválidas.") from exc
    except SessionLimitError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Se alcanzó el máximo de sesiones activas. Cierra una sesión.",
        ) from exc


@router.post(
    "/refresh",
    response_model=TokenResponse,
    operation_id="refreshToken",
    dependencies=[Depends(ip_rate_limit("refresh", "REFRESH_IP_LIMIT", "REFRESH_IP_WINDOW_MINUTES"))],
)
def refresh(data: RefreshRequest, request: Request, db: Session = Depends(get_db)):
    try:
        return AuthService(db).refresh(data.refresh_token, ip=client_ip(request))
    except InvalidRefreshTokenError as exc:
        raise _unauthorized("Refresh token inválido. Inicia sesión nuevamente.") from exc


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    operation_id="logout",
)
def logout(data: RefreshRequest, db: Session = Depends(get_db)):
    # Responde 204 siempre: no revela si el token era válido.
    AuthService(db).logout(data.refresh_token)
