"""Convert routed Waypoint proposals to shared drafts."""

from sugarglider.planning.drafts import CandidateDraft
from sugarglider.planning.models import WaypointPlanRequest
from sugarglider.planning.waypoint.models import WaypointSequenceProposal
from sugarglider.routing.backend import RoutedPath
from sugarglider.routing.result import RouteResultFactory


def waypoint_draft(
    *,
    request: WaypointPlanRequest,
    proposal: WaypointSequenceProposal,
    path: RoutedPath,
    result_factory: RouteResultFactory,
) -> CandidateDraft:
    route = result_factory.create(
        name=request.name,
        path=path,
        input_point_count=len(proposal.routing_points),
    )
    return CandidateDraft(
        route=route,
        routing_points=proposal.routing_points,
        topology=request.topology,
        construction=proposal.construction,
        search_family=(
            "waypoint_control"
            if proposal.construction == "fixed_control"
            else "waypoint_ordering"
        ),
        exact_waypoint_indices=proposal.original_indices,
        metadata=(
            ("original_indices", repr(proposal.original_indices)),
            ("order_provenance", proposal.order_provenance),
            ("detour_provenance", proposal.detour_provenance or "none"),
            (
                "portfolio_reservation",
                "standard_control"
                if proposal.construction == "fixed_control"
                else "none",
            ),
        ),
    )
