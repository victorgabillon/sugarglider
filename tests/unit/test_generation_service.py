"""Deterministic generation orchestration using a fake routing backend."""

from collections.abc import Mapping

import pytest

from sugarglider.domain.generation import RouteGenerationRequest
from sugarglider.domain.models import Coordinate, PathDetailSegment
from sugarglider.generation.low_overlap import LowOverlapSettings
from sugarglider.generation.service import RouteGenerationService
from sugarglider.routing.backend import RoutedPath
from sugarglider.routing.graphhopper import (
    RoutingPointError,
    RoutingTimeoutError,
    RoutingUnavailableError,
)


class FakeRoutingBackend:
    def __init__(
        self,
        *,
        baseline_distance_m: float = 22_500,
        static_proposals: bool = False,
        fail_proposals: bool = False,
        fail_candidates: bool = False,
        snap_shift_degrees: float = 0.0,
        omit_snapped_points: bool = False,
        truncate_snapped_points: bool = False,
    ) -> None:
        self.baseline_distance_m = baseline_distance_m
        self.static_proposals = static_proposals
        self.fail_proposals = fail_proposals
        self.fail_candidates = fail_candidates
        self.snap_shift_degrees = snap_shift_degrees
        self.omit_snapped_points = omit_snapped_points
        self.truncate_snapped_points = truncate_snapped_points
        self.round_trip_calls = 0
        self.candidate_route_calls = 0
        self.candidate_sequences: list[tuple[Coordinate, ...]] = []
        self.pass_through_values: list[bool] = []
        self.alternative_route_calls = 0

    async def route(
        self,
        points: tuple[Coordinate, ...],
        profile: str = "hike",
        *,
        pass_through: bool = False,
    ) -> RoutedPath:
        if not pass_through:
            return self._path(points, self.baseline_distance_m, edge_offset=1)
        self.candidate_route_calls += 1
        self.candidate_sequences.append(points)
        self.pass_through_values.append(pass_through)
        if self.fail_candidates:
            raise RoutingPointError("candidate cannot be routed")
        distance = (
            self.baseline_distance_m + 14_000 + (self.candidate_route_calls % 5) * 1_000
        )
        return self._path(
            points,
            distance,
            edge_offset=100 * self.candidate_route_calls,
            shift_snaps=self.snap_shift_degrees,
            omit_snaps=self.omit_snapped_points,
            truncate_snaps=self.truncate_snapped_points,
        )

    async def round_trip(
        self,
        start: Coordinate,
        distance_m: float,
        seed: int,
        profile: str = "hike",
    ) -> RoutedPath:
        self.round_trip_calls += 1
        if self.fail_proposals:
            raise RoutingPointError("proposal failed")
        variation = 0.0 if self.static_proposals else (seed % 97) * 0.000001
        radius = 0.02 if self.static_proposals else max(distance_m / 500_000, 0.005)
        geometry = (
            (start.lon, start.lat),
            (start.lon + radius + variation, start.lat),
            (start.lon + radius, start.lat + radius),
            (start.lon, start.lat + radius + variation),
            (start.lon, start.lat),
        )
        return RoutedPath(
            distance_m=distance_m,
            duration_ms=1,
            ascend_m=None,
            descend_m=None,
            geometry=geometry,
            snapped_points=((start.lon, start.lat),),
            details={},
        )

    async def alternative_routes(
        self,
        start: Coordinate,
        end: Coordinate,
        profile: str = "hike",
        *,
        max_paths: int = 3,
        max_weight_factor: float = 1.6,
        max_share_factor: float = 0.5,
    ) -> tuple[RoutedPath, ...]:
        self.alternative_route_calls += 1
        return (
            self._path(
                (start, end),
                1_000,
                edge_offset=50_000 + self.alternative_route_calls * 10,
            ),
        )

    @staticmethod
    def _path(
        points: tuple[Coordinate, ...],
        distance_m: float,
        *,
        edge_offset: int,
        shift_snaps: float = 0.0,
        omit_snaps: bool = False,
        truncate_snaps: bool = False,
    ) -> RoutedPath:
        geometry = tuple((point.lon, point.lat) for point in points)
        details: Mapping[str, tuple[PathDetailSegment, ...]] = {
            "edge_id": tuple(
                PathDetailSegment(
                    from_index=index,
                    to_index=index + 1,
                    value=edge_offset + index,
                )
                for index in range(len(geometry) - 1)
            ),
            "surface": (
                PathDetailSegment(
                    from_index=0, to_index=len(geometry) - 1, value="GRAVEL"
                ),
            ),
            "road_class": (
                PathDetailSegment(
                    from_index=0, to_index=len(geometry) - 1, value="PATH"
                ),
            ),
        }
        snapped = (
            None
            if omit_snaps
            else tuple(
                (point.lon + shift_snaps, point.lat + shift_snaps) for point in points
            )
        )
        if snapped is not None and truncate_snaps:
            snapped = snapped[:-1]
        return RoutedPath(
            distance_m=distance_m,
            duration_ms=1,
            ascend_m=None,
            descend_m=None,
            geometry=geometry,
            snapped_points=snapped,
            details=details,
        )


