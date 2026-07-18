"""Immutable models exposed specifically for the browser application."""

from typing import Annotated, Literal

from pydantic import Field

from sugarglider.domain.analysis import DetailValue
from sugarglider.domain.models import GeoJsonPosition, ImmutableModel
from sugarglider.nature.analysis import NatureVisualizationClass


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
    auto_tour_max_hard_points: Literal[6] = 6
    auto_tour_max_preferred_pois: Literal[8] = 8
    auto_tour_scenic_corridor_radius_m: Annotated[float, Field(ge=50, le=2000)]
    auto_tour_water_corridor_radius_m: Annotated[float, Field(ge=25, le=1000)]


class LineStringGeometry(ImmutableModel):
    """A GeoJSON LineString in longitude/latitude order."""

    type: Literal["LineString"] = "LineString"
    coordinates: Annotated[tuple[GeoJsonPosition, ...], Field(min_length=2)]


class RouteSectionProperties(ImmutableModel):
    """Map styling and inspection properties for a contiguous route section."""

    kind: Literal["normal", "repeated", "immediate_backtrack"]
    distance_m: Annotated[float, Field(ge=0)]
    edge_id: int | None
    surface: DetailValue
    road_class: DetailValue
    nature_class: NatureVisualizationClass | None = None
    park_or_protected: bool | None = None
    near_water: bool | None = None


class RouteSectionFeature(ImmutableModel):
    """One deterministic GeoJSON-compatible route feature."""

    type: Literal["Feature"] = "Feature"
    geometry: LineStringGeometry
    properties: RouteSectionProperties


class RouteVisualization(ImmutableModel):
    """Feature collection returned for selected-candidate overlays."""

    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: tuple[RouteSectionFeature, ...]
