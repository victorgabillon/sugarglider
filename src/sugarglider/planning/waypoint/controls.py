"""Exact endpoint-fixed native Waypoint controls."""

from sugarglider.planning.models import WaypointPlanRequest
from sugarglider.planning.waypoint.models import WaypointSequenceProposal


def control_proposal(request: WaypointPlanRequest) -> WaypointSequenceProposal:
    """Build the one mandatory sequence without changing any exact point."""
    interior = tuple(
        waypoint.coordinate.model_copy(update={"name": waypoint.name})
        for waypoint in request.waypoints
    )
    if request.topology == "loop":
        routing = (request.start, *interior, request.start)
        exact_positions = (
            0,
            *(
                index + 1
                for index, waypoint in enumerate(request.waypoints)
                if waypoint.constraint_strength == "exact"
            ),
            len(routing) - 1,
        )
        original_indices = (0, *(position for position in exact_positions[1:-1]), 0)
        exact_ids = (
            "start",
            *(
                waypoint.id
                for waypoint in request.waypoints
                if waypoint.constraint_strength == "exact"
            ),
            "start",
        )
    else:
        assert request.end is not None
        routing = (request.start, *interior, request.end)
        exact_positions = (
            0,
            *(
                index + 1
                for index, waypoint in enumerate(request.waypoints)
                if waypoint.constraint_strength == "exact"
            ),
            len(routing) - 1,
        )
        original_indices = exact_positions
        exact_ids = (
            "start",
            *(
                waypoint.id
                for waypoint in request.waypoints
                if waypoint.constraint_strength == "exact"
            ),
            "end",
        )
    return WaypointSequenceProposal(
        routing_points=routing,
        exact_points=tuple(routing[position] for position in exact_positions),
        exact_point_positions=exact_positions,
        original_indices=original_indices,
        exact_point_ids=exact_ids,
        topology=request.topology,
        construction="fixed_control",
        order_provenance="fixed",
    )
