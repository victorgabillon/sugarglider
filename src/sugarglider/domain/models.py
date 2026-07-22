"""Typed models shared by the routing, API, and GPX layers."""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, model_validator

from sugarglider.domain.analysis import DetailValue, RouteAnalysis

type RoutingProfileId = Literal[
    "hike",
    "trail_run",
    "city_bike",
    "gravel_bike",
    "mountain_bike",
    "road_bike",
]

Latitude = Annotated[float, Field(ge=-90, le=90)]
Longitude = Annotated[float, Field(ge=-180, le=180)]
GeoJsonPosition = tuple[Longitude, Latitude]
PathDetailValue = DetailValue


class ImmutableModel(BaseModel):
    """Base model whose fields cannot be reassigned after validation."""

    model_config = ConfigDict(frozen=True)


class Coordinate(ImmutableModel):
    """A named WGS84 coordinate using explicit latitude and longitude fields."""

    lat: Latitude
    lon: Longitude
    name: str | None = None


class RouteRequest(ImmutableModel):
    """An ordered collection of anchors to route through."""

    name: str = "Sugarglider route"
    points: Annotated[list[Coordinate], Field(min_length=2)]
    closed: bool = False
    profile: RoutingProfileId
    _input_point_count: int = PrivateAttr()

    @model_validator(mode="after")
    def validate_and_close_points(self) -> Self:
        """Reject adjacent duplicates and append a closing point when requested."""
        self._input_point_count = len(self.points)
        for previous, current in zip(self.points, self.points[1:], strict=False):
            if (previous.lat, previous.lon) == (current.lat, current.lon):
                raise ValueError(
                    "adjacent route points must not have equal coordinates"
                )

        if self.closed:
            first = self.points[0]
            last = self.points[-1]
            if (first.lat, first.lon) != (last.lat, last.lon):
                object.__setattr__(self, "points", [*self.points, first])
        return self

    @property
    def input_point_count(self) -> int:
        """Number of anchors supplied before automatic loop closure."""
        return self._input_point_count


class RouteSummary(ImmutableModel):
    """High-level metrics for a routed path."""

    distance_m: Annotated[float, Field(ge=0)]
    duration_ms: Annotated[int, Field(ge=0)]
    ascend_m: float | None = None
    descend_m: float | None = None
    input_point_count: Annotated[int, Field(ge=2)]
    routed_point_count: Annotated[int, Field(ge=1)]


class PathDetailSegment(ImmutableModel):
    """A GraphHopper path detail over a half-open geometry index interval."""

    from_index: Annotated[int, Field(ge=0)]
    to_index: Annotated[int, Field(ge=0)]
    value: PathDetailValue


class RouteResult(ImmutableModel):
    """A route computed on the GraphHopper/OSM network."""

    name: str
    routing_profile: RoutingProfileId
    summary: RouteSummary
    geometry: tuple[GeoJsonPosition, ...]
    snapped_points: tuple[GeoJsonPosition, ...] | None = None
    path_details: dict[str, tuple[PathDetailSegment, ...]] = Field(default_factory=dict)
    analysis: RouteAnalysis
