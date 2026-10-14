
import json
from datetime import datetime, timezone as dt_timezone 

# from app.api.routes import progress
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
)
from google import genai
from google.genai import types
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.entities import (
    Challenge,
    ChallengeWord,
    Submission,
    User,
    UserChallengeProgress,
    WordTranslation,
)

router = APIRouter(prefix="/api/submissions", tags=["submissions"])

MAX_AUDIO_BYTES = 8 * 1024 * 1024

ALLOWED_AUDIO_TYPES = {
    "audio/webm",
    "audio/ogg",
    "audio/wav",
    "audio/x-wav",
    "audio/mpeg",
    "audio/mp4",
    "audio/aac",
    "audio/flac",
    "audio/x-m4a"
}

LANGUAGES = {
    "en": "English",
    "hi": "Hindi",
    "kn": "Kannada",
    "te": "Telugu",
    "mr": "Marathi",
}


class EvaluationResult(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    language_detected: str = Field(alias="languageDetected")
    language_matches: bool = Field(alias="languageMatches")
    required_words_used: bool = Field(alias="requiredWordsUsed")
    meaningful_sentence: bool = Field(alias="meaningfulSentence")
    score: int = Field(ge=0, le=10)
    feedback: str = Field(min_length=1, max_length=1000)


def evaluate_audio(
    audio_bytes: bytes,
    mime_type: str,
    language_code: str,
    required_words: list[str],
) -> EvaluationResult:
    """Call Gemini and validate its JSON response."""

    if not settings.gemini_api_key:
        raise RuntimeError("Gemini API key is not configured.")

    language_name = LANGUAGES[language_code]

    prompt = f"""
You evaluate a language-learning speaking challenge.

Expected language: {language_name}
Required words: {json.dumps(required_words, ensure_ascii=False)}

Listen to the attached audio and return one JSON object with exactly
these fields:
{{
  "languageDetected": "name of the detected language",
  "languageMatches": true,
  "requiredWordsUsed": true,
  "meaningfulSentence": true,
  "score": 0,
  "feedback": "Short, constructive feedback"
}}

Rules:
- The speaker must speak in {language_name}.
- All three required words must be recognizably used in the spoken sentence.
- The sentence must communicate a meaningful idea.
- Do not require perfect grammar or a native accent.
- Do not penalize regional accents or normal pronunciation variation.
- If the language is wrong, any required word is missing, or the
  sentence is not meaningful, the score MUST be 0.
- Otherwise, assign an integer score from 1 to 10.
- Do not infer speech from the filename or metadata.
- Be conservative when the audio is unclear or contains no speech.
- Return JSON only. Do not use Markdown fences.
"""

    client = genai.Client(api_key=settings.gemini_api_key)

    response = client.models.generate_content(
        model=settings.gemini_model,
        contents=[
            prompt,
            types.Part.from_bytes(
                data=audio_bytes,
                mime_type=mime_type,
            ),
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
        ),
    )

    if not response.text:
        raise ValueError("Gemini returned an empty response.")

    result = EvaluationResult.model_validate_json(response.text)

    # The model must not award points when any required condition fails.
    if not (
        result.language_matches
        and result.required_words_used
        and result.meaningful_sentence
    ):
        result.score = 0

    return result


@router.post("")
def submit_attempt(
    challenge_id: UUID = Form(...),
    language: str = Form(...),
    user_id: UUID = Form(...),
    audio: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    # Temporary identity mechanism for development only.
    if settings.app_env.lower() != "development":
        raise HTTPException(
            status_code=403,
            detail="Development submission mode is disabled.",
        )

    if language not in LANGUAGES:
        raise HTTPException(
            status_code=400,
            detail="Unsupported language. Use en, hi, kn, te, or mr.",
        )

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")

    app_timezone = ZoneInfo(settings.timezone)
    today = datetime.now(app_timezone).date()

    challenge = db.scalar(
        select(Challenge).where(
            Challenge.id == challenge_id,
            Challenge.publish_date == today,
            Challenge.status == "published",
        )
    )

    if challenge is None:
        raise HTTPException(
            status_code=404,
            detail="Today's published challenge was not found.",
        )

    mime_type = (audio.content_type or "").split(";")[0].strip().lower()

    if mime_type not in ALLOWED_AUDIO_TYPES:
        raise HTTPException(
            status_code=415,
            detail="Unsupported audio format.",
        )

    # Read at most 1 byte beyond the limit to detect oversized uploads.
    audio_bytes = audio.file.read(MAX_AUDIO_BYTES + 1)

    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Audio file is empty.")

    if len(audio_bytes) > MAX_AUDIO_BYTES:
        raise HTTPException(
            status_code=413,
            detail="Audio file must be 8 MB or smaller.",
        )

    words = db.scalars(
        select(ChallengeWord)
        .where(ChallengeWord.challenge_id == challenge.id)
        .order_by(ChallengeWord.position)
    ).all()

    if len(words) != 3:
        raise HTTPException(
            status_code=500,
            detail="Challenge configuration is invalid.",
        )

    required_words = []

    for word in words:
        translation = db.scalar(
            select(WordTranslation).where(
                WordTranslation.challenge_word_id == word.id,
                WordTranslation.language_code == language,
            )
        )

        if translation is None:
            raise HTTPException(
                status_code=500,
                detail="A required translation is missing.",
            )

        required_words.append(translation.translated_word)

    # Ensure a progress row exists. A concurrent insert is harmless.
    progress = db.scalar(
        select(UserChallengeProgress).where(
            UserChallengeProgress.user_id == user_id,
            UserChallengeProgress.challenge_id == challenge.id,
        )
    )

    if progress is None:
        db.add(
            UserChallengeProgress(
                user_id=user_id,
                challenge_id=challenge.id,
                attempts_used=0,
                completed=False,
                xp_earned=0,
            )
        )

        try:
            db.commit()
        except IntegrityError:
            # Another request may have created the row first.
            db.rollback()

    # Serialize submissions for this user/challenge.
    # PostgreSQL holds this row lock while Gemini evaluates the audio.
    progress = db.scalar(
        select(UserChallengeProgress)
        .where(
            UserChallengeProgress.user_id == user_id,
            UserChallengeProgress.challenge_id == challenge.id,
        )
        .with_for_update()
    )

    if progress is None:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Could not initialize challenge progress.",
        )

    if progress.completed:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="You have already completed today's challenge.",
        )

    if progress.attempts_used >= 2:
        db.rollback()
        raise HTTPException(
            status_code=429,
            detail="You have used both attempts for today's challenge.",
        )

    # Do not increment attempts until Gemini returns a valid evaluation.
    try:
        evaluation = evaluate_audio(
            audio_bytes=audio_bytes,
            mime_type=mime_type,
            language_code=language,
            required_words=required_words,
        )
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=503,
            detail=(
                "Speech evaluation is temporarily unavailable. "
                "Your attempt was not used. Please try again."
            ),
        )

    passed = (
        evaluation.score > 0
        and evaluation.language_matches
        and evaluation.required_words_used
        and evaluation.meaningful_sentence
    )

    progress.attempts_used += 1

    if passed:
        progress.completed = True
        progress.xp_earned = 10
        progress.completed_at = datetime.now(dt_timezone.utc)
    submission = Submission(
        user_id=user_id,
        challenge_id=challenge.id,
        language_code=language,
        score=evaluation.score,
        passed=passed,
        evaluation=evaluation.model_dump(by_alias=True),
        audio_object_key=None,
    )

    db.add(submission)

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Could not save the submission. Please try again.",
        )

    db.refresh(progress)

    return {
        "submissionId": str(submission.id),
        "challengeId": str(challenge.id),
        "language": language,
        "score": evaluation.score,
        "passed": passed,
        "feedback": evaluation.feedback,
        "attemptsUsed": progress.attempts_used,
        "attemptsRemaining": max(0, 2 - progress.attempts_used),
        "completed": progress.completed,
        "xpEarned": progress.xp_earned,
    }
