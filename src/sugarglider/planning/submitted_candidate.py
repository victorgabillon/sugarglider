"""Neutral trust validation for a submitted canonical candidate."""

from sugarglider.analysis.route import haversine_distance_m
from sugarglider.planning.direction.analysis import analyze_route_direction
from sugarglider.planning.direction.traversal import build_plan_traversal
from sugarglider.planning.drafts import CandidateDraft
from sugarglider.planning.models import (
    AutoTourPlanRequest,
    PlanRequest,
    WaypointPlanRequest,
)
from sugarglider.planning.result import PlanCandidate
from sugarglider.planning.signatures import candidate_signature
from sugarglider.planning.validation import validate_search_candidate


class SubmittedCandidateInvalidError(ValueError):
    """A submitted request/candidate pair cannot be trusted."""


def validate_submitted_candidate(
    request: PlanRequest,
    candidate: PlanCandidate,
) -> None:
    """Recompute candidate identity, traversal, exactness, and route fidelity."""
    if candidate.kind != request.kind:
        raise SubmittedCandidateInvalidError("submitted planning kind mismatch")
    if candidate.topology != request.topology:
        raise SubmittedCandidateInvalidError("submitted topology mismatch")
    if candidate.routing_profile != request.routing_profile:
        raise SubmittedCandidateInvalidError("submitted profile mismatch")
    if candidate.route.routing_profile != request.routing_profile:
        raise SubmittedCandidateInvalidError("submitted route profile mismatch")
    if len(candidate.route.geometry) < 2:
        raise SubmittedCandidateInvalidError("submitted geometry is incomplete")
    if candidate.id != candidate_signature(
        candidate.route,
        topology=request.topology,
        routing_profile=request.routing_profile,
    ):
        raise SubmittedCandidateInvalidError("submitted candidate signature mismatch")
    try:
        validate_search_candidate(request, candidate)
    except ValueError as exc:
        raise SubmittedCandidateInvalidError(
            "submitted candidate validation failed"
        ) from exc
    expected_traversal = build_plan_traversal(
        request,
        CandidateDraft(
            route=candidate.route,
            routing_points=(),
            topology=request.topology,
            construction="submitted_candidate_validation",
            search_family="submitted_candidate",
            reached_stops=candidate.reached_stops,
            approximated_stops=candidate.approximated_stops,
            dropped_stops=candidate.dropped_stops,
            compromises=candidate.compromises,
        ),
    )
    if candidate.traversal != expected_traversal:
        raise SubmittedCandidateInvalidError("submitted traversal metadata mismatch")
    if candidate.traversal.direction != analyze_route_direction(
        candidate.route.geometry, request.topology
    ):
        raise SubmittedCandidateInvalidError("submitted traversal direction mismatch")
    first = candidate.traversal.anchors[0]
    if (
        haversine_distance_m(
            (first.routed_coordinate.lon, first.routed_coordinate.lat),
            candidate.route.geometry[0],
        )
        > 1
    ):
        raise SubmittedCandidateInvalidError("submitted traversal start mismatch")
    if request.topology == "point_to_point":
        last = candidate.traversal.anchors[-1]
        if (
            haversine_distance_m(
                (last.routed_coordinate.lon, last.routed_coordinate.lat),
                candidate.route.geometry[-1],
            )
            > 1
        ):
            raise SubmittedCandidateInvalidError("submitted traversal end mismatch")
    if _exact_ids(request) != {
        anchor.id.removeprefix("exact/")
        for anchor in candidate.traversal.anchors
        if anchor.kind == "exact_waypoint"
    }:
        raise SubmittedCandidateInvalidError("submitted exact constraints mismatch")


def _exact_ids(request: PlanRequest) -> set[str]:
    if isinstance(request, AutoTourPlanRequest):
        return {waypoint.id for waypoint in request.hard_waypoints}
    if isinstance(request, WaypointPlanRequest):
        return {
            waypoint.id
            for waypoint in request.waypoints
            if waypoint.constraint_strength == "exact"
        }
    return set()
