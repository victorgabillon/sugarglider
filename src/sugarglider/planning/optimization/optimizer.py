"""Bounded deterministic ALNS orchestration above the shared routing gateway."""

from __future__ import annotations

from dataclasses import dataclass, replace
from random import Random
from time import perf_counter, process_time
from typing import Protocol, cast

from sugarglider.analysis.spurs import SpurTraversalAnchor, detect_route_spurs
from sugarglider.planning.context import PlanningSearchContext
from sugarglider.planning.optimization.acceptance import (
    accept_state,
    structurally_qualifies,
)
from sugarglider.planning.optimization.diagnostics import (
    GlobalOptimizationDiagnostics,
)
from sugarglider.planning.optimization.models import (
    GlobalOptimizationSettings,
    OptimizationAnchor,
    OptimizationDraft,
    OptimizationMove,
    OptimizationOperatorKind,
    OptimizationResult,
    OptimizationSource,
    TourObjective,
    TourOptimizationState,
)
from sugarglider.planning.optimization.objective import objective_improves
from sugarglider.planning.optimization.operators import (
    OptimizationOperator,
    default_operators,
)
from sugarglider.planning.optimization.path_pool import LazyPathPool
from sugarglider.planning.optimization.spur_rejoin import structural_spur_actions
from sugarglider.planning.optimization.state import (
    ParetoArchive,
    apply_move,
    initial_state,
)
from sugarglider.planning.optimization.structural_composition import (
    compose_structural_repairs,
    validated_applied_repairs,
)
from sugarglider.routing.result import RouteResultFactory


class OptimizationClock(Protocol):
    def wall(self) -> float: ...

    def cpu(self) -> float: ...


@dataclass(frozen=True)
class SystemOptimizationClock:
    def wall(self) -> float:
        return perf_counter()

    def cpu(self) -> float:
        return process_time()


