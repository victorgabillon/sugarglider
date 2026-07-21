"""Route canonical Waypoint proposals through the shared gateway."""

from sugarglider.planning.budget import SearchPhase
from sugarglider.planning.context import PlanningSearchContext
from sugarglider.planning.models import WaypointPlanRequest
from sugarglider.planning.validation import validate_waypoint_path
from sugarglider.planning.waypoint.models import WaypointSequenceProposal
from sugarglider.routing.backend import RoutedPath


async def route_proposal(
    *,
    request: WaypointPlanRequest,
    proposal: WaypointSequenceProposal,
    context: PlanningSearchContext,
    phase: SearchPhase | None = None,
) -> RoutedPath:
    path = await context.routes.route(
        proposal.routing_points,
        request.routing_profile,
        pass_through=request.topology == "point_to_point",
        phase=phase
        or (
            SearchPhase.CONTROL
            if proposal.construction == "fixed_control"
            else SearchPhase.SKELETON
        ),
        topology_options=(("topology", request.topology),),
    )
    return validate_waypoint_path(proposal, path)
