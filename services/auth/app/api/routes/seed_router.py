from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import require_seed_token
from app.core.config import settings
from app.core.db.connection import get_db
from app.schemas.seed import SeedResponse
from app.services.seed_service import SeedConflictError, SeedService

router = APIRouter(
    prefix="/seed",
    tags=["seed"],
    dependencies=[Depends(require_seed_token)],
)


@router.post("", response_model=SeedResponse, operation_id="runSeed")
def run_seed(db: Session = Depends(get_db)):
    try:
        return SeedService(db, settings).run()
    except SeedConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc