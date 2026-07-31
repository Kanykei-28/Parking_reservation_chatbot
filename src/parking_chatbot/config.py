from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )
    app_name: str = "Parking Reservation Chatbot"
    environment: str = "development"
    log_level: str = "INFO"
    database_path: Path = Path("data/dynamic/parking.db")
    vector_store_path: Path = Path("data/vector_store")
    reservations_file_path: Path = Path("data/dynamic/reservations.txt")
    llm_provider: str = "not-configured"
    llm_model: str = "not-configured"
    embedding_model: str = "not-configured"
    openai_api_key: SecretStr | None = Field(default=None, repr=False)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
