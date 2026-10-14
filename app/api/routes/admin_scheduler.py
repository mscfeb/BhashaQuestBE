
from fastapi import APIRouter, HTTPException

from app.core.config import settings
from app.services.daily_scheduler import (
    prepare_tomorrow_challenge,
    publish_today_challenge,
)

router = APIRouter(
    prefix="/api/admin/scheduler",
    tags=["Admin - Scheduler"],
)


def ensure_development():
    if settings.app_env != "development":
        raise HTTPException(
            status_code=403,
            detail="Manual scheduler controls are disabled outside development.",
        )


@router.post("/prepare-tomorrow")
def prepare_tomorrow():
    ensure_development()
    result = prepare_tomorrow_challenge()

    if result["status"] == "error":
        raise HTTPException(status_code=503, detail=result["message"])

    return result


@router.post("/publish-today")
def publish_today():
    ensure_development()
    result = publish_today_challenge()

    if result["status"] == "error":
        raise HTTPException(status_code=503, detail=result["message"])

    return result
