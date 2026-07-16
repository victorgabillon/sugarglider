"""Application configuration loaded from environment variables."""

from pydantic import AnyHttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    graphhopper_url: AnyHttpUrl = AnyHttpUrl("http://graphhopper:8989")
    graphhopper_timeout_seconds: float = 60.0
