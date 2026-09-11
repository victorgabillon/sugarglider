"""Explicit production configuration, independent of the reference .env file."""

from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from sugarglider.config import Settings


class _SocialPersistenceSettings(Settings):
    model_config = SettingsConfigDict(env_file=None)


class SocialSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SUGARGLIDER_SOCIAL_", extra="forbid", frozen=True
    )

    public_origin: str = ""
    data_directory: Path = Path("/data")
    max_body_bytes: Annotated[int, Field(ge=1024, le=12_000_000)] = 12_000_000
    max_requests_per_minute: Annotated[int, Field(ge=12, le=6000)] = 240
    max_creations_per_hour: Annotated[int, Field(ge=1, le=1000)] = 30
    max_client_buckets: Annotated[int, Field(ge=1, le=20_000)] = 4096
    max_active_requests: Annotated[int, Field(ge=1, le=64)] = 16
    max_active_writes: Annotated[int, Field(ge=1, le=8)] = 2
    max_event_streams: Annotated[int, Field(ge=1, le=256)] = 64
    max_event_streams_per_client: Annotated[int, Field(ge=1, le=32)] = 8
    body_timeout_seconds: Annotated[float, Field(gt=0, le=60)] = 30
    cleanup_interval_seconds: Annotated[float, Field(gt=0, le=3600)] = 60
    minimum_free_bytes: Annotated[int, Field(ge=0)] = 256_000_000
    saved_route_ttl_days: Annotated[int, Field(ge=1, le=90)] = 90
    outing_ttl_days: Annotated[int, Field(ge=1, le=30)] = 30

    @field_validator("public_origin")
    @classmethod
    def validate_origin(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in ("", "/")
            or parsed.query
            or parsed.fragment
            or any(character.isspace() for character in value)
            or "*" in value
            or "\\" in value
        ):
            raise ValueError("public_origin must be one exact HTTPS origin")
        # Also validate the port, without including user input in the error.
        try:
            _port = parsed.port
        except ValueError:
            raise ValueError("public_origin has an invalid port") from None
        return f"https://{parsed.netloc.lower()}".removesuffix(":443")

    @field_validator("data_directory")
    @classmethod
    def validate_directory(cls, value: Path) -> Path:
        if not value.is_absolute():
            raise ValueError("data_directory must be absolute")
        return value

    def persistence_settings(self) -> Settings:
        """Only explicit persistence options enter the shared startup helpers."""
        return _SocialPersistenceSettings(
            saved_route_database_path=self.data_directory / "saved-routes.sqlite3",
            outing_database_path=self.data_directory / "outings.sqlite3",
            saved_route_ttl_days=self.saved_route_ttl_days,
            outing_ttl_days=self.outing_ttl_days,
            saved_route_max_snapshot_bytes=10_000_000,
            outing_max_route_snapshot_bytes=10_000_000,
            outing_max_participants=8,
            outing_live_stale_after_seconds=120,
            outing_live_expire_after_seconds=3600,
            outing_live_max_update_age_seconds=600,
            outing_live_future_tolerance_seconds=30,
            outing_live_event_retention_seconds=900,
            outing_live_max_events_per_outing=1000,
            outing_live_sse_keepalive_seconds=15,
            nature_index_path=None,
            poi_index_path=None,
        )
