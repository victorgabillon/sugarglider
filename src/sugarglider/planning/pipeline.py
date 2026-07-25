"""Canonical planning orchestration and shared publication invariants."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from sugarglider.planning.diagnostics import PlanSearchDiagnostics
from sugarglider.planning.models import AutoTourPlanRequest, PlanRequest
from sugarglider.planning.portfolio import ROLE_ORDER, build_portfolio
from sugarglider.planning.result import CandidateRole, PlanCandidate, PlanResult
from sugarglider.planning.structural import (
    StructuralComparison,
    compare_structural_refinement,
)
from sugarglider.planning.validation import (
    CandidateEvaluationError,
    validate_search_candidate,
)

if TYPE_CHECKING:
    from sugarglider.planning.auto_tour.service import AutoTourPlanner
    from sugarglider.planning.direction.models import (
        ReversePlanRequest,
        ReversePlanResponse,
    )
    from sugarglider.planning.direction.service import ReversePlanner
    from sugarglider.planning.models import PlanRequestBase
    from sugarglider.planning.waypoint.service import WaypointPlanner


@dataclass(frozen=True)
class EvaluatedPortfolio:
    """Valid published candidates and explicit producer-draft rejections."""

    candidates: tuple[PlanCandidate, ...]
    rejection_reasons: tuple[str, ...]
    best_excluded_refinement: dict[str, Any] | None = None
    best_excluded_structural_refinements: tuple[dict[str, Any], ...] = ()

    def attach_rejections(
        self, diagnostics: PlanSearchDiagnostics
    ) -> PlanSearchDiagnostics:
        """Expose every canonical rejection without hiding producer diagnostics."""
        if not self.rejection_reasons:
            return diagnostics
        return diagnostics.model_copy(
            update={
                "warnings": tuple(
                    sorted({*diagnostics.warnings, *self.rejection_reasons})
                )
            }
        )


def evaluate_candidate_portfolio(
    request: PlanRequestBase,
    candidates: tuple[PlanCandidate, ...],
    *,
    limit: int,
    ranking_key: Callable[[PlanCandidate], tuple[object, ...]] | None = None,
) -> EvaluatedPortfolio:
    """Validate every routed draft before shared deduplication and role assignment."""
    valid: list[PlanCandidate] = []
    rejections: list[str] = []
    for candidate in candidates:
        try:
            valid.append(validate_search_candidate(request, candidate))
        except CandidateEvaluationError as exc:
            rejections.append(f"candidate_rejected:{candidate.id}:{exc}")
    compared, comparisons = _annotate_structural_comparisons(tuple(valid))
    ordinary = build_portfolio(compared, limit=limit, ranking_key=ranking_key)
    selected, reserved_ids, reservation_failure = _reserve_structural_alternatives(
        ordinary,
        compared,
        comparisons,
        limit=limit,
    )
    selected_ids = {candidate.id for candidate in selected}
    excluded = tuple(
        comparison
        for comparison in comparisons
        if comparison.candidate_id not in selected_ids
    )
    grouped_excluded: dict[frozenset[str], StructuralComparison] = {}
    for comparison in excluded:
        target_set = frozenset(comparison.targeted_spur_ids)
        prior = grouped_excluded.get(target_set)
        if prior is None or _structural_key(comparison) < _structural_key(prior):
            grouped_excluded[target_set] = comparison
    excluded_summaries = tuple(
        comparison.excluded_summary(
            comparison.exclusion_reason
            if not comparison.structurally_dominant
            else (
                "stronger_same_target_refinement_selected"
                if frozenset(comparison.targeted_spur_ids)
                in {
                    frozenset(value.targeted_spur_ids)
                    for value in comparisons
                    if value.candidate_id in reserved_ids
                }
                else reservation_failure or "ordinary_portfolio_exclusion"
            )
        )
        for comparison in sorted(grouped_excluded.values(), key=_structural_key)[:3]
    )
    return EvaluatedPortfolio(
        candidates=selected,
        rejection_reasons=tuple(rejections),
        best_excluded_refinement=(
            excluded_summaries[0] if excluded_summaries else None
        ),
        best_excluded_structural_refinements=excluded_summaries,
    )


def _annotate_structural_comparisons(
    candidates: tuple[PlanCandidate, ...],
) -> tuple[tuple[PlanCandidate, ...], tuple[StructuralComparison, ...]]:
    sources = {candidate.id: candidate for candidate in candidates}
    comparisons: list[StructuralComparison] = []
    annotated: list[PlanCandidate] = []
    for candidate in candidates:
        source_id = candidate.diagnostics.details.get("source_candidate_id")
        source = sources.get(source_id) if isinstance(source_id, str) else None
        comparison = (
            compare_structural_refinement(source, candidate)
            if source is not None
            else None
        )
        if comparison is None:
            annotated.append(candidate)
            continue
        comparisons.append(comparison)
        annotated.append(
            candidate.model_copy(
                update={
                    "diagnostics": candidate.diagnostics.model_copy(
                        update={
                            "details": {
                                **candidate.diagnostics.details,
                                **comparison.safe_details(),
                            }
                        }
                    )
                }
            )
        )
    return tuple(annotated), tuple(comparisons)


def _reserve_structural_alternatives(
    ordinary: tuple[PlanCandidate, ...],
    candidates: tuple[PlanCandidate, ...],
    comparisons: tuple[StructuralComparison, ...],
    *,
    limit: int,
) -> tuple[tuple[PlanCandidate, ...], tuple[str, ...], str | None]:
    qualifying = tuple(
        sorted(
            (
                comparison
                for comparison in comparisons
                if comparison.structurally_dominant
            ),
            key=_structural_key,
        )
    )
    if not qualifying:
        return ordinary, (), None
    by_id = {candidate.id: candidate for candidate in candidates}
    slot_a = qualifying[0]
    slot_b = (
        min(
            (
                comparison
                for comparison in qualifying[1:]
                if set(comparison.targeted_spur_ids) - set(slot_a.targeted_spur_ids)
            ),
            key=lambda comparison: _distinct_structural_key(comparison, slot_a),
            default=None,
        )
        if limit >= 3
        else None
    )
    reservations = (slot_a,) + ((slot_b,) if slot_b is not None else ())
    selected: list[PlanCandidate] = [ordinary[0]]
    maximum_coverage = max(
        candidate.diagnostics.requested_stop_count for candidate in candidates
    )
    maximum_candidates = tuple(
        candidate
        for candidate in candidates
        if candidate.diagnostics.requested_stop_count == maximum_coverage
    )
    if (
        len(maximum_candidates) == 1
        and maximum_candidates[0].id != selected[0].id
        and len(selected) < limit
    ):
        selected.append(maximum_candidates[0])
    roles: dict[str, CandidateRole] = {}
    for index, comparison in enumerate(reservations):
        candidate = by_id[comparison.candidate_id]
        roles[candidate.id] = (
            "best_structural_refinement"
            if index == 0
            else "distinct_structural_refinement"
        )
        if (
            candidate.id not in {value.id for value in selected}
            and len(selected) < limit
        ):
            selected.append(candidate)
    for candidate in ordinary:
        if (
            candidate.id not in {value.id for value in selected}
            and len(selected) < limit
        ):
            selected.append(candidate)
    ranked = tuple(
        _assign_one_structural_role(candidate, roles.get(candidate.id), rank)
        for rank, candidate in enumerate(selected, start=1)
    )
    reserved_ids = tuple(comparison.candidate_id for comparison in reservations)
    failure = (
        "no_target_diverse_structural_refinement"
        if limit >= 3 and slot_b is None
        else None
    )
    return ranked, reserved_ids, failure


def _assign_one_structural_role(
    candidate: PlanCandidate,
    role: CandidateRole | None,
    rank: int,
) -> PlanCandidate:
    roles = set(candidate.roles)
    if role is not None:
        roles.add(role)
    return candidate.model_copy(
        update={
            "rank": rank,
            "roles": tuple(sorted(roles, key=ROLE_ORDER.__getitem__)),
        }
    )


def _distinct_structural_key(
    comparison: StructuralComparison,
    selected: StructuralComparison,
) -> tuple[object, ...]:
    novel = set(comparison.targeted_spur_ids) - set(selected.targeted_spur_ids)
    novel_improvement = sum(
        improvement
        for target_id, improvement in comparison.targeted_spur_improvements_m
        if target_id in novel
    )
    return (
        -len(novel),
        -novel_improvement,
        *_structural_shape_key(comparison),
        comparison.candidate_id,
    )


def _structural_shape_key(
    comparison: StructuralComparison,
) -> tuple[float, float, float, float, float]:
    return (
        -comparison.maximum_structural_improvement_m,
        -comparison.opposite_direction_improvement_m,
        -comparison.spur_repeated_distance_improvement_m,
        -comparison.immediate_backtracking_improvement_m,
        max(0.0, comparison.distance_change_m),
    )


def _structural_key(
    comparison: StructuralComparison,
) -> tuple[object, ...]:
    return (
        0 if comparison.structurally_dominant else 1,
        *_structural_shape_key(comparison),
        comparison.candidate_id,
    )


class PlanService:
    """Dispatch one strict request union to mode-specific candidate producers."""

    def __init__(
        self,
        *,
        auto_tour: AutoTourPlanner,
        waypoint: WaypointPlanner,
        reverse: ReversePlanner,
    ) -> None:
        self._auto_tour = auto_tour
        self._waypoint = waypoint
        self._reverse = reverse

    async def generate(self, request: PlanRequest) -> PlanResult:
        if isinstance(request, AutoTourPlanRequest):
            return await self._auto_tour.generate(request)
        return await self._waypoint.generate(request)

    async def reverse(self, request: ReversePlanRequest) -> ReversePlanResponse:
        return await self._reverse.reverse(request)
