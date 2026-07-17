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
    low_overlap_max_paths: Annotated[
        int,
        Field(ge=1, le=5, validation_alias="SUGARGLIDER_LOW_OVERLAP_MAX_PATHS"),
    ] = 3
    low_overlap_max_weight_factor: Annotated[
        float,
        Field(
            ge=1.0,
            le=3.0,
            validation_alias="SUGARGLIDER_LOW_OVERLAP_MAX_WEIGHT_FACTOR",
        ),
    ] = 1.6
    low_overlap_max_share_factor: Annotated[
        float,
        Field(
            ge=0.0,
            le=1.0,
            validation_alias="SUGARGLIDER_LOW_OVERLAP_MAX_SHARE_FACTOR",
        ),
    ] = 0.5
    low_overlap_beam_width: Annotated[
        int,
        Field(ge=1, le=50, validation_alias="SUGARGLIDER_LOW_OVERLAP_BEAM_WIDTH"),
    ] = 12
    low_overlap_max_leg_requests: Annotated[
        int,
        Field(ge=1, validation_alias="SUGARGLIDER_LOW_OVERLAP_MAX_LEG_REQUESTS"),
    ] = 48
    low_overlap_source_count: Annotated[
        int,
        Field(ge=1, le=3, validation_alias="SUGARGLIDER_LOW_OVERLAP_SOURCE_COUNT"),
    ] = 2
