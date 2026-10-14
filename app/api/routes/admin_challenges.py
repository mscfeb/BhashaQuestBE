
from datetime import date
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.services.challenge_generator import (
    ChallengeGenerationError,
    generate_challenge,
)
from app.services.challenge_persistence import save_challenge_draft


router = APIRouter(
    prefix="/api/admin/challenges",
    tags=["Admin - Challenges"],
)


class GenerateChallengeRequest(BaseModel):
    topic_hint: str | None = Field(
        default=None,
        min_length=2,
        max_length=100,
    )
    difficulty: str = "beginner"
    publish_date: date | None = None


@router.post("/generate")
def generate_challenge_draft(
    request: GenerateChallengeRequest,
    db: Session = Depends(get_db),
):
    # This endpoint is for local development only.
    # Add real admin authentication before production.
    if settings.app_env != "development":
        raise HTTPException(
            status_code=403,
            detail="Draft generation endpoint is disabled outside development.",
        )

    if request.difficulty not in {
        "beginner",
        "intermediate",
        "advanced",
    }:
        raise HTTPException(
            status_code=422,
            detail="Unsupported difficulty.",
        )

    try:
        draft = generate_challenge(
            topic_hint=request.topic_hint,
            difficulty=request.difficulty,
        )

        challenge_id = save_challenge_draft(
            db=db,
            draft=draft,
            concept_key=f"generated-{uuid4()}",
            publish_date=request.publish_date,
        )

        return {
            "challengeId": str(challenge_id),
            "topic": draft.topic,
            "difficulty": draft.difficulty,
            "words": [
                word.english_word for word in draft.words
            ],
            "status": "draft",
            "publishDate": (
                request.publish_date.isoformat()
                if request.publish_date
                else None
            ),
        }

    except ChallengeGenerationError as exc:
        raise HTTPException(
            status_code=503,
            detail="Challenge generation failed. Please try again.",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc
