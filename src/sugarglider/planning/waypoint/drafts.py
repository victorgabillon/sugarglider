"""Convert routed Waypoint proposals to shared drafts."""

from sugarglider.planning.constraints.outcomes import constraint_outcomes
from sugarglider.planning.constraints.resolver import ConstraintResolution
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
    constraint_resolutions: tuple[ConstraintResolution, ...] = (),
    metadata: tuple[tuple[str, str], ...] = (),
) -> CandidateDraft:
    route = result_factory.create(
        name=request.name,
        path=path,
        input_point_count=len(proposal.routing_points),
        routing_profile=request.routing_profile,
    )
    reached, approximated, dropped, compromises = constraint_outcomes(
        route.geometry,
        request.routing_profile,
        constraint_resolutions,
        category="route_waypoint",
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
        reached_stops=reached,
        approximated_stops=approximated,
        dropped_stops=dropped,
        compromises=compromises,
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
            *metadata,
        ),
    )
