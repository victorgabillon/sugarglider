"""Complete-state construction, incremental leg reuse, and Pareto archive."""

from __future__ import annotations

from hashlib import sha256

from sugarglider.planning.optimization.models import (
    AppliedSpurRepair,
    GlobalOptimizationSettings,
    OptimizationAnchor,
    OptimizationMove,
    OptimizationOperatorKind,
    OptimizationSource,
    PathOption,
    PathOptionSourceKind,
    TourOptimizationState,
)
from sugarglider.planning.optimization.objective import (
    objective_for_path,
    pareto_dominates,
)
from sugarglider.planning.optimization.path_pool import LazyPathPool
from sugarglider.routing.backend import RoutedPath
from sugarglider.routing.composition import (
    RouteCompositionError,
    compose_routed_segments,
)


async def initial_state(
    source: OptimizationSource,
    path_pool: LazyPathPool,
) -> TourOptimizationState | None:
    seeded = path_pool.seed_source(source)
    if len(source.anchors) == 1:
        return _state(
            source=source,
            anchors=source.anchors,
            options=(),
            complete_path=source.routed_path,
            operator=None,
            applied_spur_repairs=(),
            analyzed_total_spur_repetition_m=(
                source.route.analysis.spurs.total_repeated_distance_m
            ),
        )
    if len(seeded) != len(source.anchors) - 1:
        options: list[PathOption] = []
        for left, right in zip(source.anchors, source.anchors[1:], strict=False):
            available = await path_pool.options_for(left, right)
            if not available:
                return None
            options.append(available[0])
        seeded = tuple(options)
    try:
        complete = compose_routed_segments(
            tuple(option.routed_path for option in seeded)
        )
    except RouteCompositionError:
        return None
    return _state(
        source=source,
        anchors=source.anchors,
        options=seeded,
        complete_path=complete,
        operator=None,
        applied_spur_repairs=(),
        analyzed_total_spur_repetition_m=(
            source.route.analysis.spurs.total_repeated_distance_m
        ),
    )


async def apply_move(
    source: OptimizationSource,
    current: TourOptimizationState,
    move: OptimizationMove,
    path_pool: LazyPathPool,
) -> TourOptimizationState | None:
    """Reuse unchanged legs and lazily route only changed directed pairs."""
    if not _exact_anchors_preserved(source.anchors, move.anchors):
        return None
    forced = dict(move.forced_path_option_by_leg)
    previous = {
        (
            left.id,
            right.id,
            left.coordinate.lat,
            left.coordinate.lon,
            right.coordinate.lat,
            right.coordinate.lon,
        ): option
        for (left, right), option in zip(
            zip(current.anchors, current.anchors[1:], strict=False),
            current.path_options,
            strict=True,
        )
    }
    selected: list[PathOption] = []
    for leg_index, (left, right) in enumerate(
        zip(move.anchors, move.anchors[1:], strict=False)
    ):
        key = (
            left.id,
            right.id,
            left.coordinate.lat,
            left.coordinate.lon,
            right.coordinate.lat,
            right.coordinate.lon,
        )
        reusable = previous.get(key)
        if reusable is not None and leg_index not in forced:
            selected.append(reusable)
            continue
        source_kind: PathOptionSourceKind = (
            "relocation_connector"
            if move.operator == "alternate_approach"
            else (
                "spur_connector" if move.operator == "spur_rejoin" else "lazy_move_leg"
            )
        )
        available = await path_pool.options_for(
            left,
            right,
            source_kind=source_kind,
        )
        if not available:
            return None
        forced_id = forced.get(leg_index)
        option = (
            next((value for value in available if value.id == forced_id), None)
            if forced_id is not None
            else available[0]
        )
        if option is None:
            return None
        selected.append(option)
    repairs = _retained_repairs(current.applied_spur_repairs, tuple(selected))
    if move.applied_spur_repair is not None:
        repairs = tuple(
            repair
            for repair in repairs
            if (
                repair.target_stable_id != move.applied_spur_repair.target_stable_id
                and repair.containing_leg_index
                != move.applied_spur_repair.containing_leg_index
            )
        ) + (move.applied_spur_repair,)
    return state_from_selected_path_options(
        source=source,
        anchors=move.anchors,
        options=tuple(selected),
        operator=move.operator,
        applied_spur_repairs=repairs,
        analyzed_total_spur_repetition_m=(
            current.objective_components.analyzed_total_spur_repetition_m
        ),
    )


