"""Deterministic bounded low-overlap beam-search tests."""

from collections.abc import Mapping

import pytest

from sugarglider.domain.models import Coordinate, PathDetailSegment
from sugarglider.generation.low_overlap import (
    BeamState,
    LowOverlapBeamSearch,
    LowOverlapSettings,
    _prune_beam,
)
from sugarglider.routing.backend import RoutedPath
from sugarglider.routing.result import RouteResultFactory

type LegKey = tuple[float, float, float, float]


class AlternativeBackend:
    def __init__(self, alternatives: Mapping[LegKey, tuple[RoutedPath, ...]]) -> None:
        self.alternatives: dict[LegKey, tuple[RoutedPath, ...]] = dict(alternatives)
        self.calls: list[LegKey] = []

    async def route(
        self,
        points: tuple[Coordinate, ...],
        profile: str = "hike",
        *,
        pass_through: bool = False,
    ) -> RoutedPath:
        raise AssertionError("ordinary routing is not used by beam search")

    async def round_trip(
        self,
        start: Coordinate,
        distance_m: float,
        seed: int,
        profile: str = "hike",
    ) -> RoutedPath:
        raise AssertionError("round-trip routing is not used by beam search")

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
        key = (start.lat, start.lon, end.lat, end.lon)
        self.calls.append(key)
        return self.alternatives[key]


def routed_leg(
    start: Coordinate,
    end: Coordinate,
    *,
    edge_id: int | None,
    distance_m: float,
    geometry_start: tuple[float, float] | None = None,
) -> RoutedPath:
    geometry = (
        geometry_start or (start.lon, start.lat),
        (end.lon, end.lat),
    )
    details = (
        {}
        if edge_id is None
        else {"edge_id": (PathDetailSegment(from_index=0, to_index=1, value=edge_id),)}
    )
    return RoutedPath(
        distance_m=distance_m,
        duration_ms=10,
        ascend_m=None,
        descend_m=None,
        geometry=geometry,
        snapped_points=((start.lon, start.lat), (end.lon, end.lat)),
        details=details,
    )


def closed_two_leg_backend(
    *,
    return_alternatives: tuple[tuple[int | None, float], ...],
) -> tuple[AlternativeBackend, tuple[Coordinate, ...]]:
    start = Coordinate(lat=0.0, lon=0.0, name="start")
    end = Coordinate(lat=0.0, lon=0.01, name="end")
    outbound = routed_leg(start, end, edge_id=1, distance_m=40)
    returning = tuple(
        routed_leg(end, start, edge_id=edge_id, distance_m=distance)
        for edge_id, distance in return_alternatives
    )
    return (
        AlternativeBackend(
            {
                (start.lat, start.lon, end.lat, end.lon): (outbound,),
                (end.lat, end.lon, start.lat, start.lon): returning,
            }
        ),
        (start, end),
    )


def partial_state(
    signature: str,
    *,
    repetition: float,
    backtrack: float,
    distance: float,
    primary: bool = False,
) -> BeamState:
    start = Coordinate(lat=0, lon=0)
    end = Coordinate(lat=0, lon=0.01)
    path = routed_leg(start, end, edge_id=1, distance_m=distance)
    return BeamState(
        segments=(path,),
        composed_path=path,
        completed_leg_count=2,
        stable_signature=signature,
        repeated_edge_distance_m=repetition,
        immediate_backtrack_distance_m=backtrack,
        total_distance_m=distance,
        all_primary_paths=primary,
    )


@pytest.mark.asyncio
async def test_zero_overlap_global_combination_beats_individually_shortest_legs() -> (
    None
):
    backend, points = closed_two_leg_backend(return_alternatives=((1, 40), (2, 60)))
    search = LowOverlapBeamSearch(
        backend,
        RouteResultFactory(),
        LowOverlapSettings(beam_width=3),
    )
    result = await search.assemble(
        name="beam",
        routing_points=points,
        profile="hike",
        target_distance_m=100,
        input_point_count=2,
    )
    assert result.states
    assert result.states[0].repeated_edge_distance_m == 0
    assert result.states[0].total_distance_m == 100
    assert any(state.all_primary_paths for state in result.states)


