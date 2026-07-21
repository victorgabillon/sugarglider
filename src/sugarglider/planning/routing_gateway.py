"""The sole cached, budgeted routing boundary used by planning searches."""

from collections.abc import Awaitable, Callable
from typing import TypeVar, cast

from sugarglider.domain.models import Coordinate
from sugarglider.planning.budget import SearchBudget, SearchPhase
from sugarglider.planning.cache import (
    CachedFailure,
    RouteCacheKey,
    RouteCallCache,
    RoutingOperation,
)
from sugarglider.planning.diagnostics import CacheDiagnostics
from sugarglider.planning.profiles import RoutingProfileId
from sugarglider.routing.backend import (
    AutoTourRoutingBackend,
    IsochroneResult,
    RoutedPath,
)

T = TypeVar("T")


class SearchBudgetExhaustedError(RuntimeError):
    """The requested routing phase has no remaining request capacity."""


class CachedRoutingGateway:
    """Reserve on misses and cache both successful and failed backend calls."""

    def __init__(self, backend: AutoTourRoutingBackend, budget: SearchBudget) -> None:
        self._backend = backend
        self._budget = budget
        self._cache: RouteCallCache[object] = RouteCallCache()

    async def _resolve(
        self, key: RouteCacheKey, phase: SearchPhase, call: Callable[[], Awaitable[T]]
    ) -> T:
        hit, cached = self._cache.lookup(key)
        if hit:
            if isinstance(cached, CachedFailure):
                raise cached.error
            return cast(T, cached)
        if not self._budget.reserve(phase):
            self._cache.record_pre_backend_rejection()
            raise SearchBudgetExhaustedError(
                f"routing budget exhausted for {phase.value}"
            )
        self._cache.record_backend_call()
        try:
            value = await call()
        except Exception as exc:
            self._cache.store(key, CachedFailure(exc))
            raise
        self._cache.store(key, value)
        return value

    async def route(
        self,
        points: tuple[Coordinate, ...],
        profile: RoutingProfileId = "hike",
        *,
        pass_through: bool = False,
        phase: SearchPhase = SearchPhase.CONTROL,
        topology_options: tuple[tuple[str, str], ...] = (),
        custom_options: tuple[tuple[str, str], ...] = (),
    ) -> RoutedPath:
        key = RouteCacheKey(
            operation=RoutingOperation.ROUTE,
            profile_id=profile,
            coordinates=tuple((point.lat, point.lon) for point in points),
            pass_through=pass_through,
            topology_options=topology_options,
            custom_options=custom_options,
        )
        return await self._resolve(
            key,
            phase,
            lambda: self._backend.route(points, profile, pass_through=pass_through),
        )

    async def alternative_routes(
        self,
        start: Coordinate,
        end: Coordinate,
        profile: RoutingProfileId = "hike",
        *,
        max_paths: int = 3,
        max_weight_factor: float = 1.6,
        max_share_factor: float = 0.5,
        phase: SearchPhase = SearchPhase.ALTERNATIVE_LEG,
    ) -> tuple[RoutedPath, ...]:
        settings: tuple[tuple[str, float | int], ...] = (
            ("max_paths", max_paths),
            ("max_share_factor", max_share_factor),
            ("max_weight_factor", max_weight_factor),
        )
        key = RouteCacheKey(
            operation=RoutingOperation.ALTERNATIVES,
            profile_id=profile,
            coordinates=((start.lat, start.lon), (end.lat, end.lon)),
            alternative_settings=settings,
        )
        return await self._resolve(
            key,
            phase,
            lambda: self._backend.alternative_routes(
                start,
                end,
                profile,
                max_paths=max_paths,
                max_weight_factor=max_weight_factor,
                max_share_factor=max_share_factor,
            ),
        )

    async def round_trip(
        self,
        start: Coordinate,
        distance_m: float,
        seed: int,
        profile: RoutingProfileId = "hike",
        *,
        heading_degrees: float | None = None,
        phase: SearchPhase = SearchPhase.CONTROL,
    ) -> RoutedPath:
        key = RouteCacheKey(
            operation=RoutingOperation.ROUND_TRIP,
            profile_id=profile,
            coordinates=((start.lat, start.lon),),
            round_trip_distance_m=distance_m,
            round_trip_seed=seed,
            round_trip_heading_degrees=heading_degrees,
            headings=(heading_degrees,),
        )
        return await self._resolve(
            key,
            phase,
            lambda: self._backend.round_trip(
                start,
                distance_m,
                seed,
                profile,
                heading_degrees=heading_degrees,
            ),
        )

    async def isochrone(
        self,
        start: Coordinate,
        profile: RoutingProfileId,
        *,
        distance_limit_m: float,
        buckets: int = 1,
        reverse_flow: bool = False,
        phase: SearchPhase = SearchPhase.SKELETON,
    ) -> IsochroneResult:
        key = RouteCacheKey(
            operation=RoutingOperation.ISOCHRONE,
            profile_id=profile,
            coordinates=((start.lat, start.lon),),
            isochrone_distance_limit_m=distance_limit_m,
            isochrone_buckets=buckets,
            isochrone_reverse_flow=reverse_flow,
        )
        return await self._resolve(
            key,
            phase,
            lambda: self._backend.isochrone(
                start,
                profile,
                distance_limit_m=distance_limit_m,
                buckets=buckets,
                reverse_flow=reverse_flow,
            ),
        )

    def cache_snapshot(self) -> CacheDiagnostics:
        return self._cache.snapshot()

    def peek(self, key: RouteCacheKey) -> object | None:
        return self._cache.peek(key)
