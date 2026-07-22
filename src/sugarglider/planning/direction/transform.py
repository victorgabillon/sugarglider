"""Pure canonical request transformation for opposite traversal intent."""

from sugarglider.planning.models import (
    AutoTourPlanRequest,
    AutoTourPreferences,
    PlanRequest,
    RouteWaypoint,
    WaypointPlanRequest,
)
from sugarglider.planning.result import PlanCandidate, RouteTraversalDirection


def transform_reverse_request(
    request: PlanRequest, candidate: PlanCandidate, *, candidate_count: int
) -> PlanRequest:
    """Reverse endpoints and ordered intent without weakening constraints."""
    endpoints: dict[str, object] = {"candidate_count": candidate_count}
    if request.topology == "point_to_point":
        assert request.end is not None
        endpoints.update(start=request.end, end=request.start)
    if isinstance(request, AutoTourPlanRequest):
        preferences = request.preferences
        if request.topology == "loop":
            preferences = preferences.model_copy(
                update={
                    "direction": _opposite_preference(
                        preferences, candidate.traversal.direction
                    )
                }
            )
        return request.model_copy(
            update={
                **endpoints,
                "preferences": preferences,
                "hard_waypoints": tuple(reversed(request.hard_waypoints)),
                "requested_stops": tuple(reversed(request.requested_stops)),
            }
        )
    if isinstance(request, WaypointPlanRequest):
        waypoints = (
            tuple(reversed(request.waypoints))
            if request.waypoint_order == "fixed"
            else _reverse_actual_waypoint_order(request, candidate)
        )
        return request.model_copy(update={**endpoints, "waypoints": waypoints})
    raise TypeError("unsupported canonical plan request")


def _reverse_actual_waypoint_order(
    request: WaypointPlanRequest, candidate: PlanCandidate
) -> tuple[RouteWaypoint, ...]:
    by_id = {waypoint.id: waypoint for waypoint in request.waypoints}
    actual_ids = [
        anchor.id.split("/", 1)[1]
        for anchor in candidate.traversal.anchors
        if anchor.kind in {"exact_waypoint", "requested_stop", "approximated_stop"}
        and anchor.id.split("/", 1)[1] in by_id
    ]
    missing = [
        waypoint.id for waypoint in request.waypoints if waypoint.id not in actual_ids
    ]
    ordered_ids = (*actual_ids, *missing)
    return tuple(by_id[waypoint_id] for waypoint_id in reversed(ordered_ids))


def _opposite_preference(
    preferences: AutoTourPreferences,
    selected_direction: RouteTraversalDirection,
) -> str:
    if preferences.direction == "clockwise":
        return "counterclockwise"
    if preferences.direction == "counterclockwise":
        return "clockwise"
    if selected_direction == "clockwise":
        return "counterclockwise"
    if selected_direction == "counterclockwise":
        return "clockwise"
    return "any"