def state_from_selected_path_options(
    *,
    source: OptimizationSource,
    anchors: tuple[OptimizationAnchor, ...],
    options: tuple[PathOption, ...],
    operator: OptimizationOperatorKind | None,
    applied_spur_repairs: tuple[AppliedSpurRepair, ...],
    analyzed_total_spur_repetition_m: float | None,
) -> TourOptimizationState | None:
    """Synchronously construct a complete state without routing or pool mutation."""
    if not _exact_anchors_preserved(source.anchors, anchors):
        return None
    try:
        complete = compose_routed_segments(
            tuple(option.routed_path for option in options)
        )
    except RouteCompositionError:
        return None
    return _state(
        source=source,
        anchors=anchors,
        options=options,
        complete_path=complete,
        operator=operator,
        applied_spur_repairs=tuple(
            sorted(applied_spur_repairs, key=AppliedSpurRepair.ordering_key)
        ),
        analyzed_total_spur_repetition_m=analyzed_total_spur_repetition_m,
    )


class ParetoArchive:
    """Small deterministic non-dominated archive of feasible complete states."""

    def __init__(self, settings: GlobalOptimizationSettings) -> None:
        self._limit = settings.pareto_archive_size
        self._states: dict[str, TourOptimizationState] = {}

    def add(self, state: TourOptimizationState) -> bool:
        if not state.objective_components.hard_feasible:
            return False
        if state.stable_signature in self._states:
            return False
        if any(
            pareto_dominates(existing.objective_components, state.objective_components)
            for existing in self._states.values()
        ):
            return False
        self._states = {
            signature: existing
            for signature, existing in self._states.items()
            if not pareto_dominates(
                state.objective_components, existing.objective_components
            )
        }
        self._states[state.stable_signature] = state
        ordered = sorted(
            self._states.values(),
            key=lambda value: (
                value.objective_components.lexicographic_key(),
                value.stable_signature,
            ),
        )[: self._limit]
        self._states = {value.stable_signature: value for value in ordered}
        return state.stable_signature in self._states

    def states(self) -> tuple[TourOptimizationState, ...]:
        return tuple(
            sorted(
                self._states.values(),
                key=lambda value: (
                    value.objective_components.lexicographic_key(),
                    value.stable_signature,
                ),
            )
        )


def _state(
    *,
    source: OptimizationSource,
    anchors: tuple[OptimizationAnchor, ...],
    options: tuple[PathOption, ...],
    complete_path: RoutedPath,
    operator: OptimizationOperatorKind | None,
    applied_spur_repairs: tuple[AppliedSpurRepair, ...],
    analyzed_total_spur_repetition_m: float | None,
) -> TourOptimizationState:
    objective, edge_usage = objective_for_path(
        source,
        complete_path,
        options,
        analyzed_total_spur_repetition_m=analyzed_total_spur_repetition_m,
    )
    selected_targets = tuple(
        (anchor.id, anchor.selected_approach.id)
        for anchor in anchors
        if anchor.selected_approach is not None
    )
    signature = sha256(
        repr(
            (
                source.source_candidate_id,
                tuple(
                    (
                        anchor.id,
                        anchor.coordinate.lat,
                        anchor.coordinate.lon,
                    )
                    for anchor in anchors
                ),
                tuple(option.id for option in options),
            )
        ).encode()
    ).hexdigest()[:24]
    return TourOptimizationState(
        source_candidate_id=source.source_candidate_id,
        topology=source.topology,
        routing_profile=source.routing_profile,
        anchors=anchors,
        ordered_anchor_ids=tuple(anchor.id for anchor in anchors),
        selected_target_by_anchor=selected_targets,
        selected_path_option_by_leg=tuple(option.id for option in options),
        path_options=options,
        exact_window_by_anchor=tuple(
            (anchor.id, anchor.exact_window) for anchor in anchors
        ),
        visited_requested_stop_ids=source.reached_requested_ids
        | source.approximated_requested_ids,
        visited_discovered_poi_ids=frozenset(
            anchor.id for anchor in anchors if anchor.discovered
        ),
        edge_usage=edge_usage,
        objective_components=objective,
        complete_path=complete_path,
        stable_signature=signature,
        last_operator=operator,
        applied_spur_repairs=applied_spur_repairs,
    )


def _exact_anchors_preserved(
    source: tuple[OptimizationAnchor, ...],
    proposed: tuple[OptimizationAnchor, ...],
) -> bool:
    def exact(
        anchors: tuple[OptimizationAnchor, ...],
    ) -> tuple[tuple[str, float, float], ...]:
        return tuple(
            (anchor.id, anchor.coordinate.lat, anchor.coordinate.lon)
            for anchor in anchors
            if anchor.kind == "exact"
        )

    return exact(source) == exact(proposed) and {anchor.id for anchor in source} == {
        anchor.id for anchor in proposed
    }


def _retained_repairs(
    repairs: tuple[AppliedSpurRepair, ...],
    options: tuple[PathOption, ...],
) -> tuple[AppliedSpurRepair, ...]:
    return tuple(
        repair
        for repair in repairs
        if (
            repair.containing_leg_index < len(options)
            and options[repair.containing_leg_index].id
            == repair.replacement_path_option_id
        )
    )
