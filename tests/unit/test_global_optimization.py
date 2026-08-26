"""Synthetic graph coverage for the shared edge-aware global optimizer."""

from __future__ import annotations

from dataclasses import replace
from random import Random
from typing import cast

import pytest

from sugarglider.domain.models import Coordinate, PathDetailSegment
from sugarglider.planning.budget import SearchBudget, SearchPhase
from sugarglider.planning.context import PlanningSearchContext
from sugarglider.planning.optimization import (
    GlobalOptimizationDiagnostics,
    GlobalOptimizationSettings,
    OptimizationAnchor,
    OptimizationSource,
    TourObjective,
    normalized_anchor_progress,
    optimize_tours,
)
from sugarglider.planning.optimization.acceptance import (
    accept_state,
    structurally_qualifies,
)
from sugarglider.planning.optimization.models import (
    OptimizationAnchorKind,
    OptimizationMove,
)
from sugarglider.planning.optimization.objective import (
    acceptance_energy,
    edge_reuse_components,
    objective_improves,
    pareto_dominates,
)
from sugarglider.planning.optimization.operators import (
    AlternateApproachOperator,
    RelocateOperator,
    RuinRecreateOperator,
    SpurRejoinOperator,
    SwapOperator,
    TwoOptOperator,
)
from sugarglider.planning.optimization.optimizer import OptimizationClock
from sugarglider.planning.optimization.path_pool import LazyPathPool
from sugarglider.planning.optimization.state import initial_state
from sugarglider.pois.models import PoiApproachCandidate
from sugarglider.routing.backend import AutoTourRoutingBackend, RoutedPath
from sugarglider.routing.composition import compose_routed_segments
from sugarglider.routing.errors import RoutingPointError
from sugarglider.routing.result import RouteResultFactory

START = Coordinate(lat=0.0, lon=0.0, name="Start")
TURN = Coordinate(lat=0.0, lon=0.01, name="Turn")
TIP = Coordinate(lat=0.0, lon=0.02, name="Tip")
END = Coordinate(lat=0.01, lon=0.01, name="End")
ALT = Coordinate(lat=0.01, lon=0.0, name="Alternate")


