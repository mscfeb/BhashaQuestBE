
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Bhasha Quest API"
    app_env: str = "development"

    database_url: str

    gemini_api_key: str
    gemini_model: str = "gemini-3.1-flash-lite"

    google_client_id: str
    timezone: str = "Asia/Kolkata"
    frontend_origin: str = "http://localhost:3000"
    session_secret: str
    session_cookie_secure: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