class OrderAwareRoutingBackend(FakeRoutingBackend):
    """Return a retracing fixed route and one signature for all reordered loops."""

    def __init__(self) -> None:
        super().__init__(baseline_distance_m=41_000)
        self.order_sequences: list[tuple[str | None, ...]] = []

    async def route(
        self,
        points: tuple[Coordinate, ...],
        profile: str = "hike",
        *,
        pass_through: bool = False,
    ) -> RoutedPath:
        names = tuple(point.name for point in points[:-1])
        self.order_sequences.append(names)
        fixed = names == ("p0", "p1", "p2", "p3")
        if not pass_through or fixed:
            geometry = ((0.0, 0.0), (0.01, 0.0), (0.02, 0.0), (0.01, 0.0), (0.0, 0.0))
            edge_ids = (1, 2, 2, 1)
        else:
            geometry = ((0.0, 0.0), (0.01, 0.0), (0.01, 0.01), (0.0, 0.01), (0.0, 0.0))
            edge_ids = (10, 11, 12, 13)
        return RoutedPath(
            distance_m=41_000,
            duration_ms=1,
            ascend_m=None,
            descend_m=None,
            geometry=geometry,
            snapped_points=tuple((point.lon, point.lat) for point in points),
            details={
                "edge_id": tuple(
                    PathDetailSegment(
                        from_index=index,
                        to_index=index + 1,
                        value=edge_id,
                    )
                    for index, edge_id in enumerate(edge_ids)
                )
            },
        )


class SequencedOrderRoutingBackend(FakeRoutingBackend):
    """Return configured order distances and track which order receives detours."""

    def __init__(
        self,
        *,
        baseline_distance_m: float,
        order_distances_m: tuple[float, ...],
        fail_orders: bool = False,
        malformed_orders: bool = False,
    ) -> None:
        super().__init__(baseline_distance_m=baseline_distance_m)
        self.order_distances_m = order_distances_m
        self.fail_orders = fail_orders
        self.malformed_orders = malformed_orders
        self.order_evaluations = 0
        self.expandable_order: tuple[str, ...] | None = None
        self.detour_orders: list[tuple[str, ...]] = []

    async def route(
        self,
        points: tuple[Coordinate, ...],
        profile: str = "hike",
        *,
        pass_through: bool = False,
    ) -> RoutedPath:
        if not pass_through:
            return self._path(points, self.baseline_distance_m, edge_offset=1)
        mandatory_names = tuple(
            point.name or ""
            for point in points
            if point.name is not None and not point.name.startswith("Generated detour")
        )[:-1]
        has_optional_points = any(
            point.name is not None and point.name.startswith("Generated detour")
            for point in points
        )
        if has_optional_points:
            self.detour_orders.append(mandatory_names)
            return self._path(
                points,
                41_000,
                edge_offset=10_000 + len(self.detour_orders) * 100,
            )

        self.order_evaluations += 1
        if self.fail_orders:
            raise RoutingPointError("order cannot be routed")
        distance = (
            self.order_distances_m[self.order_evaluations - 1]
            if self.order_evaluations <= len(self.order_distances_m)
            else 46_000 + self.order_evaluations * 100
        )
        if distance == 20_000:
            self.expandable_order = mandatory_names
        path = self._path(
            points,
            distance,
            edge_offset=100 * self.order_evaluations,
        )
        if self.malformed_orders and path.snapped_points is not None:
            return RoutedPath(
                distance_m=path.distance_m,
                duration_ms=path.duration_ms,
                ascend_m=path.ascend_m,
                descend_m=path.descend_m,
                geometry=path.geometry,
                snapped_points=path.snapped_points[:-1],
                details=path.details,
            )
        return path


