"""Application configuration loaded from environment variables."""

from typing import Annotated

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings."""

    model_config = SettingsConfigDict(
        env_file=".env", extra="ignore", populate_by_name=True
    )

    graphhopper_url: AnyHttpUrl = AnyHttpUrl("http://graphhopper:8989")
    graphhopper_timeout_seconds: float = 60.0
    generation_max_evaluations: Annotated[
        int,
        Field(ge=1, validation_alias="SUGARGLIDER_GENERATION_MAX_EVALUATIONS"),
    ] = 48
    generation_max_optional_snap_displacement_m: Annotated[
        float,
        Field(
            ge=0,
            validation_alias=(
                "SUGARGLIDER_GENERATION_MAX_OPTIONAL_SNAP_DISPLACEMENT_M"
            ),
        ),
    ] = 300.0
