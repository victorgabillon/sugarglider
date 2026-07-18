"""Application configuration loaded from environment variables."""

from pathlib import Path
from typing import Annotated, Self

from pydantic import AnyHttpUrl, Field, model_validator
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
    map_tile_url: Annotated[
        str,
        Field(min_length=1, validation_alias="SUGARGLIDER_MAP_TILE_URL"),
    ] = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
    map_attribution: Annotated[
        str,
        Field(min_length=1, validation_alias="SUGARGLIDER_MAP_ATTRIBUTION"),
    ] = "© OpenStreetMap contributors"
    map_initial_lat: Annotated[
        float,
        Field(ge=-90, le=90, validation_alias="SUGARGLIDER_MAP_INITIAL_LAT"),
    ] = 48.87
    map_initial_lon: Annotated[
        float,
        Field(ge=-180, le=180, validation_alias="SUGARGLIDER_MAP_INITIAL_LON"),
    ] = 2.10
    map_initial_zoom: Annotated[
        float,
        Field(ge=0, le=22, validation_alias="SUGARGLIDER_MAP_INITIAL_ZOOM"),
    ] = 11.0
    nature_index_path: Annotated[
        Path | None,
        Field(validation_alias="SUGARGLIDER_NATURE_INDEX_PATH"),
    ] = Path("/data/nature/ile-de-france-nature-index.json.gz")
    nature_water_buffer_m: Annotated[
        float,
        Field(
            ge=0,
            le=1000,
            validation_alias="SUGARGLIDER_NATURE_WATER_BUFFER_M",
        ),
    ] = 100.0
    nature_missing_index_warning: Annotated[
        bool,
        Field(validation_alias="SUGARGLIDER_NATURE_MISSING_INDEX_WARNING"),
    ] = False
    poi_index_path: Annotated[
        Path | None,
        Field(validation_alias="SUGARGLIDER_POI_INDEX_PATH"),
    ] = Path("/data/pois/ile-de-france-poi-index.json.gz")
    poi_missing_index_warning: Annotated[
        bool,
        Field(validation_alias="SUGARGLIDER_POI_MISSING_INDEX_WARNING"),
    ] = False
    poi_default_limit: Annotated[
        int,
        Field(ge=1, le=5000, validation_alias="SUGARGLIDER_POI_DEFAULT_LIMIT"),
    ] = 500
    poi_max_limit: Annotated[
        int,
        Field(ge=1, le=5000, validation_alias="SUGARGLIDER_POI_MAX_LIMIT"),
    ] = 1000
    auto_tour_scenic_corridor_radius_m: Annotated[
        float,
        Field(
            ge=50,
            le=2000,
            validation_alias="SUGARGLIDER_AUTO_TOUR_SCENIC_CORRIDOR_RADIUS_M",
        ),
    ] = 600.0
    auto_tour_water_corridor_radius_m: Annotated[
        float,
        Field(
            ge=25,
            le=1000,
            validation_alias="SUGARGLIDER_AUTO_TOUR_WATER_CORRIDOR_RADIUS_M",
        ),
    ] = 350.0
    auto_tour_include_broad_attractions: Annotated[
        bool,
        Field(validation_alias="SUGARGLIDER_AUTO_TOUR_INCLUDE_BROAD_ATTRACTIONS"),
    ] = False

    @model_validator(mode="after")
    def validate_poi_limits(self) -> Self:
        if self.poi_default_limit > self.poi_max_limit:
            raise ValueError("POI default limit cannot exceed the maximum limit")
        return self
