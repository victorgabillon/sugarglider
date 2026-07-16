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