class LowOverlapRoutingBackend(FakeRoutingBackend):
    """Expose a repeated standard loop and distinct graph-routed leg alternatives."""

    def __init__(self, *, alternative_error: Exception | None = None) -> None:
        super().__init__(baseline_distance_m=41_000)
        self.alternative_error = alternative_error
        self.alternative_legs: list[tuple[Coordinate, Coordinate]] = []

    async def route(
        self,
        points: tuple[Coordinate, ...],
        profile: str = "hike",
        *,
        pass_through: bool = False,
    ) -> RoutedPath:
        path = self._path(points, 41_000, edge_offset=1)
        return RoutedPath(
            distance_m=path.distance_m,
            duration_ms=path.duration_ms,
            ascend_m=path.ascend_m,
            descend_m=path.descend_m,
            geometry=path.geometry,
            snapped_points=path.snapped_points,
            details={
                **path.details,
                "edge_id": tuple(
                    PathDetailSegment(
                        from_index=index,
                        to_index=index + 1,
                        value=1,
                    )
                    for index in range(len(path.geometry) - 1)
                ),
            },
        )

    async def alternative_routes(
        self,
        start: Coordinate,
        end: Coordinate,
        profile: str = "hike",
        *,
        max_paths: int = 3,
        max_weight_factor: float = 1.6,
        max_share_factor: float = 0.5,
    ) -> tuple[RoutedPath, ...]:
        self.alternative_route_calls += 1
        self.alternative_legs.append((start, end))
        if self.alternative_error is not None:
            raise self.alternative_error
        return (
            self._path((start, end), 20_500, edge_offset=1),
            self._path(
                (start, end),
                20_500,
                edge_offset=100 + self.alternative_route_calls,
            ),
        )


class TradeoffLowOverlapRoutingBackend(LowOverlapRoutingBackend):
    """Lower repetition only by introducing immediate reversal."""

    async def route(
        self,
        points: tuple[Coordinate, ...],
        profile: str = "hike",
        *,
        pass_through: bool = False,
    ) -> RoutedPath:
        start = (points[0].lon, points[0].lat)
        required = (points[1].lon, points[1].lat)
        outward_midpoint = (
            (start[0] + required[0]) / 2,
            (start[1] + required[1]) / 2,
        )
        return_midpoint = (required[0] + 0.02, start[1] + 0.02)
        geometry = (start, outward_midpoint, required, return_midpoint, start)
        return RoutedPath(
            distance_m=41_000,
            duration_ms=1,
            ascend_m=None,
            descend_m=None,
            geometry=geometry,
            snapped_points=tuple((point.lon, point.lat) for point in points),
            details={
                "edge_id": tuple(
                    PathDetailSegment(
                        from_index=index,
                        to_index=index + 1,
                        value=edge_id,
                    )
                    for index, edge_id in enumerate((1, 2, 1, 2))
                )
            },
        )

    async def alternative_routes(
        self,
        start: Coordinate,
        end: Coordinate,
        profile: str = "hike",
        *,
        max_paths: int = 3,
        max_weight_factor: float = 1.6,
        max_share_factor: float = 0.5,
    ) -> tuple[RoutedPath, ...]:
        self.alternative_route_calls += 1
        self.alternative_legs.append((start, end))
        midpoint = (
            (start.lon + end.lon) / 2,
            (start.lat + end.lat) / 2,
        )
        edge_ids = (10, 11) if self.alternative_route_calls == 1 else (11, 12)
        geometry = ((start.lon, start.lat), midpoint, (end.lon, end.lat))
        return (
            RoutedPath(
                distance_m=20_500,
                duration_ms=1,
                ascend_m=None,
                descend_m=None,
                geometry=geometry,
                snapped_points=((start.lon, start.lat), (end.lon, end.lat)),
                details={
                    "edge_id": tuple(
                        PathDetailSegment(
                            from_index=index,
                            to_index=index + 1,
                            value=edge_id,
                        )
                        for index, edge_id in enumerate(edge_ids)
                    )
                },
            ),
        )


