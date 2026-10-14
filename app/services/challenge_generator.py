
from typing import Optional

from google import genai
from google.genai import types
from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.config import settings


LANGUAGE_CODES = ("en", "hi", "kn", "te", "mr")


class TranslationDraft(BaseModel):
    translated_word: str = Field(min_length=1)
    transliteration: Optional[str] = None
    meaning_note: Optional[str] = None

    @field_validator("translated_word")
    @classmethod
    def translated_word_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Translated word cannot be blank")
        return value


class TranslationSet(BaseModel):
    en: TranslationDraft
    hi: TranslationDraft
    kn: TranslationDraft
    te: TranslationDraft
    mr: TranslationDraft


class WordDraft(BaseModel):
    english_word: str = Field(min_length=1)
    english_meaning: str = Field(min_length=1)
    translations: TranslationSet

    @field_validator("english_word", "english_meaning")
    @classmethod
    def text_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Word and meaning must not be blank")
        return value


class ChallengeDraft(BaseModel):
    topic: str = Field(min_length=1)
    difficulty: str = "beginner"
    words: list[WordDraft] = Field(min_length=3, max_length=3)

    @field_validator("topic")
    @classmethod
    def topic_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Topic cannot be blank")
        return value

    @field_validator("difficulty")
    @classmethod
    def valid_difficulty(cls, value: str) -> str:
        if value not in {"beginner", "intermediate", "advanced"}:
            raise ValueError("Unsupported difficulty")
        return value

    @model_validator(mode="after")
    def validate_words(self):
        normalized = [
            word.english_word.strip().casefold()
            for word in self.words
        ]

        if len(set(normalized)) != 3:
            raise ValueError("The challenge must contain three distinct words")

        for word in self.words:
            if len(word.english_meaning.strip()) == 0:
                raise ValueError("Every word needs an English meaning")

            for language in LANGUAGE_CODES:
                translation = getattr(word.translations, language)
                if not translation.translated_word.strip():
                    raise ValueError(
                        f"Missing translation for {language}"
                    )

        return self


class ChallengeGenerationError(Exception):
    """Raised when Gemini cannot produce a valid challenge."""


def generate_challenge(
    topic_hint: Optional[str] = None,
    difficulty: str = "beginner",
) -> ChallengeDraft:
    """Generate and validate a three-word challenge in five languages."""

    if difficulty not in {"beginner", "intermediate", "advanced"}:
        raise ValueError("Unsupported difficulty")

    client = genai.Client(api_key=settings.gemini_api_key)

    topic_instruction = (
        f"Focus on this topic: {topic_hint}."
        if topic_hint
        else "Choose a useful everyday-life topic."
    )

    
    prompt = f"""
Create one language-learning challenge for an English-speaking learner.

REQUIRED TOPIC: {topic_hint or "Everyday life"}
REQUIRED DIFFICULTY: {difficulty}

Strict requirements:
- The topic MUST match the required topic.
- Do not substitute a related but different topic.
- For "Food and drinks", words must be about food, beverages,
  ordering food, cooking, or eating.
- For "Everyday life", words must be useful in ordinary daily activities.
- Include exactly three distinct, useful English words.
- Choose words that can naturally be used together in a sentence.
- Give each word a short, accurate English meaning.
- Translate every word into English (en), Hindi (hi), Kannada (kn),
  Telugu (te), and Marathi (mr).
- Include a natural translated word for each language.
- Provide transliteration when useful for non-Latin scripts.
- Do not invent translations or add extra required words.
- Return only data matching the requested structured schema.
"""


    try:
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=ChallengeDraft,
            ),
        )

        if not response.text:
            raise ChallengeGenerationError(
                "Gemini returned an empty response"
            )

        draft = ChallengeDraft.model_validate_json(response.text)

        # English translation should match the canonical English word.
        for word in draft.words:
            word.translations.en.translated_word = word.english_word

        return draft

    except ChallengeGenerationError:
        raise
    except Exception as exc:
        # Log the underlying exception on the server in a later hardening step.
        raise ChallengeGenerationError(
            "Could not generate a valid challenge"
        ) from exc
