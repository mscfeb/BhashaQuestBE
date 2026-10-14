
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.entities import Challenge, ChallengeWord, WordTranslation

router = APIRouter(
    prefix="/api/challenges",
    tags=["challenges"],
)

SUPPORTED_LANGUAGES = {"en", "hi", "kn", "te", "mr"}


@router.get("/today")
def get_today_challenge(
    language_code: str = Query(default="en", alias="language"),
    db: Session = Depends(get_db),
):
    # Validate the requested language.
    if language_code not in SUPPORTED_LANGUAGES:
        raise HTTPException(
            status_code=400,
            detail="Unsupported language. Use en, hi, kn, te, or mr.",
        )

    # Always calculate today's date using the configured timezone.
    timezone = ZoneInfo(settings.timezone)
    today = datetime.now(timezone).date()

    # Only return a challenge that has been published for today.
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

    # Load the challenge's three required words in their defined order.
    words = db.scalars(
        select(ChallengeWord)
        .where(ChallengeWord.challenge_id == challenge.id)
        .order_by(ChallengeWord.position)
    ).all()

    if len(words) != 3:
        raise HTTPException(
            status_code=500,
            detail="The published challenge does not have exactly three words.",
        )

    word_results = []

    for word in words:
        translation = db.scalar(
            select(WordTranslation).where(
                WordTranslation.challenge_word_id == word.id,
                WordTranslation.language_code == language_code,
            )
        )

        if translation is None:
            raise HTTPException(
                status_code=500,
                detail="A required challenge translation is missing.",
            )

        word_results.append(
            {
                "position": word.position,
                "englishWord": word.english_word,
                "translatedWord": translation.translated_word,
                "transliteration": translation.transliteration,
                "englishMeaning": word.english_meaning,
                "meaningNote": translation.meaning_note,
            }
        )

    return {
        "id": str(challenge.id),
        "date": challenge.publish_date.isoformat(),
        "topic": challenge.topic,
        "difficulty": challenge.difficulty,
        "language": language_code,
        "words": word_results,
    }
