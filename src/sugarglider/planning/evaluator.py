"""Shared final candidate-evaluation and publication lifecycle."""

from dataclasses import replace
from typing import Protocol

from sugarglider.analysis.spurs import (
    SpurTraversalAnchor,
    detect_route_spurs,
)
from sugarglider.planning.direction.traversal import build_plan_traversal
from sugarglider.planning.drafts import CandidateDraft
from sugarglider.planning.models import PlanRequestBase
from sugarglider.planning.profile_quality import profile_quality_components
from sugarglider.planning.result import (
    PlanCandidate,
    PlanCandidateDiagnostics,
    PlanCompromise,
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
                routing_profile=request.routing_profile,
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
        _quality_total, _quality_components, profile_incompatible = (
            profile_quality_components(route)
        )
        within_tolerance = target_error_m <= request.distance_objective.tolerance_m
        objective = request.distance_objective
        hard_distance_eligible = (
            maximum_distance_m is None or route.summary.distance_m <= maximum_distance_m
        ) and (objective.priority != "strict" or within_tolerance)
        compromises = [*draft.compromises]
        compromised_ids = {
            value.constraint_id for value in compromises if value.constraint_id
        }
        for stop in draft.dropped_stops:
            if stop.selection_origin != "requested" or stop.id in compromised_ids:
                continue
            compromises.append(
                PlanCompromise(
                    code="stop_dropped",
                    severity="warning",
                    constraint_id=stop.id,
                    constraint_name=stop.name,
                    semantic_coordinate=stop.semantic_coordinate,
                    reason=stop.reason,
                    profile=request.routing_profile,
                    suggestion=(
                        "Review the place, provide a safe approach, increase its "
                        "bounded search radius, or remove it."
                    ),
                )
            )
        for reached_stop in draft.reached_stops:
            if (
                reached_stop.selection_origin != "requested"
                or reached_stop.resolved_approach.access != "unknown"
                or any(
                    value.code == "access_unknown"
                    and value.constraint_id == reached_stop.id
                    for value in compromises
                )
            ):
                continue
            compromises.append(
                PlanCompromise(
                    code="access_unknown",
                    severity="warning",
                    constraint_id=reached_stop.id,
                    constraint_name=reached_stop.name,
                    semantic_coordinate=reached_stop.semantic_coordinate,
                    routed_coordinate=reached_stop.resolved_approach.coordinate,
                    reason="Mapped access is unknown and must be checked locally.",
                    profile=request.routing_profile,
                    suggestion="Check access, opening, and current conditions locally.",
                )
            )
        if not within_tolerance and objective.priority != "strict":
            compromises.append(
                PlanCompromise(
                    code="target_distance_missed",
                    severity="warning",
                    distance_m=target_error_m,
                    normal_tolerance_m=objective.tolerance_m,
                    configured_maximum_m=objective.maximum_m,
                    reason=(
                        "The graph-valid route is outside the requested distance "
                        "tolerance; this objective is soft for the selected priority."
                    ),
                    profile=request.routing_profile,
                    suggestion=(
                        "Review the route or use strict distance priority when the "
                        "tolerance must be a hard constraint."
                    ),
                )
            )
        traversal = build_plan_traversal(request, draft)
        spur_analysis = detect_route_spurs(
            route,
            tuple(
                SpurTraversalAnchor(
                    id=anchor.id,
                    name=anchor.name,
                    route_progress=anchor.route_progress,
                )
                for anchor in traversal.anchors
                if anchor.kind not in {"start", "end"}
            ),
            topology=request.topology,
        )
        analysis = analysis.model_copy(update={"spurs": spur_analysis})
        route = route.model_copy(update={"analysis": analysis})
        candidate = PlanCandidate(
            id=candidate_signature(
                route,
                topology=draft.topology,
                routing_profile=request.routing_profile,
            ),
            kind=request.kind,
            topology=request.topology,
            routing_profile=request.routing_profile,
            rank=1,
            roles=(),
            route=route,
            score=score,
            traversal=traversal,
            reached_stops=draft.reached_stops,
            approximated_stops=draft.approximated_stops,
            dropped_stops=draft.dropped_stops,
            compromises=tuple(
                sorted(
                    compromises,
                    key=lambda value: (
                        value.constraint_id or "",
                        value.code,
                        value.reason,
                    ),
                )
            ),
            diagnostics=PlanCandidateDiagnostics(
                safety_eligible=(
                    draft.structural_safety_eligible
                    and not profile_incompatible
                    and hard_distance_eligible
                ),
                target_error_m=target_error_m,
                within_tolerance=within_tolerance,
                requested_stop_count=sum(
                    stop.selection_origin == "requested" for stop in draft.reached_stops
                )
                + sum(
                    stop.selection_origin == "requested"
                    for stop in draft.approximated_stops
                ),
                approximated_stop_count=len(draft.approximated_stops),
                dropped_stop_count=len(draft.dropped_stops),
                immediate_backtracking_m=(analysis.immediate_backtrack.distance_m),
                repeated_distance_m=(analysis.repetition.repeated_distance.distance_m),
                spur_count=spur_analysis.spur_count,
                spur_repeated_distance_m=(spur_analysis.total_repeated_distance_m),
                longest_spur_distance_m=(spur_analysis.longest_spur_distance_m),
                details={
                    "construction": draft.construction,
                    "search_family": draft.search_family,
                    **dict(draft.metadata),
                },
            ),
        )
        return validate_search_candidate(request, candidate)