def _path(
    points: tuple[Coordinate, ...],
    edge_ids: tuple[int, ...],
    *,
    distance_per_edge_m: float = 600.0,
    snapped: tuple[Coordinate, ...] | None = None,
) -> RoutedPath:
    assert len(points) == len(edge_ids) + 1
    return RoutedPath(
        distance_m=distance_per_edge_m * len(edge_ids),
        duration_ms=1_000 * len(edge_ids),
        ascend_m=None,
        descend_m=None,
        geometry=tuple((point.lon, point.lat) for point in points),
        snapped_points=tuple((point.lon, point.lat) for point in (snapped or points)),
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


def _approach(anchor_id: str, coordinate: Coordinate) -> PoiApproachCandidate:
    return PoiApproachCandidate(
        id=f"{anchor_id}/approach",
        coordinate=coordinate.model_copy(update={"name": None}),
        kind="mapped_entrance",
        source="osm_entrance",
        access="public",
        semantic_distance_m=5,
        arrival_tolerance_m=25,
    )


def _anchor(
    anchor_id: str,
    coordinate: Coordinate,
    progress: float,
    *,
    kind: OptimizationAnchorKind = "exact",
    window: int = 0,
) -> OptimizationAnchor:
    approach = _approach(anchor_id, coordinate) if kind == "soft" else None
    return OptimizationAnchor(
        id=anchor_id,
        name=coordinate.name or anchor_id,
        coordinate=coordinate,
        semantic_coordinate=coordinate,
        kind=kind,
        source_progress=progress,
        exact_window=window,
        constraint_strength="approach" if approach is not None else None,
        outcome="reached" if approach is not None else None,
        selected_approach=approach,
        approach_options=(approach,) if approach is not None else (),
        maximum_semantic_distance_m=100 if approach is not None else None,
    )


def _source(
    path: RoutedPath,
    *,
    anchors: tuple[OptimizationAnchor, ...] | None = None,
    maximum_m: float | None = None,
) -> OptimizationSource:
    source_anchors = anchors or (
        _anchor("start", START, 0),
        _anchor("end", END, 1, window=1),
    )
    return OptimizationSource(
        source_candidate_id="source",
        route=RouteResultFactory().create(
            name="Synthetic source",
            path=path,
            input_point_count=max(2, len(source_anchors)),
            routing_profile="hike",
        ),
        routed_path=path,
        anchors=source_anchors,
        topology="point_to_point",
        routing_profile="hike",
        target_distance_m=path.distance_m,
        tolerance_m=10_000,
        distance_priority="flexible",
        maximum_distance_m=maximum_m,
        reached_requested_ids=frozenset(),
        approximated_requested_ids=frozenset(),
        dropped_requested_ids=frozenset(),
    )


class _Backend:
    def __init__(
        self,
        alternatives: tuple[RoutedPath, ...],
        *,
        fail: bool = False,
    ) -> None:
        self.alternatives = alternatives
        self.fail = fail
        self.alternative_calls = 0
        self.profiles: list[str] = []

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
        del start, end, max_weight_factor, max_share_factor
        self.alternative_calls += 1
        self.profiles.append(profile)
        if self.fail:
            raise RoutingPointError("synthetic no path")
        return self.alternatives[:max_paths]


class _AdvancingClock:
    def __init__(self) -> None:
        self.wall_value = 0.0
        self.cpu_value = 0.0

    def wall(self) -> float:
        value = self.wall_value
        self.wall_value += 0.2
        return value

    def cpu(self) -> float:
        value = self.cpu_value
        self.cpu_value += 0.2
        return value


def _context(backend: _Backend, *, limit: int = 64) -> PlanningSearchContext:
    limits = {phase: 0 for phase in SearchPhase}
    limits[SearchPhase.GLOBAL_OPTIMIZATION] = limit
    return PlanningSearchContext.create(
        backend=cast(AutoTourRoutingBackend, backend),
        budget=SearchBudget(limits, total_limit=limit),
    )


def _pool(
    context: PlanningSearchContext,
    diagnostics: GlobalOptimizationDiagnostics,
    *,
    options: int = 3,
) -> LazyPathPool:
    return LazyPathPool(
        context=context,
        profile="hike",
        result_factory=RouteResultFactory(),
        settings=GlobalOptimizationSettings(
            maximum_path_options_per_directed_pair=options,
            maximum_iterations=10,
            maximum_no_improvement_iterations=10,
        ),
        diagnostics=diagnostics,
    )


def test_edge_objective_distinguishes_same_and_opposite_direction_reuse() -> None:
    unique = _path((START, TURN, END), (1, 2))
    same = _path((START, TURN, TIP, TURN, END), (1, 2, 3, 2))
    opposite = _path((START, TURN, TIP, TURN, END), (1, 2, 2, 3))

    unique_reuse = edge_reuse_components(unique)
    same_reuse = edge_reuse_components(same)
    opposite_reuse = edge_reuse_components(opposite)

    assert unique_reuse.total_repeated_distance_m == 0
    assert same_reuse.same_direction_reuse_m == pytest.approx(600)
    assert same_reuse.opposite_direction_reuse_m == 0
    assert opposite_reuse.opposite_direction_reuse_m == pytest.approx(600)
    assert opposite_reuse.same_direction_reuse_m == 0


def test_semantic_anchor_progress_is_explicit_for_one_and_multiple_points() -> None:
    assert normalized_anchor_progress(0, 1) == 0.0
    assert tuple(normalized_anchor_progress(index, 2) for index in range(2)) == (
        0.0,
        1.0,
    )
    quarters = tuple(normalized_anchor_progress(index, 4) for index in range(4))
    assert quarters[0] == 0.0
    assert quarters[1] == pytest.approx(1 / 3)
    assert quarters[2] == pytest.approx(2 / 3)
    assert quarters[3] == 1.0


def _objective(
    *,
    distance_m: float = 40_000,
    opposite_m: float = 2_000,
    backtracking_m: float = 2_000,
    distance_error_m: float = 0,
    hard_feasible: bool = True,
    reached: int = 1,
    nature_utility: float | None = 0,
) -> TourObjective:
    return TourObjective(
        hard_feasible=hard_feasible,
        reached_requested=reached,
        approximated_requested=0,
        dropped_requested=0,
        priority_weighted_coverage=2 * reached,
        opposite_direction_reuse_m=opposite_m,
        analyzed_total_spur_repetition_m=opposite_m,
        total_repeated_distance_m=max(opposite_m, backtracking_m),
        same_direction_reuse_m=0,
        immediate_backtracking_m=backtracking_m,
        profile_penalty=0,
        nature_utility=nature_utility,
        distance_m=distance_m,
        distance_error_m=distance_error_m,
    )


def test_structural_signal_prefers_shape_gain_with_bounded_extra_distance() -> None:
    settings = GlobalOptimizationSettings()
    source = _objective(backtracking_m=2_500)

    assert structurally_qualifies(
        source,
        _objective(distance_m=40_700, opposite_m=500),
        settings,
    )
    assert structurally_qualifies(
        source,
        _objective(
            distance_m=41_800,
            opposite_m=2_000,
            backtracking_m=0,
        ),
        settings,
    )
    assert not structurally_qualifies(
        source,
        _objective(distance_m=42_500, opposite_m=0, backtracking_m=0),
        settings,
    )
    assert not structurally_qualifies(
        source,
        _objective(distance_m=40_100, opposite_m=0, reached=0),
        settings,
    )


def test_lexicographic_shape_priority_precedes_large_soft_target_error() -> None:
    source = _objective(distance_error_m=0)
    shape_improvement = _objective(
        distance_m=41_000,
        opposite_m=0,
        backtracking_m=0,
        distance_error_m=41_000,
    )
    assert objective_improves(shape_improvement, source)
    assert not objective_improves(
        _objective(hard_feasible=False, opposite_m=0, backtracking_m=0),
        source,
    )


def test_last_analyzed_spur_total_is_not_a_cheap_alns_ranking_signal() -> None:
    objective = _objective()
    stale_other_analysis = replace(
        objective,
        analyzed_total_spur_repetition_m=0,
    )

    assert objective.lexicographic_key() == stale_other_analysis.lexicographic_key()
    assert acceptance_energy(objective) == acceptance_energy(stale_other_analysis)


def test_unavailable_nature_is_neutral_in_optimizer_comparisons() -> None:
    measured = _objective(nature_utility=100)
    unavailable = _objective(nature_utility=None)

    assert measured.lexicographic_key(
        include_nature=False
    ) == unavailable.lexicographic_key(include_nature=False)
    assert not objective_improves(measured, unavailable)
    assert not objective_improves(unavailable, measured)
    assert not pareto_dominates(measured, unavailable)
    assert not pareto_dominates(unavailable, measured)


def test_seeded_annealing_can_accept_a_temporary_feasible_regression() -> None:
    settings = GlobalOptimizationSettings(maximum_iterations=20)
    current = _objective()
    temporary = _objective(distance_m=40_001, distance_error_m=1)

    assert accept_state(
        current,
        temporary,
        iteration=1,
        settings=settings,
        rng=Random(9),
    )
    assert not accept_state(
        current,
        _objective(hard_feasible=False),
        iteration=1,
        settings=settings,
        rng=Random(9),
    )


@pytest.mark.asyncio
async def test_seeded_leg_incremental_objective_matches_full_recomputation() -> None:
    first = _path((START, TURN), (1,))
    second = _path(
        (TURN, TIP, TURN, END),
        (2, 2, 3),
        snapped=(TURN, END),
    )
    complete = compose_routed_segments((first, second))
    anchors = (
        _anchor("start", START, 0),
        _anchor("turn", TURN, 0.25, kind="soft"),
        _anchor("end", END, 1, window=1),
    )
    source = _source(complete, anchors=anchors)
    diagnostics = GlobalOptimizationDiagnostics(
        graphhopper_call_limit=64,
        complete_evaluation_limit=24,
    )
    state = await initial_state(source, _pool(_context(_Backend(())), diagnostics))

    assert state is not None
    incremental = edge_reuse_components(state.complete_path, state.path_options)
    full = edge_reuse_components(state.complete_path)
    assert incremental == full


@pytest.mark.asyncio
async def test_lazy_path_pool_is_bounded_profile_explicit_and_cache_backed() -> None:
    source_path = _path(
        (START, TURN, TIP, TURN, END),
        (1, 2, 2, 3),
        snapped=(START, END),
    )
    alternatives = (
        _path((START, ALT, END), (8, 9), snapped=(START, END)),
        _path((START, TURN, END), (4, 5), snapped=(START, END)),
        _path((START, TIP, END), (6, 7), snapped=(START, END)),
        _path((START, TURN, ALT, END), (10, 11, 12), snapped=(START, END)),
    )
    backend = _Backend(alternatives)
    context = _context(backend)
    source = _source(source_path)
    first_diagnostics = GlobalOptimizationDiagnostics(64, 24)
    first_pool = _pool(context, first_diagnostics, options=3)
    assert len(first_pool.seed_source(source)) == 1

    first = await first_pool.options_for(
        source.anchors[0],
        source.anchors[1],
        request_alternatives=True,
    )
    second_diagnostics = GlobalOptimizationDiagnostics(64, 24)
    second_pool = _pool(context, second_diagnostics, options=3)
    assert len(second_pool.seed_source(source)) == 1
    second = await second_pool.options_for(
        source.anchors[0],
        source.anchors[1],
        request_alternatives=True,
    )

    assert len(first) == len(second) == 3
    assert tuple(option.id for option in first) == tuple(option.id for option in second)
    assert backend.alternative_calls == 1
    assert backend.profiles == ["hike"]
    assert second_diagnostics.graphhopper_cache_hits == 1


@pytest.mark.asyncio
async def test_path_pool_retains_modestly_longer_low_overlap_option() -> None:
    source_path = _path(
        (START, TURN, END),
        (1, 2),
        snapped=(START, END),
    )
    shortest = _path(
        (START, TURN, END),
        (1, 3),
        distance_per_edge_m=500,
        snapped=(START, END),
    )
    near_shortest = _path(
        (START, TIP, END),
        (2, 4),
        distance_per_edge_m=550,
        snapped=(START, END),
    )
    low_overlap = _path(
        (START, TURN, ALT, END),
        (8, 9, 10),
        distance_per_edge_m=500,
        snapped=(START, END),
    )
    source = _source(source_path)
    diagnostics = GlobalOptimizationDiagnostics(64, 24)
    pool = _pool(
        _context(_Backend((shortest, near_shortest, low_overlap))),
        diagnostics,
        options=3,
    )
    pool.seed_source(source)

    retained = await pool.options_for(
        source.anchors[0],
        source.anchors[1],
        request_alternatives=True,
    )

    assert len(retained) == 3
    assert any(option.source_kind == "source_leg" for option in retained)
    assert any(option.routed_path.geometry == shortest.geometry for option in retained)
    assert any(
        option.routed_path.geometry == low_overlap.geometry for option in retained
    )


@pytest.mark.asyncio
async def test_failed_path_is_negatively_cached_without_second_backend_call() -> None:
    backend = _Backend((), fail=True)
    diagnostics = GlobalOptimizationDiagnostics(64, 24)
    pool = _pool(_context(backend), diagnostics)
    left = _anchor("left", START, 0)
    right = _anchor("right", END, 1, window=1)

    assert await pool.options_for(left, right) == ()
    assert await pool.options_for(left, right) == ()
    assert backend.alternative_calls == 1
    assert diagnostics.negative_path_results == 1
    assert diagnostics.graphhopper_negative_cache_hits == 1


@pytest.mark.asyncio
async def test_order_operators_preserve_exact_anchors_and_exact_windows() -> None:
    anchors = (
        _anchor("start", START, 0),
        _anchor("a", TURN, 0.25, kind="soft"),
        _anchor("b", TIP, 0.5, kind="soft"),
        _anchor("boundary", ALT, 0.75, window=1),
        _anchor("end", END, 1, window=2),
    )
    path = _path(
        (START, TURN, TIP, ALT, END),
        (1, 2, 3, 4),
    )
    source = _source(path, anchors=anchors)
    diagnostics = GlobalOptimizationDiagnostics(64, 24)
    pool = _pool(_context(_Backend(())), diagnostics)
    state = await initial_state(source, pool)
    assert state is not None
    settings = GlobalOptimizationSettings(
        maximum_iterations=10,
        maximum_no_improvement_iterations=10,
    )
    operators = (RelocateOperator(), SwapOperator(), TwoOptOperator())
    move_values: list[OptimizationMove] = []
    for operator in operators:
        move_values.extend(
            operator.propose_descriptors(
                state,
                rng=Random(7),
                settings=settings,
                diagnostics=diagnostics,
            )
        )
    moves = tuple(move_values)

    assert moves
    for move in moves:
        exact = tuple(anchor.id for anchor in move.anchors if anchor.kind == "exact")
        assert exact == ("start", "boundary", "end")
        windows = {anchor.id: anchor.exact_window for anchor in move.anchors}
        assert windows == {anchor.id: anchor.exact_window for anchor in anchors}


@pytest.mark.asyncio
async def test_semantic_and_spur_operators_keep_identity_and_safe_names() -> None:
    alternate_approach = _approach("a-alt", ALT)
    soft_a = replace(
        _anchor("a", TURN, 1 / 3, kind="soft"),
        approach_options=(
            _approach("a", TURN),
            alternate_approach,
        ),
        containing_spur_ids=("spur/one",),
        containing_spur_names=("Synthetic overlook",),
    )
    anchors = (
        _anchor("start", START, 0),
        soft_a,
        _anchor("b", TIP, 2 / 3, kind="soft"),
        _anchor("end", END, 1, window=1),
    )
    path = _path((START, TURN, TIP, END), (1, 2, 3))
    diagnostics = GlobalOptimizationDiagnostics(64, 24)
    backend = _Backend((_path((TURN, ALT, TIP), (8, 9), snapped=(TURN, TIP)),))
    pool = _pool(_context(backend), diagnostics)
    state = await initial_state(_source(path, anchors=anchors), pool)
    assert state is not None
    settings = GlobalOptimizationSettings(
        maximum_iterations=10,
        maximum_no_improvement_iterations=10,
    )

    approach_moves = AlternateApproachOperator().propose_descriptors(
        state,
        rng=Random(3),
        settings=settings,
        diagnostics=diagnostics,
    )
    ruin_moves = RuinRecreateOperator().propose_descriptors(
        state,
        rng=Random(3),
        settings=settings,
        diagnostics=diagnostics,
    )
    spur_moves = SpurRejoinOperator().propose_descriptors(
        state,
        rng=Random(3),
        settings=settings,
        diagnostics=diagnostics,
    )

    assert approach_moves
    changed = approach_moves[0].anchors[1]
    assert changed.id == soft_a.id
    assert changed.semantic_coordinate == soft_a.semantic_coordinate
    assert changed.selected_approach == alternate_approach
    assert ruin_moves
    assert {anchor.id for anchor in ruin_moves[0].anchors} == {
        anchor.id for anchor in anchors
    }
    assert spur_moves == ()
    targeted = diagnostics.as_dict()["targeted_spurs"]
    assert isinstance(targeted, tuple)
    assert targeted == ()


@pytest.mark.asyncio
async def test_optimizer_replaces_reversed_corridor_and_is_seed_deterministic() -> None:
    source_path = _path(
        (START, TURN, TIP, TURN, END),
        (1, 2, 2, 3),
        snapped=(START, END),
    )
    clean = _path(
        (START, ALT, END),
        (8, 9),
        distance_per_edge_m=1_500,
        snapped=(START, END),
    )
    settings = GlobalOptimizationSettings(
        maximum_iterations=14,
        maximum_no_improvement_iterations=14,
        optimizer_cpu_time_limit_s=1,
        optimizer_total_wall_time_limit_s=1,
    )

    async def run_once(
        clock: OptimizationClock | None = None,
    ) -> tuple[tuple[str, ...], GlobalOptimizationDiagnostics]:
        diagnostics = GlobalOptimizationDiagnostics(64, 24)
        result = await optimize_tours(
            (_source(source_path),),
            context=_context(_Backend((clean,))),
            result_factory=RouteResultFactory(),
            seed=23,
            settings=settings,
            diagnostics=diagnostics,
            clock=clock,
        )
        return tuple(draft.stable_signature for draft in result.drafts), diagnostics

    runs = [
        await run_once(_AdvancingClock() if index % 2 else None) for index in range(5)
    ]
    first, first_diagnostics = runs[0]

    assert all(signatures == first for signatures, _diagnostics in runs)
    assert first
    stable_diagnostics = []
    for _signatures, value in runs:
        snapshot = value.as_dict()
        for key in (
            "wall_time_ms",
            "routing_wait_time_ms",
            "optimization_cpu_time_ms",
            "graphhopper_cache_hits",
        ):
            snapshot.pop(key)
        stable_diagnostics.append(snapshot)
    assert all(snapshot == stable_diagnostics[0] for snapshot in stable_diagnostics)
    assert first_diagnostics.best_opposite_direction_improvement_m >= 600
    assert first_diagnostics.operator_attempts["path_option"] >= 1
    assert first_diagnostics.proposals_generated >= (
        first_diagnostics.descriptors_selected
    )
    assert first_diagnostics.path_requests <= first_diagnostics.descriptors_selected
    assert first_diagnostics.states_reconstructed <= (
        first_diagnostics.descriptors_selected
    )
    assert first_diagnostics.graphhopper_calls_used <= 64
    assert first_diagnostics.iterations <= 14
    assert first_diagnostics.as_dict()["targeted_spurs"] == ()
    assert runs[1][1].complete_evaluations == 0


@pytest.mark.asyncio
async def test_one_anchor_source_uses_no_route_budget_and_returns_no_draft() -> None:
    loop = _path(
        (START, TURN, START),
        (1, 1),
        snapped=(START,),
    )
    source = _source(
        loop,
        anchors=(_anchor("start", START, 0),),
    )
    backend = _Backend(())
    context = _context(backend)
    diagnostics = GlobalOptimizationDiagnostics(64, 24)

    result = await optimize_tours(
        (source,),
        context=context,
        result_factory=RouteResultFactory(),
        seed=1,
        settings=GlobalOptimizationSettings(
            maximum_iterations=7,
            maximum_no_improvement_iterations=7,
        ),
        diagnostics=diagnostics,
    )

    assert result.drafts == ()
    assert backend.alternative_calls == 0
    assert context.budget.used(SearchPhase.GLOBAL_OPTIMIZATION) == 0
    assert diagnostics.source_states == diagnostics.initial_states == 1
    assert diagnostics.unique_path_options == 0
    assert diagnostics.accepted_moves == 0
    assert diagnostics.iterations == 7


@pytest.mark.asyncio
async def test_one_hundred_in_memory_iterations_need_no_complete_evaluation() -> None:
    path = _path((START, TURN, END), (1, 2), snapped=(START, END))
    backend = _Backend(())
    diagnostics = GlobalOptimizationDiagnostics(64, 24)

    result = await optimize_tours(
        (_source(path),),
        context=_context(backend),
        result_factory=RouteResultFactory(),
        seed=5,
        settings=GlobalOptimizationSettings(
            maximum_iterations=100,
            maximum_no_improvement_iterations=100,
            optimizer_cpu_time_limit_s=2,
            optimizer_total_wall_time_limit_s=2,
        ),
        diagnostics=diagnostics,
        operators=(SpurRejoinOperator(),),
    )

    assert result.drafts == ()
    assert diagnostics.iterations == 100
    assert diagnostics.complete_evaluations == 0
    assert backend.alternative_calls == 0
    assert diagnostics.accepted_moves == 0


@pytest.mark.asyncio
async def test_fake_clock_is_observational_for_bounded_optimizer_output() -> None:
    source_path = _path(
        (START, TURN, TIP, TURN, END),
        (1, 2, 2, 3),
        snapped=(START, END),
    )
    diagnostics = GlobalOptimizationDiagnostics(64, 24)
    result = await optimize_tours(
        (_source(source_path),),
        context=_context(_Backend(())),
        result_factory=RouteResultFactory(),
        seed=2,
        settings=GlobalOptimizationSettings(
            maximum_iterations=100,
            maximum_no_improvement_iterations=100,
            optimizer_cpu_time_limit_s=0.1,
            optimizer_total_wall_time_limit_s=0.1,
        ),
        diagnostics=diagnostics,
        clock=_AdvancingClock(),
    )

    assert result.drafts == ()
    assert not diagnostics.time_limit_reached
    assert diagnostics.iterations == 100
    assert result.warnings == ()
    assert diagnostics.wall_time_ms >= 0
    assert diagnostics.optimization_cpu_time_ms >= 0


@pytest.mark.asyncio
async def test_explicit_maximum_excludes_infeasible_initial_state() -> None:
    source_path = _path(
        (START, TURN, END),
        (1, 2),
        snapped=(START, END),
    )
    diagnostics = GlobalOptimizationDiagnostics(64, 24)
    result = await optimize_tours(
        (_source(source_path, maximum_m=1_000),),
        context=_context(_Backend(())),
        result_factory=RouteResultFactory(),
        seed=4,
        diagnostics=diagnostics,
    )

    assert result.drafts == ()
    assert diagnostics.initial_states == 0
    assert diagnostics.states_pruned_distance_maximum == 1
