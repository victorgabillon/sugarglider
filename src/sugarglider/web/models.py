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
