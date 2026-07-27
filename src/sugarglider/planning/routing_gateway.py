"""The sole cached, budgeted routing boundary used by planning searches."""

from collections.abc import Awaitable, Callable
from hashlib import sha256
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
from sugarglider.planning.profiles import RoutingProfileId, routing_profile
from sugarglider.routing.backend import (
    AutoTourRoutingBackend,
    CorridorAvoidanceArea,
    CorridorAvoidingRoutingBackend,
    GraphHopperRoutingCapabilities,
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

    @property
    def capabilities(self) -> GraphHopperRoutingCapabilities:
        if isinstance(self._backend, CorridorAvoidingRoutingBackend):
            return self._backend.routing_capabilities
        return GraphHopperRoutingCapabilities(
            request_custom_model=False,
            custom_model_areas=False,
            alternative_route_with_custom_model=False,
            internal_via_points=callable(getattr(self._backend, "route", None)),
        )

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
        profile: RoutingProfileId,
        *,
        pass_through: bool = False,
        phase: SearchPhase = SearchPhase.CONTROL,
        topology_options: tuple[tuple[str, str], ...] = (),
        custom_options: tuple[tuple[str, str], ...] = (),
    ) -> RoutedPath:
        key = RouteCacheKey(
            operation=RoutingOperation.ROUTE,
            profile_id=profile,
            backend_profile=routing_profile(profile).graphhopper_profile,
            coordinates=tuple((point.lat, point.lon) for point in points),
            pass_through=pass_through,
            topology_options=topology_options,
            custom_options=(
                (
                    "snap_preventions",
                    ",".join(routing_profile(profile).snap_preventions),
                ),
                *custom_options,
            ),
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
        profile: RoutingProfileId,
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
            backend_profile=routing_profile(profile).graphhopper_profile,
            coordinates=((start.lat, start.lon), (end.lat, end.lon)),
            alternative_settings=settings,
            custom_options=(
                (
                    "snap_preventions",
                    ",".join(routing_profile(profile).snap_preventions),
                ),
            ),
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

    async def alternative_routes_avoiding_corridor(
        self,
        start: Coordinate,
        end: Coordinate,
        profile: RoutingProfileId,
        area: CorridorAvoidanceArea,
        *,
        priority_multiplier: float,
        max_paths: int = 3,
        max_weight_factor: float = 1.8,
        max_share_factor: float = 0.7,
        phase: SearchPhase = SearchPhase.GLOBAL_OPTIMIZATION,
    ) -> tuple[RoutedPath, ...]:
        """Route with one cached request-specific custom-model area penalty."""
        if not isinstance(self._backend, CorridorAvoidingRoutingBackend):
            raise RuntimeError("routing backend does not support corridor avoidance")
        backend = cast(CorridorAvoidingRoutingBackend, self._backend)
        area_digest = sha256(repr(area).encode()).hexdigest()
        settings: tuple[tuple[str, float | int], ...] = (
            ("max_paths", max_paths),
            ("max_share_factor", max_share_factor),
            ("max_weight_factor", max_weight_factor),
        )
        key = RouteCacheKey(
            operation=RoutingOperation.AVOIDING_ALTERNATIVES,
            profile_id=profile,
            backend_profile=routing_profile(profile).graphhopper_profile,
            coordinates=((start.lat, start.lon), (end.lat, end.lon)),
            alternative_settings=settings,
            custom_options=(
                ("avoidance_area_sha256", area_digest),
                ("avoidance_priority_multiplier", f"{priority_multiplier:.6f}"),
                (
                    "snap_preventions",
                    ",".join(routing_profile(profile).snap_preventions),
                ),
            ),
        )
        return await self._resolve(
            key,
            phase,
            lambda: backend.alternative_routes_avoiding_corridor(
                start,
                end,
                profile,
                area,
                priority_multiplier=priority_multiplier,
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
        profile: RoutingProfileId,
        *,
        heading_degrees: float | None = None,
        phase: SearchPhase = SearchPhase.CONTROL,
    ) -> RoutedPath:
        key = RouteCacheKey(
            operation=RoutingOperation.ROUND_TRIP,
            profile_id=profile,
            backend_profile=routing_profile(profile).graphhopper_profile,
            coordinates=((start.lat, start.lon),),
            round_trip_distance_m=distance_m,
            round_trip_seed=seed,
            round_trip_heading_degrees=heading_degrees,
            headings=(heading_degrees,),
            custom_options=(
                (
                    "snap_preventions",
                    ",".join(routing_profile(profile).snap_preventions),
                ),
            ),
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
            backend_profile=routing_profile(profile).graphhopper_profile,
            coordinates=((start.lat, start.lon),),
            isochrone_distance_limit_m=distance_limit_m,
            isochrone_buckets=buckets,
            isochrone_reverse_flow=reverse_flow,
            custom_options=(
                ("backend_profile", routing_profile(profile).graphhopper_profile),
            ),
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
