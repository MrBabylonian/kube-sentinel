from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        case_sensitive=True,
        env_ignore_empty=True,
        extra="ignore",
        env_file=Path(__file__).parent.parent / ".env",
    )
    GOOGLE_VERTEX_API_KEY: Annotated[SecretStr, Field(...)]
    GOOGLE_CLOUD_PROJECT: Annotated[SecretStr, Field(...)]
    DATABASE_URL: Annotated[SecretStr, Field(...)]
    DATABASE_URL_TEST: Annotated[SecretStr, Field()]
    LOG_LEVEL: Annotated[str, Field(...)]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # ty: ignore
