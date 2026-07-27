"""Synthetic bounded composition of independent structural repairs."""

from __future__ import annotations

from dataclasses import replace
from typing import cast

import pytest

from sugarglider.analysis.spurs import detect_route_spurs
from sugarglider.domain.models import Coordinate, PathDetailSegment
from sugarglider.planning.budget import SearchBudget, SearchPhase
from sugarglider.planning.context import PlanningSearchContext
from sugarglider.planning.optimization.diagnostics import (
    GlobalOptimizationDiagnostics,
)
from sugarglider.planning.optimization.models import (
    AppliedSpurRepair,
    GlobalOptimizationSettings,
    OptimizationAnchor,
    OptimizationMove,
    OptimizationSource,
    StructuralRepairAction,
)
from sugarglider.planning.optimization.optimizer import optimize_tours
from sugarglider.planning.optimization.path_pool import LazyPathPool
from sugarglider.planning.optimization.spur_rejoin import (
    _analyze_structural_state,
    optimization_targets,
)
from sugarglider.planning.optimization.state import (
    apply_move,
    initial_state,
    state_from_selected_path_options,
)
from sugarglider.planning.optimization.structural_composition import (
    compose_structural_repairs,
)
from sugarglider.routing.backend import AutoTourRoutingBackend, RoutedPath
from sugarglider.routing.result import RouteResultFactory

A = Coordinate(lat=0.0, lon=0.000, name="A")
B = Coordinate(lat=0.0, lon=0.001, name="B")
C = Coordinate(lat=0.0, lon=0.002, name="C")
D = Coordinate(lat=0.0, lon=0.003, name="D")
X = Coordinate(lat=0.001, lon=0.001, name="X")
F = Coordinate(lat=0.001, lon=0.002, name="F")
G = Coordinate(lat=0.001, lon=0.003, name="G")
H = Coordinate(lat=0.001, lon=0.004, name="H")
E = Coordinate(lat=0.002, lon=0.002, name="E")
Y = Coordinate(lat=0.002, lon=0.004, name="Y")
Z = Coordinate(lat=0.002, lon=0.005, name="Z")


class _NoCallBackend:
    def __init__(self) -> None:
        self.calls = 0

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
        del start, end, profile, max_paths, max_weight_factor, max_share_factor
        self.calls += 1
        return ()