class BacktrackingOnlyTradeoffBackend(LowOverlapRoutingBackend):
    """Lower backtracking only by accepting more total repeated edges."""

    async def alternative_routes(
        self,
        start: Coordinate,
        end: Coordinate,
        profile: str = "hike",
        *,
        max_paths: int = 3,
        max_weight_factor: float = 1.6,
        max_share_factor: float = 0.5,
    ) -> tuple[RoutedPath, ...]:
        self.alternative_route_calls += 1
        self.alternative_legs.append((start, end))
        direction = 1 if self.alternative_route_calls == 1 else -1
        mid_lon = (start.lon + end.lon) / 2
        mid_lat = (start.lat + end.lat) / 2
        geometry = (
            (start.lon, start.lat),
            (start.lon + 0.02 * direction, start.lat),
            (mid_lon, mid_lat + 0.02 * direction),
            (end.lon - 0.02 * direction, end.lat),
            (end.lon, end.lat),
        )
        return (
            RoutedPath(
                distance_m=20_500,
                duration_ms=1,
                ascend_m=None,
                descend_m=None,
                geometry=geometry,
                snapped_points=((start.lon, start.lat), (end.lon, end.lat)),
                details={
                    "edge_id": tuple(
                        PathDetailSegment(
                            from_index=index,
                            to_index=index + 1,
                            value=edge_id,
                        )
                        for index, edge_id in enumerate((1, 2, 1, 2))
                    )
                },
            ),
        )


def generation_request(
    *, target: float = 41_000, tolerance: float = 2_000, candidates: int = 3
) -> RouteGenerationRequest:
    return RouteGenerationRequest(
        name="Generated test",
        points=[
            Coordinate(lat=48.0, lon=2.0, name="start"),
            Coordinate(lat=48.1, lon=2.1, name="required"),
        ],
        target_distance_m=target,
        tolerance_m=tolerance,
        candidate_count=candidates,
        seed=42,
    )


def optimized_order_request() -> RouteGenerationRequest:
    return RouteGenerationRequest(
        name="Optimized order",
        points=[
            Coordinate(lat=0, lon=0, name="p0"),
            Coordinate(lat=0, lon=2, name="p1"),
            Coordinate(lat=1, lon=0, name="p2"),
            Coordinate(lat=1, lon=2, name="p3"),
        ],
        target_distance_m=41_000,
        tolerance_m=2_000,
        candidate_count=3,
        seed=42,
        point_order_mode="optimize_loop",
    )


@pytest.mark.asyncio
async def test_baseline_above_target_is_infeasible_with_useful_baseline() -> None:
    backend = FakeRoutingBackend(baseline_distance_m=44_000)
    result = await RouteGenerationService(backend).generate(generation_request())
    assert result.search.status == "infeasible"
    assert result.baseline.summary.distance_m == 44_000
    assert result.candidates == ()
    assert result.search.warnings == ("mandatory_route_exceeds_target_tolerance",)
    assert backend.round_trip_calls == 0


@pytest.mark.asyncio
async def test_infeasible_low_overlap_request_keeps_metrics_unknown() -> None:
    request = generation_request().model_copy(
        update={"path_selection_mode": "low_overlap"}
    )
    result = await RouteGenerationService(
        FakeRoutingBackend(baseline_distance_m=44_000)
    ).generate(request)
    assert result.search.status == "infeasible"
    assert result.search.low_overlap_requested
    assert result.search.low_overlap_request_budget == 48
    assert result.search.pre_low_overlap_repeated_share is None
    assert result.search.best_low_overlap_repeated_share is None


@pytest.mark.asyncio
async def test_baseline_already_at_target_is_a_candidate() -> None:
    backend = FakeRoutingBackend(baseline_distance_m=41_000)
    result = await RouteGenerationService(backend).generate(generation_request())
    assert result.search.status == "within_tolerance"
    assert len(result.candidates) == 1
    assert result.candidates[0].optional_points == ()
    assert result.candidates[0].target_error_m == 0


