"""Exact endpoint-fixed native Waypoint controls."""

from sugarglider.planning.models import WaypointPlanRequest
from sugarglider.planning.waypoint.models import WaypointSequenceProposal


def control_proposal(request: WaypointPlanRequest) -> WaypointSequenceProposal:
    """Build the one mandatory sequence without changing any exact point."""
    if request.topology == "loop":
        exact = (request.start, *request.waypoints, request.start)
        original_indices = (0, *range(1, len(request.waypoints) + 1), 0)
    else:
        assert request.end is not None
        exact = (request.start, *request.waypoints, request.end)
        original_indices = tuple(range(len(exact)))
    return WaypointSequenceProposal(
        routing_points=exact,
        exact_points=exact,
        exact_point_positions=tuple(range(len(exact))),
        original_indices=original_indices,
        topology=request.topology,
        construction="fixed_control",
        order_provenance="fixed",
    )
