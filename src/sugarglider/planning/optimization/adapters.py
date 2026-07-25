"""Mode-neutral translation from finalized PR21 anchor sources."""

from __future__ import annotations

from sugarglider.planning.optimization.models import (
    OptimizationAnchor,
    OptimizationSource,
)
from sugarglider.planning.optimization.source_models import (
    SemanticOptimizationSource,
)
from sugarglider.planning.result import PlanCandidate


def optimization_source(
    source: SemanticOptimizationSource,
    candidate: PlanCandidate,
) -> OptimizationSource:
    """Translate semantic anchors without treating route geometry as stops."""
    requested_ids = (
        {
            stop.id
            for stop in candidate.reached_stops
            if stop.selection_origin == "requested"
        }
        | {
            stop.id
            for stop in candidate.approximated_stops
            if stop.selection_origin == "requested"
        }
        | {
            stop.id
            for stop in candidate.dropped_stops
            if stop.selection_origin == "requested"
        }
    )
    discovered_ids = {
        stop.id
        for stop in candidate.reached_stops
        if stop.selection_origin != "requested"
    } | {
        stop.id
        for stop in candidate.approximated_stops
        if stop.selection_origin != "requested"
    }
    window = 0
    anchors: list[OptimizationAnchor] = []
    for index, anchor in enumerate(source.source_anchor_order):
        if index > 0 and anchor.kind == "exact":
            window += 1
        containing = tuple(
            spur
            for spur in source.route.analysis.spurs.spurs
            if (
                anchor.id in spur.deliberate_stop_ids
                or f"stop/{anchor.id}" in spur.deliberate_stop_ids
            )
        )
        anchors.append(
            OptimizationAnchor(
                id=anchor.id,
                name=anchor.name,
                coordinate=anchor.coordinate,
                semantic_coordinate=anchor.semantic_coordinate,
                kind=anchor.kind,
                source_progress=anchor.route_progress,
                exact_window=window,
                constraint_strength=anchor.constraint_strength,
                outcome=anchor.outcome,
                selected_approach=anchor.current_approach,
                approach_options=tuple(
                    sorted(
                        {
                            option.id: option
                            for option in (
                                *(
                                    (anchor.current_approach,)
                                    if anchor.current_approach
                                    else ()
                                ),
                                *anchor.approach_candidates,
                            )
                        }.values(),
                        key=lambda option: (
                            option.semantic_distance_m,
                            option.id,
                        ),
                    )
                ),
                maximum_semantic_distance_m=(anchor.maximum_semantic_distance_m),
                requested=anchor.id in requested_ids,
                discovered=anchor.id in discovered_ids,
                containing_spur_ids=tuple(spur.id for spur in containing),
                containing_spur_names=tuple(
                    dict.fromkeys(
                        name
                        for spur in containing
                        for name in spur.deliberate_stop_names
                        if name.strip()
                    )
                ),
            )
        )
    return OptimizationSource(
        source_candidate_id=source.source_candidate_id,
        route=source.route,
        routed_path=source.routed_path,
        anchors=tuple(anchors),
        topology=source.topology,
        routing_profile=source.profile,
        target_distance_m=source.target_distance_m,
        tolerance_m=source.tolerance_m,
        distance_priority=source.distance_priority,
        maximum_distance_m=source.maximum_distance_m,
        reached_requested_ids=frozenset(
            stop.id
            for stop in candidate.reached_stops
            if stop.selection_origin == "requested"
        ),
        approximated_requested_ids=frozenset(
            stop.id
            for stop in candidate.approximated_stops
            if stop.selection_origin == "requested"
        ),
        dropped_requested_ids=frozenset(
            stop.id
            for stop in candidate.dropped_stops
            if stop.selection_origin == "requested"
        ),
    )


def requested_outcomes_regress(
    source: PlanCandidate,
    optimized: PlanCandidate,
) -> bool:
    """Reject any global move that weakens requested-place coverage."""
    source_reached = {
        stop.id for stop in source.reached_stops if stop.selection_origin == "requested"
    }
    source_approximated = {
        stop.id
        for stop in source.approximated_stops
        if stop.selection_origin == "requested"
    }
    optimized_reached = {
        stop.id
        for stop in optimized.reached_stops
        if stop.selection_origin == "requested"
    }
    optimized_approximated = {
        stop.id
        for stop in optimized.approximated_stops
        if stop.selection_origin == "requested"
    }
    return bool(
        source_reached - optimized_reached
        or source_approximated - optimized_reached - optimized_approximated
    )
