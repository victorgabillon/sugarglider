"""Typed routing boundary shared by ordinary routing and generation."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

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
