"""Safe structural comparisons and bounded refinement dominance."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sugarglider.analysis.route import (
    opposite_direction_reuse_distance_m,
    project_geometry_edges,
)
from sugarglider.domain.analysis import RouteSpur
from sugarglider.planning.profile_quality import profile_quality_components
from sugarglider.planning.result import PlanCandidate
from sugarglider.pois.models import AccessStatus

STRUCTURAL_CONSTRUCTIONS = frozenset({"edge_aware_global_optimization"})
_EPSILON_M = 1e-6


@dataclass(frozen=True)
class StructuralDominanceSettings:
    """Immutable product thresholds for a display-worthy route-shape alternative."""

    minimum_structural_improvement_m: float = 500.0
    maximum_extra_distance_share: float = 0.05
    maximum_extra_distance_m: float = 2_000.0

    def __post_init__(self) -> None:
        if self.minimum_structural_improvement_m <= 0:
            raise ValueError("minimum structural improvement must be positive")
        if not 0 <= self.maximum_extra_distance_share <= 1:
            raise ValueError(
                "maximum extra-distance share must be between zero and one"
            )
        if self.maximum_extra_distance_m < 0:
            raise ValueError("maximum extra distance must be non-negative")


@dataclass(frozen=True)
class StructuralComparison:
    """Public-safe final comparison of one refinement with its source."""

    candidate_id: str
    source_candidate_id: str
    construction: str
    targeted_spur_ids: tuple[str, ...]
    targeted_spur_names: tuple[str, ...]
    targeted_spur_improvements_m: tuple[tuple[str, float], ...]
    source_spur_repeated_distance_m: float
    resulting_spur_repeated_distance_m: float
    spur_repeated_distance_improvement_m: float
    source_opposite_direction_reuse_m: float
    resulting_opposite_direction_reuse_m: float
    opposite_direction_improvement_m: float
    source_immediate_backtracking_m: float
    resulting_immediate_backtracking_m: float
    immediate_backtracking_improvement_m: float
    source_total_repetition_m: float
    resulting_total_repetition_m: float
    total_repetition_improvement_m: float
    distance_change_m: float
    reached_change: int
    approximated_change: int
    dropped_change: int
    profile_regression: bool
    exact_constraints_preserved: bool
    structurally_dominant: bool
    exclusion_reason: str | None

    @property
    def maximum_structural_improvement_m(self) -> float:
        return max(
            self.spur_repeated_distance_improvement_m,
            self.opposite_direction_improvement_m,
            self.immediate_backtracking_improvement_m,
            self.total_repetition_improvement_m,
        )

    def safe_details(self) -> dict[str, Any]:
        """Return only explainable public values, never graph-edge evidence."""
        return {
            "source_candidate_id": self.source_candidate_id,
            "construction": self.construction,
            "targeted_spur_ids": self.targeted_spur_ids,
            "targeted_spur_names": self.targeted_spur_names,
            "source_spur_repeated_distance_m": (self.source_spur_repeated_distance_m),
            "resulting_spur_repeated_distance_m": (
                self.resulting_spur_repeated_distance_m
            ),
            "spur_repeated_distance_improvement_m": (
                self.spur_repeated_distance_improvement_m
            ),
            "source_opposite_direction_reuse_m": (
                self.source_opposite_direction_reuse_m
            ),
            "resulting_opposite_direction_reuse_m": (
                self.resulting_opposite_direction_reuse_m
            ),
            "opposite_direction_improvement_m": (self.opposite_direction_improvement_m),
            "source_immediate_backtracking_m": (self.source_immediate_backtracking_m),
            "resulting_immediate_backtracking_m": (
                self.resulting_immediate_backtracking_m
            ),
            "immediate_backtracking_improvement_m": (
                self.immediate_backtracking_improvement_m
            ),
            "source_total_repetition_m": self.source_total_repetition_m,
            "resulting_total_repetition_m": self.resulting_total_repetition_m,
            "total_repetition_improvement_m": (self.total_repetition_improvement_m),
            "distance_change_m": self.distance_change_m,
            "reached_change": self.reached_change,
            "approximated_change": self.approximated_change,
            "dropped_change": self.dropped_change,
            "profile_regression": self.profile_regression,
            "exact_constraints_preserved": self.exact_constraints_preserved,
            "structurally_dominant": self.structurally_dominant,
        }

    def excluded_summary(self, reason: str | None = None) -> dict[str, Any]:
        return {
            **self.safe_details(),
            "target_count": len(self.targeted_spur_ids),
            "reason_excluded": reason or self.exclusion_reason or "portfolio_exclusion",
        }


def compare_structural_refinement(
    source: PlanCandidate,
    refined: PlanCandidate,
    *,
    settings: StructuralDominanceSettings | None = None,
) -> StructuralComparison | None:
    """Compare a PR20/PR21 result with its fully evaluated source candidate."""
    construction = str(refined.diagnostics.details.get("construction", ""))
    source_id = refined.diagnostics.details.get("source_candidate_id")
    if (
        construction not in STRUCTURAL_CONSTRUCTIONS
        or not isinstance(source_id, str)
        or source_id != source.id
    ):
        return None
    resolved = settings or StructuralDominanceSettings()
    targeted = _targeted_spurs(
        source,
        refined,
        construction,
        minimum_improvement_m=resolved.minimum_structural_improvement_m,
    )
    source_spur_m = sum(value[0].repeated_distance_m for value in targeted)
    resulting_spur_m = sum(value[1] for value in targeted)
    spur_improvement_m = source_spur_m - resulting_spur_m
    source_backtrack_m = source.diagnostics.immediate_backtracking_m
    result_backtrack_m = refined.diagnostics.immediate_backtracking_m
    source_opposite_m = _opposite_direction_reuse(source)
    result_opposite_m = _opposite_direction_reuse(refined)
    source_repetition_m = source.diagnostics.repeated_distance_m
    result_repetition_m = refined.diagnostics.repeated_distance_m
    distance_change_m = (
        refined.route.summary.distance_m - source.route.summary.distance_m
    )
    reached_change, approximated_change, dropped_change = _requested_changes(
        source, refined
    )
    coverage_regression = _requested_coverage_regresses(source, refined)
    access_regression = _requested_access_regresses(source, refined)
    exact_preserved = _exact_anchor_identity(source) == _exact_anchor_identity(refined)
    _result_penalty, _result_components, result_severe = profile_quality_components(
        refined.route
    )
    profile_regression = result_severe
    maximum_improvement = max(
        spur_improvement_m,
        source_opposite_m - result_opposite_m,
        source_backtrack_m - result_backtrack_m,
        source_repetition_m - result_repetition_m,
    )
    maximum_extra_m = min(
        source.route.summary.distance_m * resolved.maximum_extra_distance_share,
        resolved.maximum_extra_distance_m,
    )
    exclusion_reason: str | None = None
    if not exact_preserved:
        exclusion_reason = "exact_constraints_not_preserved"
    elif coverage_regression:
        exclusion_reason = "requested_coverage_regression"
    elif profile_regression:
        exclusion_reason = "severe_profile_regression"
    elif access_regression:
        exclusion_reason = "unsafe_access_regression"
    elif not refined.diagnostics.safety_eligible:
        exclusion_reason = "hard_validity_failure"
    elif result_repetition_m > source_repetition_m + _EPSILON_M:
        exclusion_reason = "total_repetition_worsened"
    elif distance_change_m > maximum_extra_m + _EPSILON_M:
        exclusion_reason = "distance_increase_exceeded_rule"
    elif maximum_improvement + _EPSILON_M < (resolved.minimum_structural_improvement_m):
        exclusion_reason = "insufficient_structural_improvement"
    return StructuralComparison(
        candidate_id=refined.id,
        source_candidate_id=source.id,
        construction=construction,
        targeted_spur_ids=tuple(value[0].id for value in targeted),
        targeted_spur_names=_safe_spur_names(targeted),
        targeted_spur_improvements_m=tuple(
            (spur.id, spur.repeated_distance_m - residual)
            for spur, residual in targeted
        ),
        source_spur_repeated_distance_m=source_spur_m,
        resulting_spur_repeated_distance_m=resulting_spur_m,
        spur_repeated_distance_improvement_m=spur_improvement_m,
        source_opposite_direction_reuse_m=source_opposite_m,
        resulting_opposite_direction_reuse_m=result_opposite_m,
        opposite_direction_improvement_m=source_opposite_m - result_opposite_m,
        source_immediate_backtracking_m=source_backtrack_m,
        resulting_immediate_backtracking_m=result_backtrack_m,
        immediate_backtracking_improvement_m=(source_backtrack_m - result_backtrack_m),
        source_total_repetition_m=source_repetition_m,
        resulting_total_repetition_m=result_repetition_m,
        total_repetition_improvement_m=(source_repetition_m - result_repetition_m),
        distance_change_m=distance_change_m,
        reached_change=reached_change,
        approximated_change=approximated_change,
        dropped_change=dropped_change,
        profile_regression=profile_regression,
        exact_constraints_preserved=exact_preserved,
        structurally_dominant=exclusion_reason is None,
        exclusion_reason=exclusion_reason,
    )


def _opposite_direction_reuse(candidate: PlanCandidate) -> float:
    projection = project_geometry_edges(
        geometry=candidate.route.geometry,
        route_distance_m=candidate.route.summary.distance_m,
        path_details=candidate.route.path_details,
    )
    return opposite_direction_reuse_distance_m(projection.edges)


def _targeted_spurs(
    source: PlanCandidate,
    refined: PlanCandidate,
    construction: str,
    *,
    minimum_improvement_m: float,
) -> tuple[tuple[RouteSpur, float], ...]:
    source_spurs = source.route.analysis.spurs.spurs
    result_spurs = refined.route.analysis.spurs.spurs
    affected = tuple(
        (spur, _matching_spur_distance(spur, result_spurs)) for spur in source_spurs
    )
    return tuple(
        value
        for value in affected
        if value[0].repeated_distance_m - value[1] >= minimum_improvement_m - _EPSILON_M
    )


def _matching_spur_distance(
    source: RouteSpur,
    candidates: tuple[RouteSpur, ...],
) -> float:
    source_ids = set(source.deliberate_stop_ids)
    identity_matches = tuple(
        spur
        for spur in candidates
        if source_ids and source_ids.intersection(spur.deliberate_stop_ids)
    )
    pool = identity_matches or tuple(
        spur
        for spur in candidates
        if _interval_overlap(source, spur) > 0
        or abs(source.turnaround_progress - spur.turnaround_progress) <= 0.10
    )
    if not pool:
        return 0.0
    matched = min(
        pool,
        key=lambda spur: (
            -len(source_ids.intersection(spur.deliberate_stop_ids)),
            -_interval_overlap(source, spur),
            abs(source.turnaround_progress - spur.turnaround_progress),
            spur.id,
        ),
    )
    return matched.repeated_distance_m


def _interval_overlap(left: RouteSpur, right: RouteSpur) -> float:
    return max(
        0.0,
        min(left.end_progress, right.end_progress)
        - max(left.start_progress, right.start_progress),
    )


def _safe_spur_names(
    targeted: tuple[tuple[RouteSpur, float], ...],
) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            name
            for spur, _result_distance in targeted
            for name in spur.deliberate_stop_names
            if name.strip()
        )
    )


def _requested_changes(
    source: PlanCandidate, refined: PlanCandidate
) -> tuple[int, int, int]:
    return (
        sum(stop.selection_origin == "requested" for stop in refined.reached_stops)
        - sum(stop.selection_origin == "requested" for stop in source.reached_stops),
        sum(stop.selection_origin == "requested" for stop in refined.approximated_stops)
        - sum(
            stop.selection_origin == "requested" for stop in source.approximated_stops
        ),
        sum(stop.selection_origin == "requested" for stop in refined.dropped_stops)
        - sum(stop.selection_origin == "requested" for stop in source.dropped_stops),
    )


def _requested_coverage_regresses(
    source: PlanCandidate, refined: PlanCandidate
) -> bool:
    source_reached = {
        stop.id for stop in source.reached_stops if stop.selection_origin == "requested"
    }
    source_approximated = {
        stop.id
        for stop in source.approximated_stops
        if stop.selection_origin == "requested"
    }
    refined_reached = {
        stop.id
        for stop in refined.reached_stops
        if stop.selection_origin == "requested"
    }
    refined_approximated = {
        stop.id
        for stop in refined.approximated_stops
        if stop.selection_origin == "requested"
    }
    return bool(
        source_reached - refined_reached
        or source_approximated - refined_reached - refined_approximated
    )


def _requested_access_regresses(source: PlanCandidate, refined: PlanCandidate) -> bool:
    def accesses(candidate: PlanCandidate) -> dict[str, AccessStatus]:
        return {
            stop.id: stop.resolved_approach.access
            for stop in candidate.reached_stops
            if stop.selection_origin == "requested"
        } | {
            stop.id: stop.resolved_approach.access
            for stop in candidate.approximated_stops
            if stop.selection_origin == "requested"
        }

    source_access = accesses(source)
    result_access = accesses(refined)
    return any(
        result_access.get(stop_id) in {"private", "restricted"}
        or (access == "public" and result_access.get(stop_id) not in {"public", None})
        for stop_id, access in source_access.items()
    )


def _exact_anchor_identity(
    candidate: PlanCandidate,
) -> tuple[tuple[str, str, float, float], ...]:
    return tuple(
        (
            anchor.id,
            anchor.kind,
            anchor.semantic_coordinate.lat,
            anchor.semantic_coordinate.lon,
        )
        for anchor in candidate.traversal.anchors
        if anchor.kind in {"start", "end", "exact_waypoint"}
        or anchor.constraint_strength == "exact"
    )