@pytest.mark.asyncio
async def test_exact_repeated_edge_and_immediate_reverse_are_measured_globally() -> (
    None
):
    backend, points = closed_two_leg_backend(return_alternatives=((1, 40),))
    result = await LowOverlapBeamSearch(
        backend, RouteResultFactory(), LowOverlapSettings()
    ).assemble(
        name="beam",
        routing_points=points,
        profile="hike",
        target_distance_m=80,
        input_point_count=2,
    )
    state = result.states[0]
    assert state.repeated_edge_distance_m == pytest.approx(40)
    assert state.immediate_backtrack_distance_m == pytest.approx(40)


@pytest.mark.asyncio
async def test_open_beam_never_appends_the_start() -> None:
    start = Coordinate(lat=48.85, lon=2.36)
    end = Coordinate(lat=48.88, lon=2.10)
    key = (start.lat, start.lon, end.lat, end.lon)
    backend = AlternativeBackend(
        {key: (routed_leg(start, end, edge_id=1, distance_m=20_000),)}
    )
    result = await LowOverlapBeamSearch(
        backend, RouteResultFactory(), LowOverlapSettings()
    ).assemble(
        name="open",
        routing_points=(start, end),
        profile="hike",
        target_distance_m=25_000,
        input_point_count=2,
        close_loop=False,
    )
    assert backend.calls == [key]
    assert result.states[0].composed_path.geometry[0] == (start.lon, start.lat)
    assert result.states[0].composed_path.geometry[-1] == (end.lon, end.lat)


@pytest.mark.asyncio
async def test_distance_progress_competitive_and_primary_states_survive_pruning() -> (
    None
):
    backend, points = closed_two_leg_backend(return_alternatives=((1, 60), (2, 160)))
    result = await LowOverlapBeamSearch(
        backend, RouteResultFactory(), LowOverlapSettings(beam_width=3)
    ).assemble(
        name="beam",
        routing_points=points,
        profile="hike",
        target_distance_m=100,
        input_point_count=2,
    )
    assert any(state.total_distance_m == 100 for state in result.states)
    assert any(state.repeated_edge_distance_m == 0 for state in result.states)
    assert any(state.all_primary_paths for state in result.states)


def test_minimum_backtracking_state_has_second_pruning_priority() -> None:
    states = (
        partial_state("min-repeat", repetition=1, backtrack=5, distance=50),
        partial_state("min-backtrack", repetition=2, backtrack=1, distance=80),
        partial_state(
            "progress-primary",
            repetition=1.5,
            backtrack=3,
            distance=50,
            primary=True,
        ),
    )
    first = _prune_beam(
        states,
        beam_width=2,
        target_distance_m=100,
        total_leg_count=4,
    )
    second = _prune_beam(
        states,
        beam_width=2,
        target_distance_m=100,
        total_leg_count=4,
    )
    assert [state.stable_signature for state in first] == [
        "min-repeat",
        "min-backtrack",
    ]
    assert first == second


def test_retained_low_backtracking_state_can_enable_later_natural_improvement() -> None:
    retained = _prune_beam(
        (
            partial_state("min-repeat", repetition=1, backtrack=5, distance=50),
            partial_state("min-backtrack", repetition=2, backtrack=1, distance=80),
            partial_state("progress", repetition=1.5, backtrack=3, distance=50),
        ),
        beam_width=2,
        target_distance_m=100,
        total_leg_count=4,
    )
    completed_metrics = {
        "min-repeat": (4.0, 6.0),
        "min-backtrack": (3.0, 1.0),
    }
    natural = [
        state.stable_signature
        for state in retained
        if completed_metrics[state.stable_signature][0] < 5.0
        and completed_metrics[state.stable_signature][1] <= 2.0
    ]
    assert natural == ["min-backtrack"]


