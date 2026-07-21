"""Immutable route-section projection models independent of the browser package."""

from typing import Annotated, Literal

from pydantic import Field

from sugarglider.domain.analysis import DetailValue
from sugarglider.domain.models import GeoJsonPosition, ImmutableModel
from sugarglider.nature.analysis import NatureVisualizationClass


class LineStringGeometry(ImmutableModel):
    type: Literal["LineString"] = "LineString"
    coordinates: Annotated[tuple[GeoJsonPosition, ...], Field(min_length=2)]


class RouteSectionProperties(ImmutableModel):
    kind: Literal["normal", "repeated", "immediate_backtrack"]
    distance_m: Annotated[float, Field(ge=0)]
    edge_id: int | None
    surface: DetailValue
    road_class: DetailValue
    nature_class: NatureVisualizationClass | None = None
    park_or_protected: bool | None = None
    near_water: bool | None = None


class RouteSectionFeature(ImmutableModel):
    type: Literal["Feature"] = "Feature"
    geometry: LineStringGeometry
    properties: RouteSectionProperties


class RouteVisualization(ImmutableModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: tuple[RouteSectionFeature, ...]
