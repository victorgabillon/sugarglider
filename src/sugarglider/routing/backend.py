"""Typed routing boundary shared by ordinary routing and generation."""

from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite
from re import fullmatch
from typing import Protocol, runtime_checkable

from shapely.geometry import MultiPolygon, Polygon

from sugarglider.domain.models import Coordinate, GeoJsonPosition, PathDetailSegment
from sugarglider.routing.profiles import RoutingProfileId


@dataclass(frozen=True)
class RoutedPath:
    """Immutable routed path returned by any routing backend."""

    distance_m: float
    duration_ms: int
    ascend_m: float | None
    descend_m: float | None
    geometry: tuple[GeoJsonPosition, ...]
    snapped_points: tuple[GeoJsonPosition, ...] | None
    details: Mapping[str, tuple[PathDetailSegment, ...]]


@dataclass(frozen=True)
class GraphHopperRoutingCapabilities:
    """Features verified against the packaged GraphHopper configuration."""

    request_custom_model: bool
    custom_model_areas: bool
    alternative_route_with_custom_model: bool
    internal_via_points: bool


@dataclass(frozen=True)
class CorridorAvoidanceArea:
    """One private bounded GeoJSON polygon used only for route weighting."""

    id: str
    polygon: tuple[GeoJsonPosition, ...]
    source_distance_m: float
    buffer_width_m: float

    def __post_init__(self) -> None:
        if fullmatch(r"[a-z][a-z0-9_]{0,47}", self.id) is None:
            raise ValueError("avoidance area ID is not a safe custom-model identifier")
        if len(self.polygon) < 4 or self.polygon[0] != self.polygon[-1]:
            raise ValueError("avoidance area must be a closed polygon")
        if len(self.polygon) > 80:
            raise ValueError("avoidance area polygon exceeds the complexity bound")
        if any(
            not isfinite(value) or value < 0
            for value in (self.source_distance_m, self.buffer_width_m)
        ):
            raise ValueError("avoidance area distances must be finite and nonnegative")

    @property
    def vertex_count(self) -> int:
        return len(self.polygon)


@dataclass(frozen=True)
class IsochronePolygon:
    """One WGS84 polygon shell and its preserved interior rings."""

    exterior: tuple[GeoJsonPosition, ...]
    holes: tuple[tuple[GeoJsonPosition, ...], ...] = ()

    def to_shapely(self) -> Polygon:
        """Build an independent Shapely value for spatial operations."""
        return Polygon(self.exterior, self.holes)


@dataclass(frozen=True)
class IsochroneResult:
    """Validated polygonal reachable envelope returned by GraphHopper."""

    polygons: tuple[IsochronePolygon, ...]
    geometry_was_repaired: bool = False

    @property
    def geometry(self) -> Polygon | MultiPolygon:
        """Return the complete polygonal envelope with holes intact."""
        values = tuple(polygon.to_shapely() for polygon in self.polygons)
        return values[0] if len(values) == 1 else MultiPolygon(values)


class RoutingBackend(Protocol):
    """Minimal asynchronous routing operations needed by generation."""

    async def route(
        self,
        points: tuple[Coordinate, ...],
        profile: RoutingProfileId = "hike",
        *,
        pass_through: bool = False,
    ) -> RoutedPath: ...

    async def round_trip(
        self,
        start: Coordinate,
        distance_m: float,
        seed: int,
        profile: RoutingProfileId = "hike",
    ) -> RoutedPath: ...

    async def alternative_routes(
        self,
        start: Coordinate,
        end: Coordinate,
        profile: RoutingProfileId = "hike",
        *,
        max_paths: int = 3,
        max_weight_factor: float = 1.6,
        max_share_factor: float = 0.5,
    ) -> tuple[RoutedPath, ...]: ...


class AutoTourRoutingBackend(RoutingBackend, Protocol):
    """Additional GraphHopper proposal operations used only by Auto Tour."""

    async def round_trip(
        self,
        start: Coordinate,
        distance_m: float,
        seed: int,
        profile: RoutingProfileId = "hike",
        *,
        heading_degrees: float | None = None,
    ) -> RoutedPath: ...

    async def isochrone(
        self,
        start: Coordinate,
        profile: RoutingProfileId,
        *,
        distance_limit_m: float,
        buckets: int = 1,
        reverse_flow: bool = False,
    ) -> IsochroneResult: ...


@runtime_checkable
class CorridorAvoidingRoutingBackend(Protocol):
    """Optional self-hosted capability for request-specific area penalties."""

    @property
    def routing_capabilities(self) -> GraphHopperRoutingCapabilities: ...

    async def alternative_routes_avoiding_corridor(
        self,
        start: Coordinate,
        end: Coordinate,
        profile: RoutingProfileId,
        area: CorridorAvoidanceArea,
        *,
        priority_multiplier: float,
        max_paths: int,
        max_weight_factor: float,
        max_share_factor: float,
    ) -> tuple[RoutedPath, ...]: ...
