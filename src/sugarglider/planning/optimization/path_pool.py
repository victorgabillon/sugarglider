"""Lazy request-scoped GraphHopper path-option pool."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from hashlib import sha256
from time import perf_counter

from sugarglider.analysis.route import (
    canonical_edge_traversals,
    haversine_distance_m,
    project_geometry_edges,
)
from sugarglider.domain.models import Coordinate, PathDetailSegment
from sugarglider.planning.budget import SearchPhase
from sugarglider.planning.context import PlanningSearchContext
from sugarglider.planning.diagnostics import CacheDiagnostics
from sugarglider.planning.optimization.diagnostics import (
    GlobalOptimizationDiagnostics,
)
from sugarglider.planning.optimization.models import (
    GlobalOptimizationSettings,
    OptimizationAnchor,
    OptimizationSource,
    PathOption,
    PathOptionSourceKind,
)
from sugarglider.planning.profile_quality import profile_quality_components
from sugarglider.planning.profiles import RoutingProfileId
from sugarglider.planning.routing_gateway import SearchBudgetExhaustedError
from sugarglider.routing.backend import (
    CorridorAvoidanceArea,
    GraphHopperRoutingCapabilities,
    RoutedPath,
)
from sugarglider.routing.errors import RoutingError
from sugarglider.routing.result import RouteResultFactory

type _PathKey = tuple[str, str, str, float, float, float, float]
_ROUTE_REQUEST_TIMEOUT_S = 10.0


class LazyPathPool:
    """Seed source legs and lazily request bounded cached alternatives."""

    def __init__(
        self,
        *,
        context: PlanningSearchContext,
        profile: RoutingProfileId,
        result_factory: RouteResultFactory,
        settings: GlobalOptimizationSettings,
        diagnostics: GlobalOptimizationDiagnostics,
        wall_clock: Callable[[], float] = perf_counter,
        wall_deadline: float | None = None,
        enforce_wall_deadline: bool = True,
    ) -> None:
        self._context = context
        self._profile = profile
        self._result_factory = result_factory
        self._settings = settings
        self._diagnostics = diagnostics
        self._wall_clock = wall_clock
        self._wall_deadline = (
            wall_deadline
            if wall_deadline is not None
            else wall_clock() + settings.optimizer_total_wall_time_limit_s
        )
        self._enforce_wall_deadline = enforce_wall_deadline
        self._options: dict[_PathKey, dict[str, PathOption]] = {}
        self._queried: set[_PathKey] = set()
        self._negative: set[_PathKey] = set()
        self._avoidance_queried: set[tuple[_PathKey, str, float]] = set()

    @property
    def capabilities(self) -> GraphHopperRoutingCapabilities:
        return self._context.routes.capabilities

    def known_options_for(
        self,
        from_anchor: OptimizationAnchor,
        to_anchor: OptimizationAnchor,
    ) -> tuple[PathOption, ...]:
        return self._ordered(_key(from_anchor, to_anchor, self._profile))

    def begin_time_bounded_alns(self) -> None:
        """Apply the legacy absolute deadline only to optional ALNS work."""
        self._enforce_wall_deadline = True

    def seed_source(self, source: OptimizationSource) -> tuple[PathOption, ...]:
        """Split an existing complete routed path into authoritative source legs."""
        segments = split_source_path(source.routed_path, len(source.anchors))
        if segments is None:
            return ()
        return tuple(
            self.insert(
                from_anchor=source.anchors[index],
                to_anchor=source.anchors[index + 1],
                profile=source.routing_profile,
                path=segment,
                source_kind="source_leg",
            )
            for index, segment in enumerate(segments)
        )

    def insert(
        self,
        *,
        from_anchor: OptimizationAnchor,
        to_anchor: OptimizationAnchor,
        profile: RoutingProfileId,
        path: RoutedPath,
        source_kind: PathOptionSourceKind,
    ) -> PathOption:
        """Insert one GraphHopper path with deterministic identity and ordering."""
        option = _path_option(
            from_anchor=from_anchor,
            to_anchor=to_anchor,
            profile=profile,
            path=path,
            source_kind=source_kind,
            result_factory=self._result_factory,
        )
        key = _key(from_anchor, to_anchor, profile)
        values = self._options.setdefault(key, {})
        values.setdefault(option.id, option)
        self._trim(key)
        self._diagnostics.unique_path_options = sum(
            len(options) for options in self._options.values()
        )
        return values.get(option.id, option)

    def discard(self, option_id: str) -> None:
        """Release one transient evaluation option without touching route caches."""
        empty: list[_PathKey] = []
        for key, values in self._options.items():
            values.pop(option_id, None)
            if not values:
                empty.append(key)
        for key in empty:
            del self._options[key]
        self._diagnostics.unique_path_options = sum(
            len(options) for options in self._options.values()
        )

    async def options_for(
        self,
        from_anchor: OptimizationAnchor,
        to_anchor: OptimizationAnchor,
        *,
        source_kind: PathOptionSourceKind = "lazy_move_leg",
        request_alternatives: bool = False,
    ) -> tuple[PathOption, ...]:
        """Return known options, lazily asking only the shared gateway on a miss."""
        profile = self._profile
        key = _key(from_anchor, to_anchor, profile)
        known = self._ordered(key)
        should_query = key not in self._queried and (
            not known
            or (
                request_alternatives
                and len(known) < self._settings.maximum_path_options_per_directed_pair
            )
        )
        if not should_query:
            if key in self._negative:
                self._diagnostics.graphhopper_negative_cache_hits += 1
            return known
        if (
            self._diagnostics.graphhopper_calls_used
            >= self._settings.maximum_uncached_global_optimizer_calls
        ):
            if (
                self._diagnostics.graphhopper_calls_used
                >= self._settings.maximum_uncached_global_optimizer_calls
            ):
                self._diagnostics.budget_exhausted = True
            return known
        timeout_s = self._request_timeout_s()
        if timeout_s is None:
            self._diagnostics.time_limit_reached = True
            return known
        self._queried.add(key)
        self._diagnostics.lazy_path_requests += 1
        self._diagnostics.path_requests += 1
        before = self._context.routes.cache_snapshot()
        started = perf_counter()
        paths: tuple[RoutedPath, ...] = ()
        budget_rejected = False
        routing_failed = False
        try:
            async with asyncio.timeout(timeout_s):
                paths = await self._context.routes.alternative_routes(
                    from_anchor.coordinate,
                    to_anchor.coordinate,
                    profile,
                    max_paths=(self._settings.maximum_path_options_per_directed_pair),
                    max_weight_factor=1.8,
                    max_share_factor=0.7,
                    phase=SearchPhase.GLOBAL_OPTIMIZATION,
                )
        except TimeoutError:
            self._diagnostics.time_limit_reached = True
            routing_failed = True
        except SearchBudgetExhaustedError:
            self._diagnostics.budget_exhausted = True
            budget_rejected = True
        except RoutingError:
            self._record_negative(key)
            routing_failed = True
        finally:
            self._diagnostics.routing_wait_time_ms += (perf_counter() - started) * 1_000
        after = self._context.routes.cache_snapshot()
        self._diagnostics.graphhopper_cache_hits += max(
            0, after.hit_count - before.hit_count
        )
        self._diagnostics.graphhopper_calls_used += max(
            0, after.backend_call_count - before.backend_call_count
        )
        if budget_rejected or routing_failed:
            return known
        if not paths:
            self._record_negative(key)
            return known
        self._diagnostics.lazy_paths_returned += len(paths)
        for index, path in enumerate(_ordered_paths(paths)):
            kind: PathOptionSourceKind = (
                source_kind
                if source_kind in {"spur_connector", "relocation_connector"}
                else ("shortest" if index == 0 else "alternative")
            )
            self.insert(
                from_anchor=from_anchor,
                to_anchor=to_anchor,
                profile=profile,
                path=path,
                source_kind=kind,
            )
        return self._ordered(key)

    async def avoiding_options_for(
        self,
        from_anchor: OptimizationAnchor,
        to_anchor: OptimizationAnchor,
        area: CorridorAvoidanceArea,
        *,
        priority_multiplier: float,
    ) -> tuple[PathOption, ...]:
        """Request one cached custom-model alternative batch when supported."""
        key = _key(from_anchor, to_anchor, self._profile)
        query_key = (key, area.id, priority_multiplier)
        if query_key in self._avoidance_queried:
            return ()
        if (
            not self.capabilities.alternative_route_with_custom_model
            or self._diagnostics.graphhopper_calls_used
            >= self._settings.maximum_uncached_global_optimizer_calls
        ):
            return ()
        timeout_s = self._request_timeout_s()
        if timeout_s is None:
            self._diagnostics.time_limit_reached = True
            return ()
        self._avoidance_queried.add(query_key)
        self._diagnostics.path_requests += 1
        self._diagnostics.lazy_path_requests += 1
        before = self._context.routes.cache_snapshot()
        started = perf_counter()
        try:
            async with asyncio.timeout(timeout_s):
                paths = await self._context.routes.alternative_routes_avoiding_corridor(
                    from_anchor.coordinate,
                    to_anchor.coordinate,
                    self._profile,
                    area,
                    priority_multiplier=priority_multiplier,
                    max_paths=self._settings.maximum_connector_options_per_rejoin,
                    max_weight_factor=1.8,
                    max_share_factor=0.7,
                    phase=SearchPhase.GLOBAL_OPTIMIZATION,
                )
        except TimeoutError:
            self._diagnostics.time_limit_reached = True
            return ()
        except SearchBudgetExhaustedError:
            self._diagnostics.budget_exhausted = True
            return ()
        except RoutingError:
            return ()
        finally:
            self._diagnostics.routing_wait_time_ms += (perf_counter() - started) * 1_000
            self._record_cache_delta(before)
        self._diagnostics.lazy_paths_returned += len(paths)
        return tuple(
            self.insert(
                from_anchor=from_anchor,
                to_anchor=to_anchor,
                profile=self._profile,
                path=path,
                source_kind="avoidance_connector",
            )
            for path in _ordered_paths(paths)
        )

    async def guide_option_for(
        self,
        from_anchor: OptimizationAnchor,
        to_anchor: OptimizationAnchor,
        guide: Coordinate,
        *,
        strategy: str,
        maximum_snap_distance_m: float,
    ) -> tuple[PathOption | None, bool]:
        """Route one internal via point through the shared cache and budget."""
        if not self.capabilities.internal_via_points:
            return None, False
        if (
            self._diagnostics.graphhopper_calls_used
            >= self._settings.maximum_uncached_global_optimizer_calls
        ):
            self._diagnostics.budget_exhausted = True
            return None, False
        timeout_s = self._request_timeout_s()
        if timeout_s is None:
            self._diagnostics.time_limit_reached = True
            return None, False
        self._diagnostics.path_requests += 1
        self._diagnostics.lazy_path_requests += 1
        before = self._context.routes.cache_snapshot()
        started = perf_counter()
        try:
            async with asyncio.timeout(timeout_s):
                path = await self._context.routes.route(
                    (from_anchor.coordinate, guide, to_anchor.coordinate),
                    self._profile,
                    pass_through=True,
                    phase=SearchPhase.GLOBAL_OPTIMIZATION,
                    custom_options=(("internal_strategy", strategy),),
                )
        except TimeoutError:
            self._diagnostics.time_limit_reached = True
            return None, False
        except SearchBudgetExhaustedError:
            self._diagnostics.budget_exhausted = True
            return None, False
        except RoutingError:
            return None, False
        finally:
            self._diagnostics.routing_wait_time_ms += (perf_counter() - started) * 1_000
            self._record_cache_delta(before)
        snapped = path.snapped_points
        if snapped is None or len(snapped) != 3:
            return None, True
        snap_distance = haversine_distance_m(
            (guide.lon, guide.lat),
            snapped[1],
        )
        if snap_distance > maximum_snap_distance_m:
            return None, True
        self._diagnostics.lazy_paths_returned += 1
        path = RoutedPath(
            distance_m=path.distance_m,
            duration_ms=path.duration_ms,
            ascend_m=path.ascend_m,
            descend_m=path.descend_m,
            geometry=path.geometry,
            snapped_points=(path.geometry[0], path.geometry[-1]),
            details=path.details,
        )
        return (
            self.insert(
                from_anchor=from_anchor,
                to_anchor=to_anchor,
                profile=self._profile,
                path=path,
                source_kind="guide_connector",
            ),
            False,
        )

    @property
    def unique_option_count(self) -> int:
        return sum(len(options) for options in self._options.values())

    def _ordered(self, key: _PathKey) -> tuple[PathOption, ...]:
        return tuple(
            sorted(
                self._options.get(key, {}).values(),
                key=lambda option: (
                    option.distance_m,
                    tuple(
                        (
                            edge.physical_edge_key,
                            edge.direction,
                            round(edge.distance_m, 6),
                        )
                        for edge in option.directed_edges
                    ),
                    option.id,
                ),
            )
        )

    def _trim(self, key: _PathKey) -> None:
        values = self._ordered(key)
        limit = self._settings.maximum_path_options_per_directed_pair
        if len(values) <= limit:
            return
        source = next(
            (option for option in values if option.source_kind == "source_leg"),
            None,
        )
        reference = source or values[0]
        retained: list[PathOption] = []

        def add(option: PathOption) -> None:
            if (
                option.id not in {value.id for value in retained}
                and len(retained) < limit
            ):
                retained.append(option)

        if source is not None:
            add(source)
        add(values[0])
        add(
            min(
                values,
                key=lambda option: (
                    _physical_overlap_m(option, reference),
                    option.distance_m,
                    option.id,
                ),
            )
        )
        for option in sorted(
            values,
            key=lambda value: (
                value.distance_m,
                _physical_overlap_m(value, reference),
                value.id,
            ),
        ):
            add(option)
        self._options[key] = {option.id: option for option in retained}

    def _record_negative(self, key: _PathKey) -> None:
        self._diagnostics.negative_path_results += 1
        if len(self._negative) < self._settings.maximum_negative_cache_entries:
            self._negative.add(key)

    def _record_cache_delta(self, before: CacheDiagnostics) -> None:
        after = self._context.routes.cache_snapshot()
        self._diagnostics.graphhopper_cache_hits += max(
            0, after.hit_count - before.hit_count
        )
        self._diagnostics.graphhopper_calls_used += max(
            0,
            after.backend_call_count - before.backend_call_count,
        )

    def _request_timeout_s(self) -> float | None:
        if not self._enforce_wall_deadline:
            return _ROUTE_REQUEST_TIMEOUT_S
        remaining = self._wall_deadline - self._wall_clock()
        return remaining if remaining > 0 else None


def split_source_path(
    path: RoutedPath,
    anchor_count: int,
) -> tuple[RoutedPath, ...] | None:
    """Split one GraphHopper multipoint path at its authoritative snapped points."""
    if anchor_count < 2:
        return () if anchor_count == 1 else None
    snapped = path.snapped_points
    if snapped is None or len(snapped) != anchor_count:
        return None
    indices = _snapped_geometry_indices(path.geometry, snapped)
    if indices is None:
        return None
    projection = project_geometry_edges(
        geometry=path.geometry,
        route_distance_m=path.distance_m,
        path_details=path.details,
    )
    distances = tuple(
        sum(projection.edges[index].distance_m for index in range(start, end))
        for start, end in zip(indices, indices[1:], strict=False)
    )
    durations = _integer_shares(path.duration_ms, distances)
    return tuple(
        RoutedPath(
            distance_m=distance,
            duration_ms=duration,
            ascend_m=None,
            descend_m=None,
            geometry=path.geometry[start : end + 1],
            snapped_points=(path.geometry[start], path.geometry[end]),
            details=_slice_details(path.details, start=start, end=end),
        )
        for (start, end), distance, duration in zip(
            zip(indices, indices[1:], strict=False),
            distances,
            durations,
            strict=True,
        )
    )


def _path_option(
    *,
    from_anchor: OptimizationAnchor,
    to_anchor: OptimizationAnchor,
    profile: RoutingProfileId,
    path: RoutedPath,
    source_kind: PathOptionSourceKind,
    result_factory: RouteResultFactory,
) -> PathOption:
    projection = project_geometry_edges(
        geometry=path.geometry,
        route_distance_m=path.distance_m,
        path_details=path.details,
    )
    traversals = canonical_edge_traversals(projection.edges)
    route = result_factory.create(
        name="Optimization path option",
        path=path,
        input_point_count=2,
        routing_profile=profile,
    )
    profile_penalty, _components, severe = profile_quality_components(route)
    digest = sha256(
        repr(
            (
                profile,
                from_anchor.id,
                to_anchor.id,
                tuple(
                    (
                        edge.physical_edge_key,
                        edge.direction,
                        round(edge.distance_m, 6),
                    )
                    for edge in traversals
                ),
                tuple(path.geometry),
            )
        ).encode()
    ).hexdigest()[:20]
    known_distance = sum(
        edge.distance_m for edge in projection.edges if edge.detail("edge_id")[0]
    )
    coverage = known_distance / path.distance_m if path.distance_m > 0 else 0.0
    return PathOption(
        id=f"path/{digest}",
        from_anchor_id=from_anchor.id,
        to_anchor_id=to_anchor.id,
        from_coordinate=from_anchor.coordinate,
        to_coordinate=to_anchor.coordinate,
        routing_profile=profile,
        routed_path=path,
        directed_edges=traversals,
        undirected_edge_keys=tuple(
            traversal.physical_edge_key for traversal in traversals
        ),
        distance_m=path.distance_m,
        path_detail_quality=(
            ("edge_id_coverage", coverage),
            ("profile_penalty", profile_penalty),
        ),
        severe_profile_incompatibility=severe,
        warnings=route.analysis.warnings,
        source_kind=source_kind,
    )


def _key(
    left: OptimizationAnchor,
    right: OptimizationAnchor,
    profile: RoutingProfileId,
) -> _PathKey:
    return (
        profile,
        left.id,
        right.id,
        left.coordinate.lat,
        left.coordinate.lon,
        right.coordinate.lat,
        right.coordinate.lon,
    )


def _ordered_paths(paths: tuple[RoutedPath, ...]) -> tuple[RoutedPath, ...]:
    return tuple(
        sorted(paths, key=lambda path: (path.distance_m, tuple(path.geometry)))
    )


def _physical_overlap_m(option: PathOption, reference: PathOption) -> float:
    reference_keys = frozenset(reference.undirected_edge_keys)
    return sum(
        traversal.distance_m
        for traversal in option.directed_edges
        if traversal.physical_edge_key in reference_keys
    )


def _snapped_geometry_indices(
    geometry: tuple[tuple[float, float], ...],
    snapped: tuple[tuple[float, float], ...],
) -> tuple[int, ...] | None:
    indices: list[int] = []
    cursor = 0
    for position, point in enumerate(snapped):
        start = cursor + int(position > 0)
        match = next(
            (
                index
                for index in range(start, len(geometry))
                if geometry[index] == point
            ),
            None,
        )
        if match is None:
            return None
        indices.append(match)
        cursor = match
    if any(left >= right for left, right in zip(indices, indices[1:], strict=False)):
        return None
    return tuple(indices)


def _slice_details(
    details: Mapping[str, tuple[PathDetailSegment, ...]],
    *,
    start: int,
    end: int,
) -> dict[str, tuple[PathDetailSegment, ...]]:
    values: dict[str, tuple[PathDetailSegment, ...]] = {}
    for name, segments in sorted(dict(details).items()):
        sliced = tuple(
            PathDetailSegment(
                from_index=max(segment.from_index, start) - start,
                to_index=min(segment.to_index, end) - start,
                value=segment.value,
            )
            for segment in segments
            if segment.from_index < end and segment.to_index > start
        )
        if sliced:
            values[name] = sliced
    return values


def _integer_shares(total: int, distances: tuple[float, ...]) -> tuple[int, ...]:
    distance_total = sum(distances)
    if not distances:
        return ()
    if distance_total <= 0:
        return (*((0,) * (len(distances) - 1)), total)
    values = [int(total * distance / distance_total) for distance in distances[:-1]]
    return (*values, total - sum(values))
