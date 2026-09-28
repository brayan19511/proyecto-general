from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser, get_company_context, get_current_user
from app.core.client_ip import client_ip
from app.core.db.connection import get_db
from app.schemas.me import (
    CompanyOut,
    CompanyPermissionsResponse,
    MeResponse,
    PermissionGrantOut,
    RevokedSessionsOut,
    SessionDetailOut,
)
from app.services.access_service import CompanyContext
from app.services.auth_service import AuthService
from app.schemas.user import PasswordChange
from app.services.login_throttle import LoginBlockedError
from app.services.password_service import PasswordService, SamePasswordError, WrongCurrentPasswordError
from app.services.user_service import UserService

# Identidad, permisos, sesiones y contraseña propios. El perfil y los documentos
# están en profile_router.py (también bajo /me).
router = APIRouter(prefix="/me", tags=["me"])


@router.get("", response_model=MeResponse, operation_id="getMe")
def get_me(
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # No recibe empresa: devuelve todas las membresías activas del usuario.
    # La empresa activa se elige por solicitud con el header X-Company-Id.
    return UserService(db).get_me(current.user, current.session)


@router.get(
    "/permissions",
    response_model=CompanyPermissionsResponse,
    operation_id="getMyPermissions",
)
def get_my_permissions(ctx: CompanyContext = Depends(get_company_context)):
    # El contexto ya calculó los permisos; aquí solo se presentan.
    return CompanyPermissionsResponse(
        company=CompanyOut(id=ctx.company.id, code=ctx.company.code, name=ctx.company.name),
        is_platform_admin=ctx.is_platform_admin,
        permissions=[
            PermissionGrantOut(
                code=code,
                company=grant.company,
                area_ids=sorted(grant.area_ids),
                own=grant.own,
            )
            for code, grant in sorted(ctx.grants.items())
        ],
    )


# --- Sesiones propias: el usuario ve y cierra las suyas, sin permisos extra.


@router.get("/sessions", response_model=list[SessionDetailOut], operation_id="listMySessions")
def list_my_sessions(
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return [
        SessionDetailOut(
            id=s.id,
            created_at=s.created_at,
            expires_at=s.expires_at,
            last_seen_at=s.last_seen_at,
            initial_ip=s.initial_ip,
            last_ip=s.last_ip,
            client_description=s.client_description,
            current=s.id == current.session.id,
        )
        for s in AuthService(db).list_sessions(current.user.id)
    ]


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    operation_id="revokeMySession",
)
def revoke_my_session(
    session_id: str,
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Puede ser la actual: equivale a un logout sin el refresh token.
    if not AuthService(db).revoke_own_session(current.user.id, session_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sesión no encontrada.")


@router.post(
    "/sessions/revoke-others",
    response_model=RevokedSessionsOut,
    operation_id="revokeMyOtherSessions",
)
def revoke_my_other_sessions(
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Cierra todas las sesiones propias menos la de esta solicitud."""
    count = AuthService(db).revoke_user_sessions(
        current.user.id,
        actor_id=current.user.id,
        reason="user_revoked_others",
        except_session_id=current.session.id,
    )
    return RevokedSessionsOut(revoked=count)


@router.patch("/password", response_model=RevokedSessionsOut, operation_id="changeMyPassword")
def change_my_password(
    data: PasswordChange,
    request: Request,
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Cambia la contraseña propia y cierra las demás sesiones (devuelve cuántas)."""
    try:
        revoked = PasswordService(db).change_own(
            current.user,
            current.session.id,
            data.current_password.get_secret_value(),
            data.new_password.get_secret_value(),
            client_ip(request),
        )
    except LoginBlockedError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Demasiados intentos fallidos. Intenta más tarde.",
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc
    except WrongCurrentPasswordError as exc:
        # 403 y no 401: el token es válido; lo incorrecto es la contraseña actual.
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="La contraseña actual no es correcta.") from exc
    except SamePasswordError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="La nueva contraseña debe ser distinta de la actual.",
        ) from exc
    return RevokedSessionsOut(revoked=revoked)
