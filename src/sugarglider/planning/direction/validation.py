"""Reject untrusted or inconsistent source candidates before rerouting."""

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


class ReverseSourceInvalidError(ValueError):
    """The posted source request and candidate do not form a trusted pair."""


def validate_reverse_source(request: PlanRequest, candidate: PlanCandidate) -> None:
    """Validate recomputable identity, geometry, traversal, profile, and exactness."""
    if candidate.kind != request.kind:
        raise ReverseSourceInvalidError("source planning kind mismatch")
    if candidate.topology != request.topology:
        raise ReverseSourceInvalidError("source topology mismatch")
    if candidate.routing_profile != request.routing_profile:
        raise ReverseSourceInvalidError("source profile mismatch")
    if candidate.route.routing_profile != request.routing_profile:
        raise ReverseSourceInvalidError("source route profile mismatch")
    if len(candidate.route.geometry) < 2:
        raise ReverseSourceInvalidError("source geometry is incomplete")
    if candidate.id != candidate_signature(
        candidate.route,
        topology=request.topology,
        routing_profile=request.routing_profile,
    ):
        raise ReverseSourceInvalidError("source candidate signature mismatch")
    try:
        validate_search_candidate(request, candidate)
    except ValueError as exc:
        raise ReverseSourceInvalidError("source candidate validation failed") from exc
    expected_traversal = build_plan_traversal(
        request,
        CandidateDraft(
            route=candidate.route,
            routing_points=(),
            topology=request.topology,
            construction="reverse_source_validation",
            search_family="reverse",
            reached_stops=candidate.reached_stops,
            approximated_stops=candidate.approximated_stops,
            dropped_stops=candidate.dropped_stops,
            compromises=candidate.compromises,
        ),
    )
    if candidate.traversal != expected_traversal:
        raise ReverseSourceInvalidError("source traversal metadata mismatch")
    if candidate.traversal.direction != analyze_route_direction(
        candidate.route.geometry, request.topology
    ):
        raise ReverseSourceInvalidError("source traversal direction mismatch")
    first = candidate.traversal.anchors[0]
    if (
        haversine_distance_m(
            (first.routed_coordinate.lon, first.routed_coordinate.lat),
            candidate.route.geometry[0],
        )
        > 1
    ):
        raise ReverseSourceInvalidError("source traversal start mismatch")
    if request.topology == "point_to_point":
        last = candidate.traversal.anchors[-1]
        if (
            haversine_distance_m(
                (last.routed_coordinate.lon, last.routed_coordinate.lat),
                candidate.route.geometry[-1],
            )
            > 1
        ):
            raise ReverseSourceInvalidError("source traversal end mismatch")
    expected_exact = _exact_ids(request)
    actual_exact = {
        anchor.id.split("/", 1)[1]
        for anchor in candidate.traversal.anchors
        if anchor.kind == "exact_waypoint"
    }
    if expected_exact != actual_exact:
        raise ReverseSourceInvalidError("source exact constraints mismatch")


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
