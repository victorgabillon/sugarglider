"""Bounded zero-routing composition of independently routed spur repairs."""

from __future__ import annotations

from dataclasses import dataclass, replace
from itertools import combinations

from sugarglider.analysis.route import haversine_distance_m
from sugarglider.analysis.spurs import SpurTraversalAnchor, detect_route_spurs
from sugarglider.domain.analysis import RouteSpur, RouteSpurAnalysis
from sugarglider.planning.optimization.diagnostics import (
    GlobalOptimizationDiagnostics,
)
from sugarglider.planning.optimization.models import (
    AppliedSpurRepair,
    GlobalOptimizationSettings,
    OptimizationSource,
    StructuralRepairAction,
    TourOptimizationState,
)
from sugarglider.planning.optimization.state import state_from_selected_path_options
from sugarglider.routing.result import RouteResultFactory

_EPSILON_M = 1e-6


@dataclass(frozen=True)
class AppliedSpurRepairValidation:
    """Safe final PR19 validation result for one applied major repair."""

    source: AppliedSpurRepair
    validated: AppliedSpurRepair | None
    resulting_repeated_distance_m: float
    resulting_improvement_m: float


def compose_structural_repairs(
    source: OptimizationSource,
    base_state: TourOptimizationState,
    actions: tuple[StructuralRepairAction, ...],
    *,
    result_factory: RouteResultFactory,
    settings: GlobalOptimizationSettings,
    diagnostics: GlobalOptimizationDiagnostics,
) -> tuple[TourOptimizationState, ...]:
    """Compose compatible routed actions without a gateway or backend call."""
    selected = _bounded_actions(actions, settings)
    diagnostics.composition_actions_considered += len(selected)
    retained: list[TourOptimizationState] = []
    considered = 0
    sizes = tuple(range(2, settings.maximum_repairs_per_composed_state + 1))
    for size in sizes:
        size_considered = 0
        remaining = settings.maximum_structural_combinations_per_source - considered
        size_limit = (
            remaining
            if size == sizes[-1]
            else min(
                remaining,
                max(1, settings.maximum_structural_combinations_per_source // 2),
            )
        )
        for values in combinations(selected, size):
            if size_considered >= size_limit:
                break
            considered += 1
            size_considered += 1
            if size == 2:
                diagnostics.composition_pairs_considered += 1
            else:
                diagnostics.composition_triples_considered += 1
            incompatibility = _incompatibility(values)
            if incompatibility == "same_leg":
                diagnostics.composition_incompatible_same_leg += 1
                continue
            if incompatibility == "overlap":
                diagnostics.composition_incompatible_overlap += 1
                continue
            state = _compose(
                source,
                base_state,
                values,
                result_factory=result_factory,
                settings=settings,
                diagnostics=diagnostics,
            )
            if state is not None:
                retained.append(state)
        if considered >= settings.maximum_structural_combinations_per_source:
            break
    ordered = sorted(
        {state.stable_signature: state for state in retained}.values(),
        key=lambda state: _composition_key(source, state),
    )[: settings.maximum_composed_states_retained]
    if ordered:
        diagnostics.best_composed_target_count = max(
            len(state.applied_spur_repairs) for state in ordered
        )
        diagnostics.best_composed_targeted_improvement_m = max(
            sum(repair.improvement_m for repair in state.applied_spur_repairs)
            for state in ordered
        )
    return tuple(ordered)


def _bounded_actions(
    actions: tuple[StructuralRepairAction, ...],
    settings: GlobalOptimizationSettings,
) -> tuple[StructuralRepairAction, ...]:
    by_target: dict[str, list[StructuralRepairAction]] = {}
    for action in actions:
        by_target.setdefault(action.repair.target_stable_id, []).append(action)
    ordered_by_target = {
        target_id: sorted(
            by_target[target_id],
            key=lambda value: (
                -value.repair.improvement_m,
                value.resulting_single_state.objective_components.lexicographic_key(),
                value.stable_signature,
            ),
        )[: settings.maximum_actions_per_structural_target]
        for target_id in sorted(by_target)
    }
    values = tuple(
        ordered_by_target[target_id][variant_index]
        for variant_index in range(settings.maximum_actions_per_structural_target)
        for target_id in sorted(ordered_by_target)
        if variant_index < len(ordered_by_target[target_id])
    )
    return values[: settings.maximum_structural_actions_per_source]


def _incompatibility(
    actions: tuple[StructuralRepairAction, ...],
) -> str | None:
    if len({action.repair.target_stable_id for action in actions}) != len(actions):
        return "overlap"
    if len({action.repair.containing_leg_index for action in actions}) != len(actions):
        return "same_leg"
    ordered = sorted(actions, key=lambda action: action.repair.start_progress)
    if any(
        left.repair.end_progress > right.repair.start_progress + _EPSILON_M
        for left, right in zip(ordered, ordered[1:], strict=False)
    ):
        return "overlap"
    return None


def _compose(
    source: OptimizationSource,
    base_state: TourOptimizationState,
    actions: tuple[StructuralRepairAction, ...],
    *,
    result_factory: RouteResultFactory,
    settings: GlobalOptimizationSettings,
    diagnostics: GlobalOptimizationDiagnostics,
) -> TourOptimizationState | None:
    options = list(base_state.path_options)
    for action in actions:
        repair = action.repair
        if (
            action.resulting_single_state.source_candidate_id
            != source.source_candidate_id
            or repair.containing_leg_index >= len(options)
            or base_state.anchors != action.resulting_single_state.anchors
        ):
            diagnostics.composition_states_rejected_hard += 1
            return None
        options[repair.containing_leg_index] = action.replacement_option
    state = state_from_selected_path_options(
        source=source,
        anchors=base_state.anchors,
        options=tuple(options),
        operator="spur_rejoin",
        applied_spur_repairs=tuple(action.repair for action in actions),
        analyzed_total_spur_repetition_m=None,
    )
    if state is None:
        diagnostics.composition_states_rejected_hard += 1
        return None
    diagnostics.composition_states_built += 1
    if not state.objective_components.hard_feasible:
        diagnostics.composition_states_rejected_hard += 1
        return None
    if (
        state.objective_components.total_repeated_distance_m
        > base_state.objective_components.total_repeated_distance_m + _EPSILON_M
    ):
        diagnostics.composition_states_rejected_hard += 1
        return None
    spurs = _analyzed_spurs(source, state, result_factory)
    if (
        spurs.total_repeated_distance_m
        > source.route.analysis.spurs.total_repeated_distance_m + _EPSILON_M
    ):
        diagnostics.composition_states_rejected_hard += 1
        return None
    validated = validated_applied_repairs(
        source,
        tuple(action.repair for action in actions),
        spurs,
        minimum_improvement_m=settings.minimum_structural_improvement_m,
    )
    if len(validated) != len(actions):
        diagnostics.composition_states_rejected_target_loss += 1
        return None
    diagnostics.composition_states_qualifying += 1
    return replace(
        state,
        objective_components=replace(
            state.objective_components,
            analyzed_total_spur_repetition_m=spurs.total_repeated_distance_m,
        ),
        applied_spur_repairs=tuple(
            sorted(validated, key=AppliedSpurRepair.ordering_key)
        ),
    )


def validated_applied_repairs(
    source: OptimizationSource,
    repairs: tuple[AppliedSpurRepair, ...],
    spurs: RouteSpurAnalysis,
    *,
    minimum_improvement_m: float,
) -> tuple[AppliedSpurRepair, ...]:
    """Retain only repairs still confirmed material by final PR19 matching."""
    return tuple(
        result.validated
        for result in applied_repair_validations(
            source,
            repairs,
            spurs,
            minimum_improvement_m=minimum_improvement_m,
        )
        if result.validated is not None
    )


def applied_repair_validations(
    source: OptimizationSource,
    repairs: tuple[AppliedSpurRepair, ...],
    spurs: RouteSpurAnalysis,
    *,
    minimum_improvement_m: float,
) -> tuple[AppliedSpurRepairValidation, ...]:
    """Return one stable validation record per applied major repair."""
    values: list[AppliedSpurRepairValidation] = []
    for repair in repairs:
        residual = _matching_residual(source, repair, spurs.spurs)
        improvement = repair.source_repeated_distance_m - residual
        validated = (
            None
            if improvement + _EPSILON_M < minimum_improvement_m
            else replace(
                repair,
                resulting_repeated_distance_m=residual,
                improvement_m=improvement,
            )
        )
        values.append(
            AppliedSpurRepairValidation(
                source=repair,
                validated=validated,
                resulting_repeated_distance_m=residual,
                resulting_improvement_m=improvement,
            )
        )
    return tuple(sorted(values, key=lambda result: result.source.ordering_key()))


def _analyzed_spurs(
    source: OptimizationSource,
    state: TourOptimizationState,
    result_factory: RouteResultFactory,
) -> RouteSpurAnalysis:
    route = result_factory.create(
        name=source.route.name,
        path=state.complete_path,
        input_point_count=max(2, len(state.anchors)),
        routing_profile=source.routing_profile,
    )
    cumulative = 0.0
    anchors: list[SpurTraversalAnchor] = []
    for index, anchor in enumerate(state.anchors):
        progress = (
            cumulative / state.complete_path.distance_m
            if state.complete_path.distance_m > 0
            else 0.0
        )
        if anchor.kind == "soft":
            anchors.append(
                SpurTraversalAnchor(
                    id=anchor.id,
                    name=anchor.name,
                    route_progress=progress,
                )
            )
        if index < len(state.path_options):
            cumulative += state.path_options[index].distance_m
    return detect_route_spurs(route, tuple(anchors), topology=source.topology)


def _matching_residual(
    source: OptimizationSource,
    repair: AppliedSpurRepair,
    resulting: tuple[RouteSpur, ...],
) -> float:
    source_spur = next(
        (
            spur
            for spur in source.route.analysis.spurs.spurs
            if spur.id == repair.spur_id
        ),
        None,
    )
    if source_spur is None:
        return repair.source_repeated_distance_m
    stop_ids = _normalized_stop_ids(repair.stop_ids)
    if stop_ids:
        matches = tuple(
            spur
            for spur in resulting
            if stop_ids & _normalized_stop_ids(spur.deliberate_stop_ids)
        )
        return max((spur.repeated_distance_m for spur in matches), default=0.0)
    stop_names = _normalized_stop_names(repair.stop_names)
    if stop_names:
        matches = tuple(
            spur
            for spur in resulting
            if stop_names & _normalized_stop_names(spur.deliberate_stop_names)
        )
        if not matches:
            return 0.0
        return min(
            matches,
            key=lambda spur: (
                haversine_distance_m(
                    spur.turnaround_coordinate,
                    source_spur.turnaround_coordinate,
                ),
                -spur.repeated_distance_m,
                spur.id,
            ),
        ).repeated_distance_m
    matches = tuple(
        spur
        for spur in resulting
        if haversine_distance_m(
            spur.turnaround_coordinate,
            source_spur.turnaround_coordinate,
        )
        <= 200.0
    )
    return max((spur.repeated_distance_m for spur in matches), default=0.0)


def _composition_key(
    source: OptimizationSource,
    state: TourOptimizationState,
) -> tuple[object, ...]:
    objective = state.objective_components
    return (
        0 if objective.hard_feasible else 1,
        -objective.priority_weighted_coverage,
        -len(state.applied_spur_repairs),
        -sum(repair.improvement_m for repair in state.applied_spur_repairs),
        objective.opposite_direction_reuse_m,
        objective.total_repeated_distance_m,
        objective.immediate_backtracking_m,
        max(0.0, objective.distance_m - source.route.summary.distance_m),
        state.stable_signature,
    )


def _normalized_stop_ids(values: tuple[str, ...]) -> frozenset[str]:
    return frozenset(value.removeprefix("stop/") for value in values)


def _normalized_stop_names(values: tuple[str, ...]) -> frozenset[str]:
    return frozenset(" ".join(value.casefold().split()) for value in values if value)
