"""Deterministic generation orchestration using a fake routing backend."""

from collections.abc import Mapping

import pytest

from sugarglider.domain.generation import RouteGenerationRequest
from sugarglider.domain.models import Coordinate, PathDetailSegment
from sugarglider.generation.service import RouteGenerationService
from sugarglider.routing.backend import RoutedPath
from sugarglider.routing.graphhopper import RoutingPointError


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
async def test_fixed_mode_does_not_evaluate_alternative_orders() -> None:
    result = await RouteGenerationService(
        FakeRoutingBackend(), max_evaluations=2
    ).generate(generation_request())
    assert result.search.evaluated_order_count == 0
    assert result.candidates[0].required_point_order[0].original_index == 0


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