async def optimize_tours(
    sources: tuple[OptimizationSource, ...],
    *,
    context: PlanningSearchContext,
    result_factory: RouteResultFactory,
    seed: int,
    settings: GlobalOptimizationSettings | None = None,
    diagnostics: GlobalOptimizationDiagnostics | None = None,
    operators: tuple[OptimizationOperator, ...] | None = None,
    clock: OptimizationClock | None = None,
) -> OptimizationResult:
    """Jointly optimize order, approaches, graph path options, and spur exits."""
    resolved = settings or GlobalOptimizationSettings()
    accumulator = diagnostics or GlobalOptimizationDiagnostics(
        graphhopper_call_limit=(resolved.maximum_uncached_global_optimizer_calls),
        complete_evaluation_limit=resolved.complete_evaluation_limit,
    )
    if not sources:
        return OptimizationResult(drafts=(), warnings=())
    source_values = sources[: resolved.maximum_initial_states]
    accumulator.source_states += len(sources)
    profile = source_values[0].routing_profile
    if any(source.routing_profile != profile for source in source_values):
        raise ValueError("global optimization sources must share one public profile")
    timer = clock or SystemOptimizationClock()
    wall_started = timer.wall()
    cpu_started = timer.cpu()
    pool = LazyPathPool(
        context=context,
        profile=profile,
        result_factory=result_factory,
        settings=resolved,
        diagnostics=accumulator,
        wall_clock=timer.wall,
        wall_deadline=wall_started + resolved.optimizer_total_wall_time_limit_s,
        enforce_wall_deadline=False,
    )
    source_by_id = {source.source_candidate_id: source for source in source_values}
    initial: list[TourOptimizationState] = []
    for source in source_values:
        state = await initial_state(source, pool)
        if state is None:
            accumulator.states_pruned_infeasible += 1
            continue
        if not state.objective_components.hard_feasible:
            _record_hard_rejection(source, state, accumulator)
            continue
        initial.append(state)
    unique_initial = {state.stable_signature: state for state in initial}
    initial = sorted(
        unique_initial.values(),
        key=lambda state: (
            state.objective_components.lexicographic_key(),
            state.stable_signature,
        ),
    )
    accumulator.initial_states += len(initial)
    if not initial:
        _record_timing(accumulator, timer, wall_started, cpu_started)
        return OptimizationResult(drafts=(), warnings=())
    archive = ParetoArchive(resolved)
    for state in initial:
        archive.add(state)
    initial_signatures = {state.stable_signature for state in initial}
    source_objectives = {
        state.source_candidate_id: state.objective_components for state in initial
    }
    current_states = [*initial]
    best = initial[0]
    structural: list[TourOptimizationState] = []
    for source_state in initial[: resolved.maximum_sources_for_structural_seeding]:
        source = source_by_id[source_state.source_candidate_id]
        actions = await structural_spur_actions(
            source,
            source_state,
            path_pool=pool,
            result_factory=result_factory,
            settings=resolved,
            diagnostics=accumulator,
        )
        accumulator.single_repair_actions += len(actions)
        single_states = tuple(action.resulting_single_state for action in actions)
        composed_states = compose_structural_repairs(
            source,
            source_state,
            actions,
            result_factory=result_factory,
            settings=resolved,
            diagnostics=accumulator,
        )
        major_states = (*single_states, *composed_states)
        for seed_state in major_states:
            structural.append(seed_state)
            archived = archive.add(seed_state)
            if len(seed_state.applied_spur_repairs) > 1:
                accumulator.composition_states_archived += int(archived)
            for repair in seed_state.applied_spur_repairs:
                accumulator.record_spur_outcome(
                    repair.target_stable_id,
                    improved=True,
                    archived=archived,
                )
    if structural:
        current_states.extend(structural)
        best = min(
            current_states,
            key=lambda value: (
                value.objective_components.lexicographic_key(),
                value.stable_signature,
            ),
        )
    rng = Random(seed)
    operator_values = operators or default_operators()
    weights = {operator.kind: 1 for operator in operator_values}
    no_improvement = 0
    warnings: set[str] = set()
    for iteration in range(resolved.maximum_iterations):
        if no_improvement >= resolved.maximum_no_improvement_iterations:
            break
        accumulator.iterations += 1
        state_index = iteration % len(current_states)
        current = current_states[state_index]
        operator = _select_operator(
            operator_values,
            weights,
            iteration=iteration,
            rng=rng,
        )
        kind = cast(OptimizationOperatorKind, operator.kind)
        accumulator.operator_attempts[kind] += 1
        descriptors = operator.propose_descriptors(
            current,
            rng=rng,
            settings=resolved,
            diagnostics=accumulator,
        )
        accumulator.proposals_generated += len(descriptors)
        if not descriptors:
            no_improvement += 1
            continue
        descriptor = descriptors[rng.randrange(len(descriptors))]
        accumulator.descriptors_selected += 1
        move = await operator.materialize(
            descriptor,
            current,
            path_pool=pool,
            diagnostics=accumulator,
        )
        if move is None:
            no_improvement += 1
            continue
        source = source_by_id[current.source_candidate_id]
        proposed = await apply_move(source, current, move, pool)
        if proposed is None:
            accumulator.states_pruned_infeasible += 1
            accumulator.record_spur_rejection(_move_target_id(move), "no_path")
            no_improvement += 1
            continue
        accumulator.states_reconstructed += 1
        objective = proposed.objective_components
        if not objective.hard_feasible:
            rejection = _record_hard_rejection(source, proposed, accumulator)
            accumulator.record_spur_rejection(_move_target_id(move), rejection)
            no_improvement += 1
            continue
        if not accept_state(
            current.objective_components,
            objective,
            iteration=iteration,
            settings=resolved,
            rng=rng,
        ):
            no_improvement += 1
            continue
        current_states[state_index] = proposed
        accumulator.accepted_moves += 1
        accumulator.operator_acceptances[kind] += 1
        improved = objective_improves(
            proposed.objective_components, best.objective_components
        )
        if improved:
            best = proposed
            accumulator.improving_moves += 1
            accumulator.operator_best_improvements[kind] += 1
            weights[operator.kind] = min(16, weights[operator.kind] + 3)
            no_improvement = 0
        else:
            weights[operator.kind] = min(16, weights[operator.kind] + 1)
            no_improvement += 1
        archived = archive.add(proposed)
        for repair in proposed.applied_spur_repairs:
            accumulator.record_spur_outcome(
                repair.target_stable_id,
                improved=structurally_qualifies(
                    source_objectives[proposed.source_candidate_id],
                    proposed.objective_components,
                    resolved,
                ),
                archived=archived,
            )
    archive_states = tuple(
        state
        for state in archive.states()
        if state.stable_signature not in initial_signatures
    )
    best_by_target_set: dict[frozenset[str], TourOptimizationState] = {}
    for state in structural:
        target_set = frozenset(
            repair.target_stable_id for repair in state.applied_spur_repairs
        )
        if not target_set:
            continue
        prior = best_by_target_set.get(target_set)
        if prior is None or _structural_state_key(state) < _structural_state_key(prior):
            best_by_target_set[target_set] = state
    priority_states = tuple(
        sorted(
            best_by_target_set.values(),
            key=_structural_state_key,
        )
    )
    combined = {
        (
            state.source_candidate_id,
            frozenset(repair.target_stable_id for repair in state.applied_spur_repairs),
            state.stable_signature,
        ): state
        for state in (*priority_states, *archive_states)
    }
    states = tuple(combined.values())[: resolved.complete_evaluation_limit]
    for state in states:
        for repair in state.applied_spur_repairs:
            accumulator.record_spur_evaluation(repair.target_stable_id)
    drafts = _drafts(
        states,
        source_by_id=source_by_id,
        source_objectives=source_objectives,
        result_factory=result_factory,
        minimum_targeted_improvement_m=resolved.minimum_structural_improvement_m,
    )
    accumulator.archive_candidates = len(states)
    accumulator.unique_path_options = pool.unique_option_count
    _record_best_improvements(accumulator, drafts)
    _record_timing(accumulator, timer, wall_started, cpu_started)
    if accumulator.time_limit_reached:
        warnings.add("global_optimization_time_limit_reached")
    if accumulator.budget_exhausted:
        warnings.add("global_optimization_budget_exhausted")
    return OptimizationResult(
        drafts=drafts,
        warnings=tuple(sorted(warnings)),
    )


