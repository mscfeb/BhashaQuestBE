
from datetime import date, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

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


@router.get("/history")
def get_progress_history(
    user_id: UUID = Query(...),
    days: int = Query(default=7, ge=7, le=90),
    db: Session = Depends(get_db),
):
    if db.get(User, user_id) is None:
        raise HTTPException(status_code=404, detail="User not found.")

    today = date.today()
    start_date = today - timedelta(days=days - 1)

    rows = db.execute(
        select(
            Challenge.publish_date.label("day"),
            func.sum(
                UserChallengeProgress.xp_earned
            ).label("xp"),
            func.count(
                UserChallengeProgress.id
            ).label("challenges_completed"),
        )
        .join(
            Challenge,
            Challenge.id == UserChallengeProgress.challenge_id,
        )
        .where(
            UserChallengeProgress.user_id == user_id,
            UserChallengeProgress.completed.is_(True),
            UserChallengeProgress.xp_earned > 0,
            Challenge.publish_date >= start_date,
            Challenge.publish_date <= today,
        )
        .group_by(Challenge.publish_date)
        .order_by(Challenge.publish_date)
    ).all()

    by_date = {
        row.day.isoformat(): {
            "xp": int(row.xp or 0),
            "challengesCompleted": int(
                row.challenges_completed or 0
            ),
        }
        for row in rows
        if row.day is not None
    }

    history = []

    for offset in range(days):
        day = start_date + timedelta(days=offset)
        item = by_date.get(
            day.isoformat(),
            {"xp": 0, "challengesCompleted": 0},
        )

        history.append({
            "date": day.isoformat(),
            "label": day.strftime("%a"),
            **item,
        })

    return {
        "days": days,
        "periodXp": sum(item["xp"] for item in history),
        "challengesCompleted": sum(
            item["challengesCompleted"] for item in history
        ),
        "history": history,
    }