@pytest.mark.asyncio
async def test_ties_are_stable_deduplicated_and_beam_width_is_enforced() -> None:
    backend, points = closed_two_leg_backend(
        return_alternatives=((2, 60), (3, 60), (4, 60))
    )
    settings = LowOverlapSettings(beam_width=2)
    first = await LowOverlapBeamSearch(
        backend, RouteResultFactory(), settings
    ).assemble(
        name="beam",
        routing_points=points,
        profile="hike",
        target_distance_m=100,
        input_point_count=2,
    )
    second_backend, _ = closed_two_leg_backend(
        return_alternatives=((2, 60), (3, 60), (4, 60))
    )
    second = await LowOverlapBeamSearch(
        second_backend, RouteResultFactory(), settings
    ).assemble(
        name="beam",
        routing_points=points,
        profile="hike",
        target_distance_m=100,
        input_point_count=2,
    )
    assert len(first.states) == 2
    assert [state.stable_signature for state in first.states] == [
        state.stable_signature for state in second.states
    ]
    assert len({state.stable_signature for state in first.states}) == 2


@pytest.mark.asyncio
async def test_duplicate_partial_signatures_are_removed() -> None:
    backend, points = closed_two_leg_backend(
        return_alternatives=((2, 60), (2, 60), (3, 60))
    )
    result = await LowOverlapBeamSearch(
        backend, RouteResultFactory(), LowOverlapSettings(beam_width=12)
    ).assemble(
        name="beam",
        routing_points=points,
        profile="hike",
        target_distance_m=100,
        input_point_count=2,
    )
    assert len(result.states) == 2
    assert len({state.stable_signature for state in result.states}) == 2


@pytest.mark.asyncio
async def test_exact_leg_cache_does_not_consume_budget_twice() -> None:
    backend, points = closed_two_leg_backend(return_alternatives=((2, 60),))
    search = LowOverlapBeamSearch(
        backend,
        RouteResultFactory(),
        LowOverlapSettings(max_leg_requests=2),
    )
    for _ in range(2):
        result = await search.assemble(
            name="beam",
            routing_points=points,
            profile="hike",
            target_distance_m=100,
            input_point_count=2,
        )
        assert result.states
    assert search.request_count == 2
    assert len(backend.calls) == 2


@pytest.mark.asyncio
async def test_leg_budget_is_strict_and_exposed() -> None:
    backend, points = closed_two_leg_backend(return_alternatives=((2, 60),))
    search = LowOverlapBeamSearch(
        backend,
        RouteResultFactory(),
        LowOverlapSettings(max_leg_requests=1),
    )
    result = await search.assemble(
        name="beam",
        routing_points=points,
        profile="hike",
        target_distance_m=100,
        input_point_count=2,
    )
    assert result.states == ()
    assert search.request_count == 1
    assert search.budget_exhausted
    assert result.warnings == ("low_overlap_leg_budget_exhausted",)


@pytest.mark.asyncio
async def test_incomplete_edge_coverage_is_reported() -> None:
    backend, points = closed_two_leg_backend(return_alternatives=((None, 60),))
    result = await LowOverlapBeamSearch(
        backend, RouteResultFactory(), LowOverlapSettings()
    ).assemble(
        name="beam",
        routing_points=points,
        profile="hike",
        target_distance_m=100,
        input_point_count=2,
    )
    assert "low_overlap_edge_id_coverage_insufficient" in result.warnings


@pytest.mark.asyncio
async def test_discontinuous_alternative_has_no_straight_line_fallback() -> None:
    backend, points = closed_two_leg_backend(return_alternatives=((2, 60),))
    end, start = points[1], points[0]
    backend.alternatives[(end.lat, end.lon, start.lat, start.lon)] = (
        routed_leg(
            end,
            start,
            edge_id=2,
            distance_m=60,
            geometry_start=(9.0, 9.0),
        ),
    )
    result = await LowOverlapBeamSearch(
        backend, RouteResultFactory(), LowOverlapSettings()
    ).assemble(
        name="beam",
        routing_points=points,
        profile="hike",
        target_distance_m=100,
        input_point_count=2,
    )
    assert result.states == ()
    assert result.warnings == ("low_overlap_no_complete_candidate",)