@pytest.mark.asyncio
async def test_below_target_generates_routes_and_preserves_required_order() -> None:
    backend = FakeRoutingBackend()
    request = generation_request()
    result = await RouteGenerationService(backend, max_evaluations=10).generate(request)
    assert result.candidates
    assert all(backend.pass_through_values)
    required = tuple((point.lat, point.lon) for point in request.points)
    for sequence in backend.candidate_sequences:
        positions = [(point.lat, point.lon) for point in sequence]
        cursor = 0
        for position in positions:
            if cursor < len(required) and position == required[cursor]:
                cursor += 1
        assert cursor == len(required)
        assert positions[0] == positions[-1]
    assert all(
        [visit.original_index for visit in candidate.required_point_order] == [0, 1]
        for candidate in result.candidates
    )
    assert result.search.evaluated_candidate_count <= 10


@pytest.mark.asyncio
async def test_generated_input_count_excludes_internal_waypoints() -> None:
    request = generation_request()
    result = await RouteGenerationService(
        FakeRoutingBackend(), max_evaluations=1
    ).generate(request)

    generated = result.candidates[0]
    assert request.required_point_count == 2
    assert generated.optional_points
    assert generated.route.snapped_points is not None
    assert len(generated.route.snapped_points) > request.required_point_count
    assert generated.route.summary.input_point_count == 2
    assert generated.construction == "round_trip_detour"
    assert generated.routing_points[0] == request.supplied_required_points[0]
    assert generated.routing_points[-1] != generated.routing_points[0]
    assert all(point in generated.routing_points for point in generated.optional_points)


@pytest.mark.asyncio
async def test_search_budget_is_never_exceeded_and_is_exposed() -> None:
    backend = FakeRoutingBackend()
    result = await RouteGenerationService(backend, max_evaluations=2).generate(
        generation_request()
    )
    assert result.search.evaluated_candidate_count == 2
    assert backend.candidate_route_calls == 2
    assert result.search.search_budget_exhausted
    assert "search_budget_exhausted" in result.search.warnings


@pytest.mark.asyncio
async def test_exact_point_sequences_are_cached() -> None:
    backend = FakeRoutingBackend(static_proposals=True)
    result = await RouteGenerationService(backend, max_evaluations=48).generate(
        generation_request()
    )
    assert backend.round_trip_calls >= 10
    assert result.search.evaluated_candidate_count == 2
    assert backend.candidate_route_calls == 2


@pytest.mark.asyncio
async def test_proposal_failures_do_not_consume_full_evaluation_budget() -> None:
    backend = FakeRoutingBackend(fail_proposals=True)
    result = await RouteGenerationService(backend, max_evaluations=3).generate(
        generation_request()
    )
    assert result.candidates == ()
    assert result.search.round_trip_proposal_count == 10
    assert result.search.evaluated_candidate_count == 0
    assert not result.search.search_budget_exhausted


@pytest.mark.asyncio
async def test_candidate_routing_failures_have_no_straight_line_fallback() -> None:
    backend = FakeRoutingBackend(fail_candidates=True)
    result = await RouteGenerationService(backend, max_evaluations=4).generate(
        generation_request()
    )
    assert result.candidates == ()
    assert result.search.rejected_candidate_count == 4
    assert result.search.evaluated_candidate_count == 4


@pytest.mark.asyncio
async def test_optional_snap_below_threshold_is_accepted() -> None:
    backend = FakeRoutingBackend(snap_shift_degrees=0.0001)
    result = await RouteGenerationService(backend, max_evaluations=1).generate(
        generation_request()
    )
    assert result.candidates


@pytest.mark.asyncio
async def test_optional_snap_above_threshold_is_rejected() -> None:
    backend = FakeRoutingBackend(snap_shift_degrees=0.01)
    result = await RouteGenerationService(backend, max_evaluations=1).generate(
        generation_request()
    )
    assert result.candidates == ()
    assert result.search.rejected_candidate_count == 1


@pytest.mark.asyncio
async def test_missing_snapped_waypoints_rejects_candidate() -> None:
    backend = FakeRoutingBackend(omit_snapped_points=True)
    result = await RouteGenerationService(backend, max_evaluations=1).generate(
        generation_request()
    )
    assert result.candidates == ()
    assert result.search.rejected_candidate_count == 1


