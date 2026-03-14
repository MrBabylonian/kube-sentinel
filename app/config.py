from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        case_sensitive=True,
        env_ignore_empty=True,
        extra="ignore",
        env_file=Path(".env"),
    )
    GOOGLE_VERTEX_API_KEY: Annotated[SecretStr, Field(...)]
    GOOGLE_CLOUD_PROJECT: Annotated[SecretStr, Field(...)]
    DATABASE_URL: Annotated[SecretStr, Field(...)]
    DATABASE_URL_TEST: Annotated[SecretStr | None, Field(default=None)]
    LOG_LEVEL: Annotated[
        Literal["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"],
        Field(default="NOTSET"),
    ]
    ENVIRONMENT: Annotated[
        Literal["PRODUCTION", "DEVELOPMENT"], Field(default="DEVELOPMENT")
    ]


@lru_cache
def get_app_settings() -> Settings:
    return Settings()  # ty: ignore
