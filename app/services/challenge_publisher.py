
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.entities import Challenge, ChallengeWord, WordTranslation


SUPPORTED_LANGUAGES = {"en", "hi", "kn", "te", "mr"}


class ChallengePublishError(Exception):
    pass


def publish_challenge(db: Session, challenge_id: UUID, publish_date: date) -> None:
    app_timezone = ZoneInfo(settings.timezone)

    try:
        # Lock the challenge row so concurrent publishing attempts serialize.
        challenge = db.scalar(
            select(Challenge)
            .where(Challenge.id == challenge_id)
            .with_for_update()
        )

        if challenge is None:
            raise ChallengePublishError("Challenge not found.")

        if challenge.status != "draft":
            raise ChallengePublishError(
                f"Only drafts can be published; current status is {challenge.status}."
            )

        words = list(
            db.scalars(
                select(ChallengeWord)
                .where(ChallengeWord.challenge_id == challenge.id)
                .order_by(ChallengeWord.position)
            )
        )

        if len(words) != 3 or [word.position for word in words] != [1, 2, 3]:
            raise ChallengePublishError(
                "Challenge must have exactly three words in positions 1, 2, and 3."
            )

        seen_words = [word.english_word.strip().casefold() for word in words]
        if len(set(seen_words)) != 3:
            raise ChallengePublishError(
                "The three required English words must be distinct."
            )

        for word in words:
            translations = list(
                db.scalars(
                    select(WordTranslation).where(
                        WordTranslation.challenge_word_id == word.id
                    )
                )
            )

            codes = {translation.language_code for translation in translations}

            if codes != SUPPORTED_LANGUAGES:
                raise ChallengePublishError(
                    f"Word '{word.english_word}' must have exactly one translation "
                    "for each supported language."
                )

            if any(not item.translated_word.strip() for item in translations):
                raise ChallengePublishError(
                    f"Word '{word.english_word}' has an empty translation."
                )

        # Do not allow a second challenge to be published for this date.
        existing = db.scalar(
            select(Challenge)
            .where(
                Challenge.publish_date == publish_date,
                Challenge.status == "published",
                Challenge.id != challenge.id,
            )
            .with_for_update()
        )

        if existing is not None:
            raise ChallengePublishError(
                f"A challenge is already published for {publish_date}."
            )

        challenge.publish_date = publish_date
        challenge.status = "published"
        challenge.published_at = datetime.now(app_timezone).astimezone(
            timezone.utc
        )

        db.commit()

    except Exception:
        db.rollback()
        raise
