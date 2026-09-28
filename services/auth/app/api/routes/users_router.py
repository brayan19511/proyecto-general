from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.api.dependencies import ip_rate_limit
from app.core.db.connection import get_db

from app.schemas.user import UserCreate, UserResponse
from app.services.user_service import EmailAlreadyExistsError, UserService

router = APIRouter(prefix="/users", tags=["users"])


@router.post(
    "",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="registerUser",
    dependencies=[Depends(ip_rate_limit("register", "REGISTER_IP_LIMIT", "REGISTER_IP_WINDOW_MINUTES"))],
)
def register_user(data: UserCreate, db: Session = Depends(get_db)):
    try:
        return UserService(db).register_user(data)
    except EmailAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="El correo ya está registrado.",
        ) from exc
