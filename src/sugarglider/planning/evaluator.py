"""Shared final candidate-evaluation and publication lifecycle."""

from dataclasses import replace
from typing import Protocol

from sugarglider.planning.drafts import CandidateDraft
from sugarglider.planning.models import PlanRequestBase
from sugarglider.planning.result import (
    PlanCandidate,
    PlanCandidateDiagnostics,
    PlanScore,
)
from sugarglider.planning.signatures import candidate_signature
from sugarglider.planning.validation import validate_search_candidate
from sugarglider.routing.result import RouteResultFactory


class CandidateScorer(Protocol):
    def score(
        self, *, request: PlanRequestBase, draft: CandidateDraft
    ) -> PlanScore: ...


class CandidateEvaluator:
    """Validate and enrich a complete draft exactly once before portfolio work."""

    def __init__(self, result_factory: RouteResultFactory | None = None) -> None:
        self._result_factory = result_factory

    def evaluate(
        self,
        *,
        request: PlanRequestBase,
        draft: CandidateDraft,
        scorer: CandidateScorer,
    ) -> PlanCandidate:
        route = draft.route
        if self._result_factory is not None:
            if draft.routed_path is None:
                raise ValueError("final candidate enrichment requires its routed path")
            route = self._result_factory.create(
                name=route.name,
                path=draft.routed_path,
                input_point_count=route.summary.input_point_count,
            )
            draft = replace(draft, route=route)
        score = scorer.score(request=request, draft=draft)
        target_error_m = abs(
            route.summary.distance_m - request.distance_objective.target_m
        )
        maximum_distance_m = (
            draft.maximum_distance_m
            if draft.maximum_distance_m is not None
            else request.distance_objective.maximum_m
        )
        analysis = route.analysis
        candidate = PlanCandidate(
            id=candidate_signature(route, topology=draft.topology),
            rank=1,
            roles=(),
            route=route,
            score=score,
            selected_stops=draft.selected_stops,
            dropped_stops=draft.dropped_stops,
            diagnostics=PlanCandidateDiagnostics(
                safety_eligible=(
                    draft.structural_safety_eligible
                    and (
                        maximum_distance_m is None
                        or route.summary.distance_m <= maximum_distance_m
                    )
                ),
                target_error_m=target_error_m,
                within_tolerance=(
                    target_error_m <= request.distance_objective.tolerance_m
                ),
                requested_stop_count=sum(
                    stop.selection_origin == "requested"
                    for stop in draft.selected_stops
                ),
                immediate_backtracking_m=(analysis.immediate_backtrack.distance_m),
                repeated_distance_m=(analysis.repetition.repeated_distance.distance_m),
                details={
                    "construction": draft.construction,
                    "search_family": draft.search_family,
                    **dict(draft.metadata),
                },
            ),
        )
        return validate_search_candidate(request, candidate)
