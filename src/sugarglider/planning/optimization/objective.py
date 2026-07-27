"""Canonical edge-aware objective and fast path-option recomputation."""

from __future__ import annotations

from collections import defaultdict

from sugarglider.analysis.backtracking import (
    DirectedEdgeTraversal,
    measure_immediate_backtracking,
)
from sugarglider.analysis.route import (
    CanonicalEdgeTraversal,
    ProjectedGeometryEdge,
    canonical_edge_traversals,
    project_geometry_edges,
)
from sugarglider.planning.optimization.models import (
    EdgeReuseComponents,
    EdgeUsage,
    OptimizationSource,
    PathOption,
    TourObjective,
)
from sugarglider.routing.backend import RoutedPath


def edge_reuse_components(
    path: RoutedPath,
    options: tuple[PathOption, ...] = (),
) -> EdgeReuseComponents:
    """Measure edge reuse, reusing preprojected unchanged leg contributions."""
    traversals = (
        _merged_option_traversals(options)
        if options
        else canonical_edge_traversals(_project(path))
    )
    seen_directions: dict[int, set[int]] = {}
    same_direction = 0.0
    opposite_direction = 0.0
    usage_counts: dict[int, list[float | int]] = defaultdict(lambda: [0, 0, 0.0, 0.0])
    for traversal in traversals:
        key = traversal.physical_edge_key
        directions = seen_directions.setdefault(key, set())
        if directions:
            if traversal.direction in directions:
                same_direction += traversal.distance_m
            else:
                opposite_direction += traversal.distance_m
        directions.add(traversal.direction)
        raw_usage = usage_counts[key]
        if traversal.direction == 1:
            raw_usage[0] += 1
            raw_usage[2] += traversal.distance_m
        else:
            raw_usage[1] += 1
            raw_usage[3] += traversal.distance_m
    immediate = measure_immediate_backtracking(
        tuple(
            DirectedEdgeTraversal(
                edge_id=edge.physical_edge_key,
                start=edge.start,
                end=edge.end,
                distance_m=edge.distance_m,
            )
            for edge in traversals
        )
    )
    edge_usage = tuple(
        EdgeUsage(
            physical_edge_key=edge_key,
            forward_runs=int(values[0]),
            reverse_runs=int(values[1]),
            forward_distance_m=_stable_metres(float(values[2])),
            reverse_distance_m=_stable_metres(float(values[3])),
        )
        for edge_key, values in sorted(usage_counts.items())
    )
    repeated = _stable_metres(same_direction + opposite_direction)
    return EdgeReuseComponents(
        total_repeated_distance_m=repeated,
        same_direction_reuse_m=_stable_metres(same_direction),
        opposite_direction_reuse_m=_stable_metres(opposite_direction),
        immediate_return_distance_m=_stable_metres(
            immediate.immediate_backtrack_distance_m
        ),
        targeted_spur_repetition_m=0.0,
        edge_usage=edge_usage,
    )


def objective_for_path(
    source: OptimizationSource,
    path: RoutedPath,
    options: tuple[PathOption, ...],
    *,
    analyzed_total_spur_repetition_m: float | None = None,
) -> tuple[TourObjective, tuple[EdgeUsage, ...]]:
    """Build the typed lexicographic objective without public-candidate enrichment."""
    reuse = edge_reuse_components(path, options)
    reached = len(source.reached_requested_ids)
    approximated = len(source.approximated_requested_ids)
    dropped = len(source.dropped_requested_ids)
    distance_error = abs(path.distance_m - source.target_distance_m)
    within_tolerance = distance_error <= source.tolerance_m
    under_maximum = (
        source.maximum_distance_m is None
        or path.distance_m <= source.maximum_distance_m
    )
    profile_feasible = not any(
        option.severe_profile_incompatibility for option in options
    )
    hard_feasible = (
        under_maximum
        and profile_feasible
        and (source.distance_priority != "strict" or within_tolerance)
    )
    nature = source.route.analysis.nature
    return (
        TourObjective(
            hard_feasible=hard_feasible,
            reached_requested=reached,
            approximated_requested=approximated,
            dropped_requested=dropped,
            priority_weighted_coverage=2 * reached + approximated,
            opposite_direction_reuse_m=reuse.opposite_direction_reuse_m,
            analyzed_total_spur_repetition_m=analyzed_total_spur_repetition_m,
            total_repeated_distance_m=reuse.total_repeated_distance_m,
            same_direction_reuse_m=reuse.same_direction_reuse_m,
            immediate_backtracking_m=reuse.immediate_return_distance_m,
            profile_penalty=sum(
                dict(option.path_detail_quality).get("profile_penalty", 0.0)
                for option in options
            ),
            nature_utility=nature.nature_score if nature is not None else 0.0,
            distance_m=path.distance_m,
            distance_error_m=distance_error,
        ),
        reuse.edge_usage,
    )


def objective_improves(left: TourObjective, right: TourObjective) -> bool:
    """Return whether ``left`` is lexicographically better than ``right``."""
    return left.lexicographic_key() < right.lexicographic_key()


def acceptance_energy(objective: TourObjective) -> float:
    """Documented annealing energy used only to escape feasible local optima."""
    if not objective.hard_feasible:
        return float("inf")
    return (
        -objective.priority_weighted_coverage * 1_000_000_000.0
        + objective.opposite_direction_reuse_m * 10_000.0
        + objective.total_repeated_distance_m * 1_000.0
        + objective.immediate_backtracking_m * 500.0
        + objective.profile_penalty * 100.0
        - objective.nature_utility
        + objective.distance_error_m * 0.01
        + objective.distance_m * 0.001
    )


def pareto_dominates(left: TourObjective, right: TourObjective) -> bool:
    """Compare the bounded archive dimensions without construction similarity."""
    left_values = (
        -left.priority_weighted_coverage,
        left.opposite_direction_reuse_m,
        left.total_repeated_distance_m,
        left.immediate_backtracking_m,
        left.profile_penalty,
        -left.nature_utility,
        left.distance_m,
    )
    right_values = (
        -right.priority_weighted_coverage,
        right.opposite_direction_reuse_m,
        right.total_repeated_distance_m,
        right.immediate_backtracking_m,
        right.profile_penalty,
        -right.nature_utility,
        right.distance_m,
    )
    return all(
        left <= right for left, right in zip(left_values, right_values, strict=True)
    ) and any(
        left < right for left, right in zip(left_values, right_values, strict=True)
    )


def _project(path: RoutedPath) -> tuple[ProjectedGeometryEdge, ...]:
    return project_geometry_edges(
        geometry=path.geometry,
        route_distance_m=path.distance_m,
        path_details=path.details,
    ).edges


def _merged_option_traversals(
    options: tuple[PathOption, ...],
) -> tuple[CanonicalEdgeTraversal, ...]:
    values: list[CanonicalEdgeTraversal] = []
    for option in options:
        for traversal in option.directed_edges:
            if (
                values
                and values[-1].physical_edge_key == traversal.physical_edge_key
                and values[-1].direction == traversal.direction
                and values[-1].end == traversal.start
            ):
                prior = values[-1]
                values[-1] = CanonicalEdgeTraversal(
                    physical_edge_key=prior.physical_edge_key,
                    direction=prior.direction,
                    distance_m=prior.distance_m + traversal.distance_m,
                    start=prior.start,
                    end=traversal.end,
                    edge_indices=(*prior.edge_indices, *traversal.edge_indices),
                )
            else:
                values.append(traversal)
    return tuple(values)


def _stable_metres(value: float) -> float:
    """Suppress insignificant projection-boundary drift in incremental scoring."""
    return round(value, 6)