def _path(
    points: tuple[Coordinate, ...],
    edge_ids: tuple[int, ...],
    *,
    snapped: tuple[Coordinate, ...],
) -> RoutedPath:
    return RoutedPath(
        distance_m=600.0 * len(edge_ids),
        duration_ms=1_000 * len(edge_ids),
        ascend_m=None,
        descend_m=None,
        geometry=tuple((point.lon, point.lat) for point in points),
        snapped_points=tuple((point.lon, point.lat) for point in snapped),
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


def _anchor(
    anchor_id: str,
    coordinate: Coordinate,
    progress: float,
    window: int,
) -> OptimizationAnchor:
    return OptimizationAnchor(
        id=anchor_id,
        name=coordinate.name or anchor_id,
        coordinate=coordinate,
        semantic_coordinate=coordinate,
        kind="exact",
        source_progress=progress,
        exact_window=window,
    )


def _source(*, maximum_distance_m: float | None = None) -> OptimizationSource:
    path = _path(
        (A, B, C, D, C, B, X, F, G, H, G, F, E),
        (10, 20, 30, 30, 20, 40, 50, 60, 70, 70, 60, 80),
        snapped=(A, X, E),
    )
    factory = RouteResultFactory()
    route = factory.create(
        name="Two independent spurs",
        path=path,
        input_point_count=3,
        routing_profile="hike",
    )
    spurs = detect_route_spurs(route, topology="point_to_point")
    assert len(spurs.spurs) == 2
    named = tuple(
        spur.model_copy(
            update={
                "deliberate_stop_ids": (f"stop/target-{index}",),
                "deliberate_stop_names": (f"Target {index}",),
            }
        )
        for index, spur in enumerate(spurs.spurs, start=1)
    )
    spurs = spurs.model_copy(update={"spurs": named})
    route = route.model_copy(
        update={"analysis": route.analysis.model_copy(update={"spurs": spurs})}
    )
    return OptimizationSource(
        source_candidate_id="two-spur-source",
        route=route,
        routed_path=path,
        anchors=(
            _anchor("start", A, 0.0, 0),
            _anchor("middle", X, 0.5, 1),
            _anchor("end", E, 1.0, 2),
        ),
        topology="point_to_point",
        routing_profile="hike",
        target_distance_m=path.distance_m,
        tolerance_m=10_000,
        distance_priority="flexible",
        maximum_distance_m=maximum_distance_m,
        reached_requested_ids=frozenset({"requested/start", "requested/end"}),
        approximated_requested_ids=frozenset(),
        dropped_requested_ids=frozenset(),
    )


def _context(backend: _NoCallBackend) -> PlanningSearchContext:
    limits = {phase: 0 for phase in SearchPhase}
    limits[SearchPhase.GLOBAL_OPTIMIZATION] = 64
    return PlanningSearchContext.create(
        backend=cast(AutoTourRoutingBackend, backend),
        budget=SearchBudget(limits, total_limit=64),
    )


async def _actions(
    source: OptimizationSource,
    backend: _NoCallBackend,
) -> tuple[
    LazyPathPool,
    tuple[StructuralRepairAction, StructuralRepairAction],
]:
    settings = GlobalOptimizationSettings()
    diagnostics = GlobalOptimizationDiagnostics(64, 24)
    pool = LazyPathPool(
        context=_context(backend),
        profile="hike",
        result_factory=RouteResultFactory(),
        settings=settings,
        diagnostics=diagnostics,
    )
    base = await initial_state(source, pool)
    assert base is not None
    targets = optimization_targets(source, settings)
    assert len(targets) == 2
    replacement_paths = (
        _path((A, B, C, D, Y, X), (10, 20, 30, 90, 91), snapped=(A, X)),
        _path((X, F, G, H, Z, E), (50, 60, 70, 92, 93), snapped=(X, E)),
    )
    actions: list[StructuralRepairAction] = []
    for target, replacement_path in zip(targets, replacement_paths, strict=True):
        leg = target.containing_leg_start_index
        option = pool.insert(
            from_anchor=source.anchors[leg],
            to_anchor=source.anchors[leg + 1],
            profile="hike",
            path=replacement_path,
            source_kind="spur_connector",
        )
        repair = AppliedSpurRepair(
            target_stable_id=target.stable_id,
            spur_id=target.spur_id,
            stop_ids=target.stop_ids,
            stop_names=target.stop_names,
            containing_leg_index=leg,
            start_progress=target.start_progress,
            turnaround_progress=target.turnaround_progress,
            end_progress=target.end_progress,
            source_repeated_distance_m=target.repeated_distance_m,
            resulting_repeated_distance_m=0,
            improvement_m=target.repeated_distance_m,
            generation_strategy="ordinary_alternative",
            replacement_path_option_id=option.id,
        )
        options = list(base.path_options)
        options[leg] = option
        state = state_from_selected_path_options(
            source=source,
            anchors=base.anchors,
            options=tuple(options),
            operator="spur_rejoin",
            applied_spur_repairs=(repair,),
            analyzed_total_spur_repetition_m=(
                source.route.analysis.spurs.total_repeated_distance_m
                - target.repeated_distance_m
            ),
        )
        assert state is not None
        residual, total_spur_repetition = _analyze_structural_state(
            source,
            state,
            target,
            RouteResultFactory(),
        )
        repair = replace(
            repair,
            resulting_repeated_distance_m=residual,
            improvement_m=target.repeated_distance_m - residual,
        )
        state = replace(
            state,
            objective_components=replace(
                state.objective_components,
                analyzed_total_spur_repetition_m=total_spur_repetition,
            ),
            applied_spur_repairs=(repair,),
        )
        actions.append(
            StructuralRepairAction(
                repair=repair,
                replacement_option=option,
                resulting_single_state=state,
                stable_signature=f"action/{target.stable_id}",
            )
        )
    return pool, (actions[0], actions[1])


@pytest.mark.asyncio
async def test_two_independent_repairs_compose_without_routing() -> None:
    source = _source()
    backend = _NoCallBackend()
    pool, actions = await _actions(source, backend)
    base = await initial_state(source, pool)
    assert base is not None
    diagnostics = GlobalOptimizationDiagnostics(64, 24)
    calls_before = backend.calls

    states = compose_structural_repairs(
        source,
        base,
        actions,
        result_factory=RouteResultFactory(),
        settings=GlobalOptimizationSettings(),
        diagnostics=diagnostics,
    )

    assert backend.calls == calls_before == 0
    assert len(states) == 1
    combined = states[0]
    assert combined.selected_path_option_by_leg == tuple(
        action.replacement_option.id for action in actions
    )
    assert tuple(repair.stop_names for repair in combined.applied_spur_repairs) == (
        ("Target 1",),
        ("Target 2",),
    )
    assert all(repair.improvement_m >= 500 for repair in combined.applied_spur_repairs)
    assert combined.objective_components.analyzed_total_spur_repetition_m == 0
    single_totals = tuple(
        action.resulting_single_state.objective_components.analyzed_total_spur_repetition_m
        for action in actions
    )
    assert all(total is not None and total > 500 for total in single_totals)
    assert all(
        total != action.repair.resulting_repeated_distance_m
        for total, action in zip(single_totals, actions, strict=True)
    )
    assert combined.ordered_anchor_ids == base.ordered_anchor_ids
    assert combined.visited_requested_stop_ids == base.visited_requested_stop_ids
    assert diagnostics.composition_actions_considered == 2
    assert diagnostics.composition_pairs_considered == 1
    assert diagnostics.composition_triples_considered == 0
    assert diagnostics.composition_states_qualifying == 1


@pytest.mark.asyncio
async def test_same_leg_overlap_and_target_loss_are_explained(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _source()
    backend = _NoCallBackend()
    pool, actions = await _actions(source, backend)
    base = await initial_state(source, pool)
    assert base is not None

    same_leg_repair = replace(
        actions[1].repair,
        containing_leg_index=actions[0].repair.containing_leg_index,
    )
    same_leg = replace(
        actions[1],
        repair=same_leg_repair,
        resulting_single_state=replace(
            actions[1].resulting_single_state,
            applied_spur_repairs=(same_leg_repair,),
        ),
    )
    diagnostics = GlobalOptimizationDiagnostics(64, 24)
    assert (
        compose_structural_repairs(
            source,
            base,
            (actions[0], same_leg),
            result_factory=RouteResultFactory(),
            settings=GlobalOptimizationSettings(),
            diagnostics=diagnostics,
        )
        == ()
    )
    assert diagnostics.composition_incompatible_same_leg == 1

    overlapping_repair = replace(
        actions[1].repair,
        start_progress=actions[0].repair.end_progress - 0.01,
    )
    overlapping = replace(
        actions[1],
        repair=overlapping_repair,
        resulting_single_state=replace(
            actions[1].resulting_single_state,
            applied_spur_repairs=(overlapping_repair,),
        ),
    )
    diagnostics = GlobalOptimizationDiagnostics(64, 24)
    assert (
        compose_structural_repairs(
            source,
            base,
            (actions[0], overlapping),
            result_factory=RouteResultFactory(),
            settings=GlobalOptimizationSettings(),
            diagnostics=diagnostics,
        )
        == ()
    )
    assert diagnostics.composition_incompatible_overlap == 1

    monkeypatch.setattr(
        "sugarglider.planning.optimization.structural_composition._matching_residual",
        lambda source_value, repair, resulting: (
            repair.source_repeated_distance_m
            if repair.target_stable_id == actions[1].repair.target_stable_id
            else 0.0
        ),
    )
    diagnostics = GlobalOptimizationDiagnostics(64, 24)
    assert (
        compose_structural_repairs(
            source,
            base,
            actions,
            result_factory=RouteResultFactory(),
            settings=GlobalOptimizationSettings(),
            diagnostics=diagnostics,
        )
        == ()
    )
    assert diagnostics.composition_states_rejected_target_loss == 1


@pytest.mark.asyncio
async def test_explicit_maximum_rejects_composition_without_routing() -> None:
    original = _source()
    backend = _NoCallBackend()
    pool, actions = await _actions(original, backend)
    base = await initial_state(original, pool)
    assert base is not None
    source = replace(original, maximum_distance_m=1_000.0)
    diagnostics = GlobalOptimizationDiagnostics(64, 24)

    assert (
        compose_structural_repairs(
            source,
            base,
            actions,
            result_factory=RouteResultFactory(),
            settings=GlobalOptimizationSettings(),
            diagnostics=diagnostics,
        )
        == ()
    )
    assert diagnostics.composition_states_rejected_hard == 1
    assert backend.calls == 0

    severe_option = replace(
        actions[1].replacement_option,
        severe_profile_incompatibility=True,
    )
    severe_state = replace(
        actions[1].resulting_single_state,
        path_options=(
            actions[1].resulting_single_state.path_options[0],
            severe_option,
        ),
    )
    severe_action = replace(
        actions[1],
        replacement_option=severe_option,
        resulting_single_state=severe_state,
    )
    diagnostics = GlobalOptimizationDiagnostics(64, 24)
    assert (
        compose_structural_repairs(
            original,
            base,
            (actions[0], severe_action),
            result_factory=RouteResultFactory(),
            settings=GlobalOptimizationSettings(),
            diagnostics=diagnostics,
        )
        == ()
    )
    assert diagnostics.composition_states_rejected_hard == 1


@pytest.mark.asyncio
async def test_moves_preserve_invalidate_and_canonically_add_repairs() -> None:
    source = _source()
    backend = _NoCallBackend()
    pool, actions = await _actions(source, backend)
    base = await initial_state(source, pool)
    assert base is not None
    first = actions[0].resulting_single_state

    unrelated = await apply_move(
        source,
        first,
        OptimizationMove(
            operator="path_option",
            anchors=first.anchors,
            forced_path_option_by_leg=((1, actions[1].replacement_option.id),),
        ),
        pool,
    )
    assert unrelated is not None
    assert unrelated.applied_spur_repairs == (actions[0].repair,)

    invalidated = await apply_move(
        source,
        first,
        OptimizationMove(
            operator="path_option",
            anchors=first.anchors,
            forced_path_option_by_leg=((0, base.path_options[0].id),),
        ),
        pool,
    )
    assert invalidated is not None
    assert invalidated.applied_spur_repairs == ()

    combined = await apply_move(
        source,
        first,
        OptimizationMove(
            operator="spur_rejoin",
            anchors=first.anchors,
            forced_path_option_by_leg=((1, actions[1].replacement_option.id),),
            applied_spur_repair=actions[1].repair,
        ),
        pool,
    )
    assert combined is not None
    assert combined.applied_spur_repairs == (
        actions[0].repair,
        actions[1].repair,
    )


@pytest.mark.asyncio
async def test_optimizer_composes_even_when_alns_wall_time_is_exhausted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _source()
    backend = _NoCallBackend()
    _pool, actions = await _actions(source, backend)
    diagnostics = GlobalOptimizationDiagnostics(64, 24)

    async def supplied_actions(
        *args: object, **kwargs: object
    ) -> tuple[StructuralRepairAction, ...]:
        del args, kwargs
        return actions

    class _ExpiredAfterSetupClock:
        def __init__(self) -> None:
            self.wall_calls = 0

        def wall(self) -> float:
            self.wall_calls += 1
            return 0.0 if self.wall_calls == 1 else 10.0

        def cpu(self) -> float:
            return 0.0

    monkeypatch.setattr(
        "sugarglider.planning.optimization.optimizer.structural_spur_actions",
        supplied_actions,
    )
    result = await optimize_tours(
        (source,),
        context=_context(backend),
        result_factory=RouteResultFactory(),
        seed=11,
        settings=GlobalOptimizationSettings(
            maximum_iterations=10,
            optimizer_total_wall_time_limit_s=1,
        ),
        diagnostics=diagnostics,
        clock=_ExpiredAfterSetupClock(),
    )

    assert diagnostics.iterations == 10
    assert diagnostics.composition_pairs_considered == 1
    assert diagnostics.composition_states_qualifying == 1
    assert any(len(draft.applied_spur_repairs) == 2 for draft in result.drafts)
    assert diagnostics.graphhopper_calls_used <= 64
    assert diagnostics.complete_evaluations <= 24
    assert backend.calls <= 4


def test_final_composed_publication_marks_every_confirmed_target() -> None:
    source = _source()
    targets = optimization_targets(source, GlobalOptimizationSettings())
    diagnostics = GlobalOptimizationDiagnostics(64, 24)
    for target in targets:
        diagnostics.register_spur_target(target, rejoin_positions=1)

    published = diagnostics.record_published_spur_ids(
        source.source_candidate_id,
        tuple(target.spur_id for target in targets),
    )

    assert published == 2
    assert tuple(
        value["final_reason"] for value in diagnostics.as_dict()["targeted_spurs"]
    ) == ("published", "published")
