
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.entities import (
    Challenge,
    User,
    UserChallengeProgress,
)

router = APIRouter(
    prefix="/api/progress",
    tags=["progress"],
)


@router.get("/today")
def get_today_progress(
    user_id: UUID = Query(
        ...,
        description="Temporary development user ID; authentication will replace this.",
    ),
    db: Session = Depends(get_db),
):
    # This endpoint uses a query parameter for testing only.
    # Never allow clients to choose their own user ID in production.
    if settings.app_env.lower() != "development":
        raise HTTPException(
            status_code=403,
            detail="This development endpoint is disabled.",
        )

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=404,
            detail="User not found. Create a development user first.",
        )

    today = datetime.now(ZoneInfo(settings.timezone)).date()
    yesterday = today - timedelta(days=1)

    challenge = db.scalar(
        select(Challenge).where(
            Challenge.publish_date == today,
            Challenge.status == "published",
        )
    )

    if challenge is None:
        raise HTTPException(
            status_code=404,
            detail="No challenge has been published for today.",
        )

    progress = db.scalar(
        select(UserChallengeProgress).where(
            UserChallengeProgress.user_id == user_id,
            UserChallengeProgress.challenge_id == challenge.id,
        )
    )

    attempts_used = progress.attempts_used if progress else 0
    completed = progress.completed if progress else False
    xp_earned_today = progress.xp_earned if progress else 0

    total_xp = db.scalar(
        select(
            func.coalesce(func.sum(UserChallengeProgress.xp_earned), 0)
        ).where(
            UserChallengeProgress.user_id == user_id
        )
    )
    Best_score = db.scalar(
        select(
            func.coalesce(func.max(UserChallengeProgress.xp_earned), 0)
        ).where(
            UserChallengeProgress.user_id == user_id
        )
    )

    # Get all completed challenge dates to calculate the streak.
    completed_dates = set(
        db.scalars(
            select(Challenge.publish_date)
            .join(
                UserChallengeProgress,
                UserChallengeProgress.challenge_id == Challenge.id,
            )
            .where(
                UserChallengeProgress.user_id == user_id,
                UserChallengeProgress.completed.is_(True),
                Challenge.publish_date.is_not(None),
                Challenge.publish_date <= today,
            )
            .order_by(Challenge.publish_date.desc())
        ).all()
    )

    # A streak remains active if the last success was today or yesterday.
    if today in completed_dates:
        streak_anchor = today
    elif yesterday in completed_dates:
        streak_anchor = yesterday
    else:
        streak_anchor = None

    current_streak = 0

    if streak_anchor is not None:
        streak_date = streak_anchor

        while streak_date in completed_dates:
            current_streak += 1
            streak_date -= timedelta(days=1)

    return {
        "userId": str(user.id),
        "challengeId": str(challenge.id),
        "date": today.isoformat(),
        "attemptsUsed": attempts_used,
        "attemptsRemaining": max(0, 2 - attempts_used) if not completed else 0,
        "completed": completed,
        "xpEarnedToday": xp_earned_today,
        "totalXp": int(total_xp or 0),
        "currentStreak": current_streak,
        "bestScore": int(Best_score or 0),  
        
    }
