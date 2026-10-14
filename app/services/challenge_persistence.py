
from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import (
    Challenge,
    ChallengeWord,
    WordTranslation,
)
from app.services.challenge_generator import ChallengeDraft


def save_challenge_draft(
    db: Session,
    draft: ChallengeDraft,
    concept_key: str,
    publish_date: date | None = None,
) -> UUID:
    """
    Persist a validated challenge and its translations atomically.
    The challenge remains a draft until explicitly published.
    """
    try:
        existing = db.scalar(
            select(Challenge).where(
                Challenge.concept_key == concept_key,
                Challenge.publish_date == publish_date,
            )
        )

        if existing is not None:
            raise ValueError(
                "A challenge already exists for this concept and date."
            )

        challenge = Challenge(
            concept_key=concept_key,
            topic=draft.topic,
            difficulty=draft.difficulty,
            status="draft",
            publish_date=publish_date,
        )
        db.add(challenge)
        db.flush()

        for position, word_draft in enumerate(draft.words, start=1):
            challenge_word = ChallengeWord(
                challenge_id=challenge.id,
                position=position,
                english_word=word_draft.english_word,
                english_meaning=word_draft.english_meaning,
            )
            db.add(challenge_word)
            db.flush()

            for language_code in ("en", "hi", "kn", "te", "mr"):
                translation_draft = getattr(
                    word_draft.translations,
                    language_code,
                )

                db.add(
                    WordTranslation(
                        challenge_word_id=challenge_word.id,
                        language_code=language_code,
                        translated_word=translation_draft.translated_word,
                        transliteration=translation_draft.transliteration,
                        meaning_note=translation_draft.meaning_note,
                    )
                )

        db.commit()
        return challenge.id

    except Exception:
        db.rollback()
        raise