@pytest.mark.asyncio
async def test_malformed_snapped_waypoint_count_rejects_candidate() -> None:
    backend = FakeRoutingBackend(truncate_snapped_points=True)
    result = await RouteGenerationService(backend, max_evaluations=1).generate(
        generation_request()
    )
    assert result.candidates == ()
    assert result.search.rejected_candidate_count == 1


@pytest.mark.asyncio
async def test_fixed_inputs_are_byte_deterministic() -> None:
    request = generation_request()
    first = await RouteGenerationService(
        FakeRoutingBackend(), max_evaluations=6
    ).generate(request)
    second = await RouteGenerationService(
        FakeRoutingBackend(), max_evaluations=6
    ).generate(request)
    assert first.model_dump_json() == second.model_dump_json()


@pytest.mark.asyncio
async def test_explicit_shortest_mode_matches_omitted_default() -> None:
    default = generation_request()
    explicit = default.model_copy(update={"path_selection_mode": "shortest"})
    first = await RouteGenerationService(
        FakeRoutingBackend(), max_evaluations=6
    ).generate(default)
    second = await RouteGenerationService(
        FakeRoutingBackend(), max_evaluations=6
    ).generate(explicit)
    assert first.model_dump_json() == second.model_dump_json()


@pytest.mark.asyncio
async def test_fixed_mode_does_not_evaluate_alternative_orders() -> None:
    result = await RouteGenerationService(
        FakeRoutingBackend(), max_evaluations=2
    ).generate(generation_request())
    assert result.search.evaluated_order_count == 0
    assert result.candidates[0].required_point_order[0].original_index == 0
    assert not result.search.low_overlap_requested
    assert result.search.pre_low_overlap_repeated_share is None
    assert result.search.best_low_overlap_repeated_share is None
    assert result.search.pre_low_overlap_backtrack_share is None
    assert result.search.best_low_overlap_backtrack_share is None


@pytest.mark.asyncio
async def test_optimized_mode_preserves_all_indices_and_lowers_retracing() -> None:
    result = await RouteGenerationService(OrderAwareRoutingBackend()).generate(
        optimized_order_request()
    )
    for candidate in result.candidates:
        indices = [visit.original_index for visit in candidate.required_point_order]
        assert indices[0] == 0
        assert sorted(indices) == [0, 1, 2, 3]
        assert len(indices) == len(set(indices))
    assert result.search.evaluated_order_count > 1
    assert (
        result.search.best_order_repeated_share
        < result.search.fixed_order_repeated_share
    )
    assert (
        result.search.best_order_backtrack_share
        < result.search.fixed_order_backtrack_share
    )


@pytest.mark.asyncio
async def test_optimized_order_search_respects_one_full_route_budget() -> None:
    backend = OrderAwareRoutingBackend()
    result = await RouteGenerationService(backend, max_evaluations=2).generate(
        optimized_order_request()
    )
    assert result.search.evaluated_candidate_count == 2
    assert result.search.evaluated_order_count == 2
    assert result.search.search_budget_exhausted


@pytest.mark.asyncio
async def test_duplicate_optimized_routes_are_deduplicated_deterministically() -> None:
    request = optimized_order_request()
    first = await RouteGenerationService(OrderAwareRoutingBackend()).generate(request)
    second = await RouteGenerationService(OrderAwareRoutingBackend()).generate(request)
    assert len({candidate.signature for candidate in first.candidates}) == len(
        first.candidates
    )
    assert first.search.rejected_order_count > 0
    assert first.search.evaluated_order_count == (
        first.search.successful_order_count + first.search.rejected_order_count
    )
    assert first.model_dump_json() == second.model_dump_json()


@pytest.mark.asyncio
async def test_expandable_order_is_retained_before_infeasibility_pruning() -> None:
    backend = SequencedOrderRoutingBackend(
        baseline_distance_m=44_000,
        order_distances_m=(45_000, 46_000, 20_000),
    )
    result = await RouteGenerationService(backend, max_evaluations=48).generate(
        optimized_order_request()
    )

    assert result.search.status != "infeasible"
    assert backend.expandable_order is not None
    assert backend.round_trip_calls > 0
    assert backend.expandable_order in backend.detour_orders
    assert result.search.evaluated_candidate_count <= result.search.search_budget


