from sqlalchemy import Index, text
import uuid

from datetime import date, datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    google_sub: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    email: Mapped[str] = mapped_column(
        String(320), index=True, nullable=False
    )
    display_name: Mapped[str | None] = mapped_column(
        String(120), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class Challenge(Base):
    __tablename__ = "challenges"
    __table_args__ = (
        UniqueConstraint("publish_date", name="uq_challenge_publish_date"),
        CheckConstraint(
            "status IN ('draft', 'scheduled', 'published', 'archived')",
            name="ck_challenge_status",
        ),
        Index(
    "uq_challenge_published_date",
    "publish_date",
    unique=True,
    postgresql_where=text("status = 'published'"),
),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    concept_key: Mapped[str] = mapped_column(
        String(120), index=True, nullable=False
    )
    topic: Mapped[str] = mapped_column(String(80), nullable=False)
    difficulty: Mapped[str] = mapped_column(
        String(20), default="beginner", nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(20), default="draft", nullable=False
    )
    publish_date: Mapped[date | None] = mapped_column(
        Date, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class ChallengeWord(Base):
    __tablename__ = "challenge_words"
    __table_args__ = (
        UniqueConstraint(
            "challenge_id", "position", name="uq_challenge_word_position"
        ),
        CheckConstraint(
            "position BETWEEN 1 AND 3", name="ck_word_position"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    challenge_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("challenges.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    english_word: Mapped[str] = mapped_column(String(100), nullable=False)
    english_meaning: Mapped[str] = mapped_column(Text, nullable=False)


class WordTranslation(Base):
    __tablename__ = "word_translations"
    __table_args__ = (
        UniqueConstraint(
            "challenge_word_id", "language_code",
            name="uq_word_translation_language",
        ),
        CheckConstraint(
            "language_code IN ('en', 'hi', 'kn', 'te', 'mr')",
            name="ck_translation_language",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    challenge_word_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("challenge_words.id", ondelete="CASCADE"),
        nullable=False,
    )
    language_code: Mapped[str] = mapped_column(
        String(2), nullable=False
    )
    translated_word: Mapped[str] = mapped_column(
        String(100), nullable=False
    )
    transliteration: Mapped[str | None] = mapped_column(
        String(150), nullable=True
    )
    meaning_note: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )


class UserChallengeProgress(Base):
    __tablename__ = "user_challenge_progress"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "challenge_id",
            name="uq_user_challenge_progress",
        ),
        CheckConstraint(
            "attempts_used BETWEEN 0 AND 2",
            name="ck_attempts_used",
        ),
        CheckConstraint("xp_earned >= 0", name="ck_xp_nonnegative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    challenge_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("challenges.id", ondelete="RESTRICT"), nullable=False
    )
    attempts_used: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    completed: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    xp_earned: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class Submission(Base):
    __tablename__ = "submissions"
    __table_args__ = (
        CheckConstraint(
            "score BETWEEN 0 AND 10", name="ck_submission_score"
        ),
        Index("ix_submission_user_created", "user_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    challenge_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("challenges.id", ondelete="RESTRICT"), nullable=False
    )
    language_code: Mapped[str] = mapped_column(
        String(2), nullable=False
    )
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    evaluation: Mapped[dict] = mapped_column(JSON, nullable=False)
    audio_object_key: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