def _select_operator(
    operators: tuple[OptimizationOperator, ...],
    weights: dict[str, int],
    *,
    iteration: int,
    rng: Random,
) -> OptimizationOperator:
    if iteration < len(operators):
        return operators[iteration]
    total = sum(weights[operator.kind] for operator in operators)
    choice = rng.randrange(total)
    cursor = 0
    for operator in operators:
        cursor += weights[operator.kind]
        if choice < cursor:
            return operator
    return operators[-1]


def _drafts(
    states: tuple[TourOptimizationState, ...],
    *,
    source_by_id: dict[str, OptimizationSource],
    source_objectives: dict[str, TourObjective],
    result_factory: RouteResultFactory,
    minimum_targeted_improvement_m: float,
) -> tuple[OptimizationDraft, ...]:
    values: list[OptimizationDraft] = []
    for state in states:
        source = source_by_id[state.source_candidate_id]
        anchors = _anchors_with_routed_progress(state)
        route = result_factory.create(
            name=source.route.name,
            path=state.complete_path,
            input_point_count=max(2, len(state.anchors)),
            routing_profile=source.routing_profile,
        )
        spurs = detect_route_spurs(
            route,
            tuple(
                SpurTraversalAnchor(
                    id=anchor.id,
                    name=anchor.name,
                    route_progress=anchor.source_progress,
                )
                for anchor in anchors
                if anchor.kind == "soft"
            ),
            topology=source.topology,
        )
        route = route.model_copy(
            update={"analysis": route.analysis.model_copy(update={"spurs": spurs})}
        )
        validated_repairs = validated_applied_repairs(
            source,
            state.applied_spur_repairs,
            spurs,
            minimum_improvement_m=minimum_targeted_improvement_m,
        )
        values.append(
            OptimizationDraft(
                source_candidate_id=state.source_candidate_id,
                path=state.complete_path,
                route=route,
                anchors=anchors,
                routing_points=tuple(anchor.coordinate for anchor in anchors),
                selected_approaches=tuple(
                    (anchor.id, anchor.selected_approach)
                    for anchor in anchors
                    if anchor.selected_approach is not None
                ),
                operator=cast(OptimizationOperatorKind, state.last_operator),
                source_objective=source_objectives[state.source_candidate_id],
                resulting_objective=replace(
                    state.objective_components,
                    analyzed_total_spur_repetition_m=(spurs.total_repeated_distance_m),
                ),
                applied_spur_repairs=validated_repairs,
                stable_signature=state.stable_signature,
            )
        )
    return tuple(values)


