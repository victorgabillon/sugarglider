"""Immutable models exposed specifically for the browser application."""

from typing import Annotated, Literal

from pydantic import Field

from sugarglider.domain.models import GeoJsonPosition, ImmutableModel


class UiConfig(ImmutableModel):
    """Runtime map configuration safe to expose to an unauthenticated browser."""

    tile_url_template: str
    tile_attribution: str
    initial_center: GeoJsonPosition
    initial_zoom: Annotated[float, Field(ge=0, le=22)]
    max_required_points: Annotated[int, Field(ge=2)]
    nature_index_available: bool
    nature_water_buffer_m: Annotated[float, Field(ge=0, le=1000)]
    nature_preference_values: tuple[Literal["off", "prefer"], ...]
    loop_geometry_preference_values: tuple[Literal["off", "prefer"], ...]
    poi_index_available: bool
    poi_default_limit: Annotated[int, Field(ge=1)]
    poi_max_limit: Annotated[int, Field(ge=1)]
    default_planning_mode: Literal["auto_tour"] = "auto_tour"
    auto_tour_max_hard_waypoints: Literal[6] = 6
    auto_tour_max_preferred_pois: Literal[8] = 8
    auto_tour_scenic_corridor_radius_m: Annotated[float, Field(ge=50, le=2000)]
    auto_tour_water_corridor_radius_m: Annotated[float, Field(ge=25, le=1000)]