@pytest.mark.asyncio
async def test_all_routed_orders_above_target_tolerance_remain_infeasible() -> None:
    backend = SequencedOrderRoutingBackend(
        baseline_distance_m=44_000,
        order_distances_m=(45_000, 46_000, 47_000),
    )
    result = await RouteGenerationService(backend).generate(optimized_order_request())
    assert result.search.status == "infeasible"
    assert result.candidates == ()
    assert backend.round_trip_calls == 0


@pytest.mark.asyncio
async def test_distinct_order_counter_outcomes_are_mutually_exclusive() -> None:
    backend = SequencedOrderRoutingBackend(
        baseline_distance_m=41_000,
        order_distances_m=(41_000,),
    )
    result = await RouteGenerationService(backend).generate(optimized_order_request())
    assert result.search.rejected_order_count == 0
    assert result.search.evaluated_order_count == result.search.successful_order_count


@pytest.mark.asyncio
async def test_routing_failure_order_counters_are_mutually_exclusive() -> None:
    backend = SequencedOrderRoutingBackend(
        baseline_distance_m=41_000,
        order_distances_m=(),
        fail_orders=True,
    )
    result = await RouteGenerationService(backend).generate(optimized_order_request())
    assert result.search.successful_order_count == 0
    assert result.search.evaluated_order_count == result.search.rejected_order_count


@pytest.mark.asyncio
async def test_malformed_snap_order_counters_are_mutually_exclusive() -> None:
    backend = SequencedOrderRoutingBackend(
        baseline_distance_m=41_000,
        order_distances_m=(41_000,),
        malformed_orders=True,
    )
    result = await RouteGenerationService(backend).generate(optimized_order_request())
    assert result.search.successful_order_count == 0
    assert result.search.evaluated_order_count == result.search.rejected_order_count


@pytest.mark.asyncio
async def test_low_overlap_refines_exact_routing_points_after_standard_search() -> None:
    backend = LowOverlapRoutingBackend()
    request = generation_request(candidates=3).model_copy(
        update={"path_selection_mode": "low_overlap"}
    )
    result = await RouteGenerationService(backend).generate(request)

    assert result.candidates[0].construction == "alternative_leg_beam"
    assert (
        result.candidates[0].required_point_order
        == result.candidates[-1].required_point_order
    )
    assert any(
        candidate.construction == "direct_order" for candidate in result.candidates
    )
    expected_points = request.supplied_required_points
    assert all(
        candidate.routing_points == expected_points for candidate in result.candidates
    )
    assert backend.alternative_legs == [
        (expected_points[0], expected_points[1]),
        (expected_points[1], expected_points[0]),
    ]
    assert result.search.evaluated_candidate_count == 0
    assert result.search.alternative_leg_request_count == 2
    assert result.search.alternative_path_count == 4
    assert result.search.low_overlap_refined_source_count == 1
    assert result.search.low_overlap_candidate_count > 0
    assert result.search.pre_low_overlap_repeated_share == pytest.approx(0.5)
    assert result.search.best_low_overlap_repeated_share == 0
    assert result.search.low_overlap_requested


@pytest.mark.asyncio
async def test_expected_leg_failure_keeps_standard_candidate() -> None:
    backend = LowOverlapRoutingBackend(
        alternative_error=RoutingPointError("leg failed")
    )
    request = generation_request().model_copy(
        update={"path_selection_mode": "low_overlap"}
    )
    result = await RouteGenerationService(backend).generate(request)
    assert result.candidates
    assert all(
        candidate.construction == "direct_order" for candidate in result.candidates
    )
    assert "low_overlap_no_complete_candidate" in result.search.warnings
    assert result.search.pre_low_overlap_repeated_share is not None
    assert (
        result.search.best_low_overlap_repeated_share
        == result.search.pre_low_overlap_repeated_share
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [RoutingTimeoutError("timed out"), RoutingUnavailableError("offline")],
)
async def test_global_leg_failure_still_propagates(error: Exception) -> None:
    backend = LowOverlapRoutingBackend(alternative_error=error)
    request = generation_request().model_copy(
        update={"path_selection_mode": "low_overlap"}
    )
    with pytest.raises(type(error)):
        await RouteGenerationService(backend).generate(request)