def _anchors_with_routed_progress(
    state: TourOptimizationState,
) -> tuple[OptimizationAnchor, ...]:
    if len(state.anchors) <= 1:
        return tuple(replace(anchor, source_progress=0.0) for anchor in state.anchors)
    total = state.complete_path.distance_m
    cumulative = 0.0
    values = []
    for index, anchor in enumerate(state.anchors):
        progress = 0.0 if total <= 0 else min(1.0, cumulative / total)
        values.append(replace(anchor, source_progress=progress))
        if index < len(state.path_options):
            cumulative += state.path_options[index].distance_m
    return tuple(values)


def _move_target_id(move: OptimizationMove) -> str | None:
    return (
        move.applied_spur_repair.target_stable_id
        if move.applied_spur_repair is not None
        else None
    )


def _structural_state_key(
    state: TourOptimizationState,
) -> tuple[object, ...]:
    return (
        -len(state.applied_spur_repairs),
        -sum(repair.improvement_m for repair in state.applied_spur_repairs),
        state.objective_components.lexicographic_key(),
        state.stable_signature,
    )


def _record_hard_rejection(
    source: OptimizationSource,
    state: TourOptimizationState,
    diagnostics: GlobalOptimizationDiagnostics,
) -> str:
    if (
        source.maximum_distance_m is not None
        and state.complete_path.distance_m > source.maximum_distance_m
    ):
        diagnostics.states_pruned_distance_maximum += 1
        return "distance"
    elif any(option.severe_profile_incompatibility for option in state.path_options):
        diagnostics.states_pruned_profile += 1
        return "profile"
    else:
        diagnostics.states_pruned_infeasible += 1
        return "infeasible"


def _record_timing(
    diagnostics: GlobalOptimizationDiagnostics,
    clock: OptimizationClock,
    wall_started: float,
    cpu_started: float,
) -> None:
    diagnostics.wall_time_ms += max(0.0, clock.wall() - wall_started) * 1_000
    diagnostics.optimization_cpu_time_ms += max(0.0, clock.cpu() - cpu_started) * 1_000


def _record_best_improvements(
    diagnostics: GlobalOptimizationDiagnostics,
    drafts: tuple[OptimizationDraft, ...],
) -> None:
    if not drafts:
        return
    diagnostics.best_opposite_direction_improvement_m = max(
        draft.source_objective.opposite_direction_reuse_m
        - draft.resulting_objective.opposite_direction_reuse_m
        for draft in drafts
    )
    diagnostics.best_repetition_improvement_m = max(
        draft.source_objective.total_repeated_distance_m
        - draft.resulting_objective.total_repeated_distance_m
        for draft in drafts
    )
    diagnostics.best_backtracking_improvement_m = max(
        draft.source_objective.immediate_backtracking_m
        - draft.resulting_objective.immediate_backtracking_m
        for draft in drafts
    )
    best = min(
        drafts,
        key=lambda draft: (
            draft.resulting_objective.lexicographic_key(),
            draft.stable_signature,
        ),
    )
    diagnostics.best_distance_change_m = (
        best.resulting_objective.distance_m - best.source_objective.distance_m
    )
