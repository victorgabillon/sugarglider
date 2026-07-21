"""One typed request-scoped cache for all routing operations."""

from dataclasses import dataclass
from enum import StrEnum
from typing import TypeVar

from sugarglider.domain.models import Coordinate
from sugarglider.planning.diagnostics import CacheDiagnostics
from sugarglider.planning.profiles import RoutingProfileId

T = TypeVar("T")


class RoutingOperation(StrEnum):
    ROUTE = "route"
    ROUND_TRIP = "round_trip"
    ISOCHRONE = "isochrone"
    ALTERNATIVES = "alternatives"


@dataclass(frozen=True)
class RouteCacheKey:
    operation: RoutingOperation
    profile_id: RoutingProfileId
    coordinates: tuple[tuple[float, float], ...]
    pass_through: bool | None = None
    topology_options: tuple[tuple[str, str], ...] = ()
    alternative_settings: tuple[tuple[str, float | int], ...] = ()
    round_trip_distance_m: float | None = None
    round_trip_seed: int | None = None
    round_trip_heading_degrees: float | None = None
    isochrone_distance_limit_m: float | None = None
    isochrone_buckets: int | None = None
    isochrone_reverse_flow: bool | None = None
    headings: tuple[float | None, ...] = ()
    custom_options: tuple[tuple[str, str], ...] = ()

    @classmethod
    def for_route(
        cls,
        *,
        profile_id: RoutingProfileId,
        points: tuple[Coordinate, ...],
        pass_through: bool,
        topology_options: tuple[tuple[str, str], ...] = (),
    ) -> "RouteCacheKey":
        return cls(
            operation=RoutingOperation.ROUTE,
            profile_id=profile_id,
            coordinates=tuple((point.lat, point.lon) for point in points),
            pass_through=pass_through,
            topology_options=topology_options,
        )


@dataclass(frozen=True)
class CachedFailure:
    error: Exception


type CacheValue[T] = T | None


class RouteCallCache[T]:
    """Cache successful and failed operations while reporting one hit/miss stream."""

    __slots__ = ("_backend_calls", "_entries", "_hits", "_misses", "_rejections")

    def __init__(self) -> None:
        self._entries: dict[RouteCacheKey, CacheValue[T]] = {}
        self._hits = 0
        self._misses = 0
        self._backend_calls = 0
        self._rejections = 0

    def lookup(self, key: RouteCacheKey) -> tuple[bool, CacheValue[T] | None]:
        if key in self._entries:
            self._hits += 1
            return True, self._entries[key]
        self._misses += 1
        return False, None

    def store(self, key: RouteCacheKey, value: CacheValue[T]) -> None:
        self._entries[key] = value

    def peek(self, key: RouteCacheKey) -> CacheValue[T] | None:
        """Read a cached value for internal heuristics without changing statistics."""
        return self._entries.get(key)

    def record_backend_call(self) -> None:
        self._backend_calls += 1

    def record_pre_backend_rejection(self) -> None:
        if self._misses < 1:
            raise RuntimeError("cannot reject before a recorded cache miss")
        self._misses -= 1
        self._rejections += 1

    def diagnostics(self) -> CacheDiagnostics:
        failures = sum(
            value is None or isinstance(value, CachedFailure)
            for value in self._entries.values()
        )
        return CacheDiagnostics(
            lookup_count=self._hits + self._misses,
            hit_count=self._hits,
            miss_count=self._misses,
            entry_count=len(self._entries),
            successful_entry_count=len(self._entries) - failures,
            failed_entry_count=failures,
            backend_call_count=self._backend_calls,
            pre_backend_rejection_count=self._rejections,
        )

    def snapshot(self) -> CacheDiagnostics:
        return self.diagnostics()

    @property
    def entry_count(self) -> int:
        return len(self._entries)
