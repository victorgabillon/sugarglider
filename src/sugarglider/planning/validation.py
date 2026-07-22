"""Shared final candidate validation used by all planning modes."""

from shapely.geometry import Point

from sugarglider.analysis.projection import LocalMetricProjection
from sugarglider.analysis.route import haversine_distance_m
from sugarglider.planning.models import (
    AutoTourPlanRequest,
    PlanRequestBase,
    WaypointPlanRequest,
)
from sugarglider.planning.result import PlanCandidate
from sugarglider.planning.waypoint.models import WaypointSequenceProposal
from sugarglider.routing.backend import RoutedPath

ENDPOINT_FIDELITY_M = 300.0
EXACT_WAYPOINT_FIDELITY_M = 300.0


class CandidateEvaluationError(ValueError):
    """A produced candidate violates the canonical publication contract."""


class ExactWaypointNotReachedError(CandidateEvaluationError):
    """GraphHopper snapped one exact mandatory point beyond its hard limit."""

    def __init__(
        self,
        *,
        point_index: int,
        point_name: str | None,
        snap_distance_m: float,
        maximum_snap_distance_m: float,
    ) -> None:
        super().__init__("exact_waypoint_not_reached")
        self.point_index = point_index
        self.point_name = point_name
        self.snap_distance_m = snap_distance_m
        self.maximum_snap_distance_m = maximum_snap_distance_m


def validate_waypoint_path(
    proposal: WaypointSequenceProposal,
    path: RoutedPath,
    *,
    maximum_snap_distance_m: float = EXACT_WAYPOINT_FIDELITY_M,
) -> RoutedPath:
    """Validate backend snaps and topology before building a complete draft."""
    if len(path.geometry) < 2:
        raise CandidateEvaluationError("invalid_geometry")
    snapped = path.snapped_points
    if snapped is None or len(snapped) != len(proposal.routing_points):
        raise CandidateEvaluationError("exact_waypoint_snapped_count_mismatch")
    for position, exact, original_index in zip(
        proposal.exact_point_positions,
        proposal.exact_points,
        proposal.original_indices,
        strict=True,
    ):
        snap_distance_m = haversine_distance_m(
            snapped[position],
            (exact.lon, exact.lat),
        )
        if snap_distance_m > maximum_snap_distance_m:
            raise ExactWaypointNotReachedError(
                point_index=original_index,
                point_name=exact.name,
                snap_distance_m=snap_distance_m,
                maximum_snap_distance_m=maximum_snap_distance_m,
            )
    endpoint_gap_m = haversine_distance_m(path.geometry[0], path.geometry[-1])
    if proposal.topology == "loop" and endpoint_gap_m > ENDPOINT_FIDELITY_M:
        raise CandidateEvaluationError("endpoint_not_reached")
    if proposal.topology == "point_to_point" and path.geometry[0] == path.geometry[-1]:
        raise CandidateEvaluationError("open_route_was_closed")
    return path


def validate_search_candidate(
    request: PlanRequestBase, candidate: PlanCandidate
) -> PlanCandidate:
    """Enforce geometry, endpoints, decisions, and strict stop arrivals once."""
    route = candidate.route
    if (
        candidate.routing_profile != request.routing_profile
        or route.routing_profile != request.routing_profile
    ):
        raise CandidateEvaluationError(
            "candidate routing profile does not match request"
        )
    if len(route.geometry) < 2:
        raise CandidateEvaluationError("candidate geometry is incomplete")
    if (
        haversine_distance_m(route.geometry[0], (request.start.lon, request.start.lat))
        > ENDPOINT_FIDELITY_M
    ):
        raise CandidateEvaluationError("candidate start is not faithfully routed")
    expected_end = request.effective_end
    if (
        haversine_distance_m(route.geometry[-1], (expected_end.lon, expected_end.lat))
        > ENDPOINT_FIDELITY_M
    ):
        raise CandidateEvaluationError("candidate end is not faithfully routed")
    projection = LocalMetricProjection(route.geometry[0][1])
    line = projection.project_line(route.geometry)
    hard_waypoints = (
        request.hard_waypoints
        if isinstance(request, AutoTourPlanRequest)
        else request.waypoints
        if isinstance(request, WaypointPlanRequest)
        else ()
    )
    for waypoint in hard_waypoints:
        measured = float(
            line.distance(
                Point(projection.project_position((waypoint.lon, waypoint.lat)))
            )
        )
        if measured > EXACT_WAYPOINT_FIDELITY_M:
            raise CandidateEvaluationError(
                "candidate did not reach a required waypoint"
            )
    for stop in candidate.selected_stops:
        approach = stop.resolved_approach
        measured = float(
            line.distance(
                Point(
                    projection.project_position(
                        (approach.coordinate.lon, approach.coordinate.lat)
                    )
                )
            )
        )
        if measured > approach.arrival_tolerance_m + 1e-6:
            raise CandidateEvaluationError("selected stop is not reached")
    return candidate
