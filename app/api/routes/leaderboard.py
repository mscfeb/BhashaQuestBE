
from datetime import datetime, timedelta, timezone
from typing import Literal
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
    prefix="/api/leaderboard",
    tags=["leaderboard"],
)


@router.get("")
def get_leaderboard(
    user_id: UUID = Query(...),
    period: Literal["weekly", "all-time"] = "weekly",
    limit: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    # Development-only identity lookup.
    current_user = db.get(User, user_id)
    if current_user is None:
        raise HTTPException(status_code=404, detail="User not found.")

    query = (
        select(
            UserChallengeProgress.user_id.label("user_id"),
            func.coalesce(
                func.sum(UserChallengeProgress.xp_earned), 0
            ).label("total_xp"),
        )
        .join(
            Challenge,
            Challenge.id == UserChallengeProgress.challenge_id,
        )
        .where(UserChallengeProgress.xp_earned > 0)
        .group_by(UserChallengeProgress.user_id)
    )

    if period == "weekly":
        # Rolling seven-day window, using challenge publication dates.
        today = datetime.now(timezone.utc).date()
        week_start = today - timedelta(days=6)

        query = query.where(
            Challenge.publish_date >= week_start,
            Challenge.publish_date <= today,
        )

    xp_rows = db.execute(query).all()
    xp_by_user = {
        row.user_id: int(row.total_xp or 0)
        for row in xp_rows
    }

    users = db.scalars(
        select(User).order_by(User.id)
    ).all()

    ranked = [
        {
            "userId": str(user.id),
            "username": user.display_name or "Learner",
            "totalXp": xp_by_user.get(user.id, 0),
        }
        for user in users
    ]

    # Deterministic ordering for users tied on XP.
    ranked.sort(
        key=lambda item: (
            -item["totalXp"],
            item["username"].casefold(),
            item["userId"],
        )
    )

    previous_xp = None
    rank = 0

    for position, player in enumerate(ranked, start=1):
        if player["totalXp"] != previous_xp:
            rank = position
            previous_xp = player["totalXp"]

        player["rank"] = rank

    me = next(
        player
        for player in ranked
        if player["userId"] == str(user_id)
    )

    return {
        "period": period,
        "currentUser": {
            "rank": me["rank"],
            "totalXp": me["totalXp"],
        },
        "leaders": ranked[:limit],
    }
