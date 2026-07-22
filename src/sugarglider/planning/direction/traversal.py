"""Build public traversal anchors once from final evaluator inputs."""

from shapely.geometry import Point

from sugarglider.analysis.projection import LocalMetricProjection
from sugarglider.domain.models import Coordinate, GeoJsonPosition
from sugarglider.planning.direction.analysis import analyze_route_direction
from sugarglider.planning.drafts import CandidateDraft
from sugarglider.planning.models import (
    AutoTourPlanRequest,
    ConstraintStrength,
    ExactWaypoint,
    PlanRequestBase,
    RouteWaypoint,
    WaypointPlanRequest,
)
from sugarglider.planning.result import (
    PlanTraversal,
    PlanTraversalAnchor,
    ReachedPlanStop,
    TraversalAnchorKind,
)


def build_plan_traversal(
    request: PlanRequestBase, draft: CandidateDraft
) -> PlanTraversal:
    """Attach only deliberate, graph-reached anchors in routed order."""
    geometry = draft.route.geometry
    anchors: list[PlanTraversalAnchor] = [
        PlanTraversalAnchor(
            id="endpoint/start",
            name=request.start.name or "Start",
            kind="start",
            routed_coordinate=_coordinate(geometry[0], request.start.name),
            semantic_coordinate=request.start,
            route_progress=0.0,
            constraint_strength="exact",
            outcome="reached",
        )
    ]
    exact: tuple[ExactWaypoint | RouteWaypoint, ...]
    if isinstance(request, AutoTourPlanRequest):
        exact = request.hard_waypoints
    elif isinstance(request, WaypointPlanRequest):
        exact = tuple(
            waypoint
            for waypoint in request.waypoints
            if waypoint.constraint_strength == "exact"
        )
    else:
        exact = ()
    for waypoint in exact:
        coordinate = waypoint.coordinate
        progress, routed = _locate(geometry, coordinate)
        anchors.append(
            PlanTraversalAnchor(
                id=f"exact/{waypoint.id}",
                name=waypoint.name,
                kind="exact_waypoint",
                routed_coordinate=routed,
                semantic_coordinate=coordinate,
                route_progress=progress,
                constraint_strength="exact",
                outcome="reached",
            )
        )
    strengths = _requested_strengths(request)
    for stop in draft.reached_stops:
        if not _is_deliberate(stop):
            continue
        kind: TraversalAnchorKind = (
            "requested_stop"
            if stop.selection_origin == "requested"
            else "deliberate_discovered_stop"
        )
        anchors.append(
            PlanTraversalAnchor(
                id=f"stop/{stop.id}",
                name=stop.name,
                kind=kind,
                routed_coordinate=stop.resolved_approach.coordinate,
                semantic_coordinate=stop.semantic_coordinate,
                route_progress=stop.route_progress,
                constraint_strength=strengths.get(stop.id),
                outcome="reached",
            )
        )
    for approximation in draft.approximated_stops:
        anchors.append(
            PlanTraversalAnchor(
                id=f"stop/{approximation.id}",
                name=approximation.name,
                kind="approximated_stop",
                routed_coordinate=approximation.resolved_approach.coordinate,
                semantic_coordinate=approximation.semantic_coordinate,
                route_progress=approximation.route_progress,
                constraint_strength=strengths.get(approximation.id, "best_effort"),
                outcome="approximated",
            )
        )
    if request.topology == "point_to_point":
        anchors.append(
            PlanTraversalAnchor(
                id="endpoint/end",
                name=request.effective_end.name or "End",
                kind="end",
                routed_coordinate=_coordinate(geometry[-1], request.effective_end.name),
                semantic_coordinate=request.effective_end,
                route_progress=1.0,
                constraint_strength="exact",
                outcome="reached",
            )
        )
    ordered = tuple(
        sorted(
            anchors,
            key=lambda anchor: (
                anchor.route_progress,
                0 if anchor.kind == "start" else 2 if anchor.kind == "end" else 1,
                anchor.id,
            ),
        )
    )
    return PlanTraversal(
        direction=analyze_route_direction(geometry, request.topology),
        anchors=ordered,
    )


def _requested_strengths(
    request: PlanRequestBase,
) -> dict[str, ConstraintStrength]:
    if isinstance(request, AutoTourPlanRequest):
        return {stop.id: stop.constraint_strength for stop in request.requested_stops}
    if isinstance(request, WaypointPlanRequest):
        return {
            waypoint.id: waypoint.constraint_strength
            for waypoint in request.waypoints
            if waypoint.constraint_strength != "exact"
        }
    return {}


def _is_deliberate(stop: ReachedPlanStop) -> bool:
    return (
        stop.selection_origin in {"requested", "user_preferred"}
        or stop.selection_method != "already_reached"
    )


def _locate(
    geometry: tuple[GeoJsonPosition, ...], coordinate: Coordinate
) -> tuple[float, Coordinate]:
    projection = LocalMetricProjection(geometry[0][1])
    line = projection.project_line(geometry)
    point = Point(projection.project_position((coordinate.lon, coordinate.lat)))
    distance = line.project(point)
    routed = line.interpolate(distance)
    lon, lat = projection.unproject_position((routed.x, routed.y))
    return (distance / line.length if line.length > 0 else 0.0), Coordinate(
        lat=lat, lon=lon
    )


def _coordinate(position: GeoJsonPosition, name: str | None) -> Coordinate:
    return Coordinate(lat=position[1], lon=position[0], name=name)
