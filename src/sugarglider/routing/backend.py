"""Typed routing boundary shared by ordinary routing and generation."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from shapely.geometry import MultiPolygon, Polygon

from sugarglider.domain.models import Coordinate, GeoJsonPosition, PathDetailSegment


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
        profile: str = "hike",
        *,
        pass_through: bool = False,
    ) -> RoutedPath: ...

    async def round_trip(
        self,
        start: Coordinate,
        distance_m: float,
        seed: int,
        profile: str = "hike",
    ) -> RoutedPath: ...

    async def alternative_routes(
        self,
        start: Coordinate,
        end: Coordinate,
        profile: str = "hike",
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
        profile: str = "hike",
        *,
        heading_degrees: float | None = None,
    ) -> RoutedPath: ...

    async def isochrone(
        self,
        start: Coordinate,
        profile: str,
        *,
        distance_limit_m: float,
        buckets: int = 1,
        reverse_flow: bool = False,
    ) -> IsochroneResult: ...