@pytest.mark.asyncio
async def test_low_overlap_leg_budget_is_separate_and_strict() -> None:
    backend = LowOverlapRoutingBackend()
    request = generation_request().model_copy(
        update={"path_selection_mode": "low_overlap"}
    )
    result = await RouteGenerationService(
        backend,
        low_overlap_settings=LowOverlapSettings(max_leg_requests=1),
    ).generate(request)
    assert backend.alternative_route_calls == 1
    assert result.search.evaluated_candidate_count == 0
    assert result.search.alternative_leg_request_count == 1
    assert result.search.low_overlap_budget_exhausted
    assert "low_overlap_leg_budget_exhausted" in result.search.warnings


@pytest.mark.asyncio
async def test_low_overlap_generation_serialization_is_deterministic() -> None:
    request = generation_request(candidates=3).model_copy(
        update={"path_selection_mode": "low_overlap"}
    )
    first = await RouteGenerationService(LowOverlapRoutingBackend()).generate(request)
    second = await RouteGenerationService(LowOverlapRoutingBackend()).generate(request)
    assert first.model_dump_json() == second.model_dump_json()


@pytest.mark.asyncio
async def test_repetition_only_tradeoff_does_not_become_recommended() -> None:
    request = generation_request(candidates=3).model_copy(
        update={"path_selection_mode": "low_overlap"}
    )
    result = await RouteGenerationService(TradeoffLowOverlapRoutingBackend()).generate(
        request
    )
    standard = result.candidates[0]
    refined = next(
        candidate
        for candidate in result.candidates
        if candidate.construction == "alternative_leg_beam"
    )
    assert standard.construction == "direct_order"
    assert (
        refined.route.analysis.repetition.repeated_distance.share
        < standard.route.analysis.repetition.repeated_distance.share
    )
    assert (
        refined.route.analysis.immediate_backtrack.share
        > standard.route.analysis.immediate_backtrack.share
    )
    assert "low_overlap_no_natural_improvement" in result.search.warnings
    assert "low_overlap_no_repetition_improvement" not in result.search.warnings


@pytest.mark.asyncio
async def test_backtracking_only_tradeoff_is_retained_but_not_recommended() -> None:
    request = generation_request(candidates=3).model_copy(
        update={"path_selection_mode": "low_overlap"}
    )
    result = await RouteGenerationService(BacktrackingOnlyTradeoffBackend()).generate(
        request
    )
    standard = result.candidates[0]
    refined = next(
        candidate
        for candidate in result.candidates
        if candidate.construction == "alternative_leg_beam"
    )
    assert standard.construction == "direct_order"
    assert (
        refined.route.analysis.immediate_backtrack.share
        < standard.route.analysis.immediate_backtrack.share
    )
    assert (
        refined.route.analysis.repetition.repeated_distance.share
        > standard.route.analysis.repetition.repeated_distance.share
    )
    assert "low_overlap_no_natural_improvement" in result.search.warnings
    assert "low_overlap_no_repetition_improvement" in result.search.warnings


@pytest.mark.asyncio
@pytest.mark.parametrize("candidate_count", [1, 2, 3, 5])
async def test_low_overlap_retention_keeps_only_one_standard_control(
    candidate_count: int,
) -> None:
    request = generation_request(candidates=candidate_count).model_copy(
        update={"path_selection_mode": "low_overlap"}
    )
    result = await RouteGenerationService(LowOverlapRoutingBackend()).generate(request)
    assert result.candidates[0].construction == "alternative_leg_beam"
    controls = [
        candidate
        for candidate in result.candidates
        if candidate.construction != "alternative_leg_beam"
    ]
    assert len(controls) == (0 if candidate_count == 1 else 1)
    assert len(result.candidates) <= candidate_count
    assert "candidate_diversity_relaxed" not in result.search.warnings


@pytest.mark.asyncio
async def test_low_overlap_without_standard_candidate_keeps_metrics_unknown() -> None:
    request = generation_request().model_copy(
        update={"path_selection_mode": "low_overlap"}
    )
    result = await RouteGenerationService(
        FakeRoutingBackend(fail_proposals=True)
    ).generate(request)
    assert result.candidates == ()
    assert result.search.low_overlap_requested
    assert result.search.pre_low_overlap_repeated_share is None
    assert result.search.best_low_overlap_repeated_share is None
    assert result.search.pre_low_overlap_backtrack_share is None
    assert result.search.best_low_overlap_backtrack_share is None
