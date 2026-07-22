"""Convert routed Waypoint proposals to shared drafts."""

from shapely.geometry import Point

from sugarglider.analysis.projection import LocalMetricProjection
from sugarglider.analysis.route import haversine_distance_m
from sugarglider.planning.constraints.resolver import ConstraintResolution
from sugarglider.planning.drafts import CandidateDraft
from sugarglider.planning.models import WaypointPlanRequest
from sugarglider.planning.profiles import RoutingProfileId
from sugarglider.planning.result import (
    ApproximatedPlanStop,
    DroppedPlanStop,
    PlanCompromise,
    ReachedPlanStop,
)
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
) -> CandidateDraft:
    route = result_factory.create(
        name=request.name,
        path=path,
        input_point_count=len(proposal.routing_points),
        routing_profile=request.routing_profile,
    )
    reached, approximated, dropped, compromises = _constraint_outcomes(
        route.geometry, request.routing_profile, constraint_resolutions
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
        ),
    )


def _constraint_outcomes(
    geometry: tuple[tuple[float, float], ...],
    profile: RoutingProfileId,
    resolutions: tuple[ConstraintResolution, ...],
) -> tuple[
    tuple[ReachedPlanStop, ...],
    tuple[ApproximatedPlanStop, ...],
    tuple[DroppedPlanStop, ...],
    tuple[PlanCompromise, ...],
]:
    reached: list[ReachedPlanStop] = []
    approximated: list[ApproximatedPlanStop] = []
    dropped: list[DroppedPlanStop] = []
    compromises: list[PlanCompromise] = []
    projection = LocalMetricProjection(geometry[0][1])
    line = projection.project_line(geometry)
    for resolution in resolutions:
        if resolution.strength == "exact":
            continue
        approach = resolution.approach
        if resolution.status == "unresolved" or approach is None:
            dropped.append(
                DroppedPlanStop(
                    id=resolution.constraint_id,
                    name=resolution.constraint_name,
                    semantic_coordinate=resolution.semantic_coordinate,
                    category="route_waypoint",
                    selection_origin="requested",
                    reason=resolution.reason,
                )
            )
            compromises.append(
                PlanCompromise(
                    code=(
                        "route_budget_exhausted"
                        if resolution.reason == "route_budget_exhausted"
                        else "no_profile_compatible_approach"
                    ),
                    severity="warning",
                    constraint_id=resolution.constraint_id,
                    constraint_name=resolution.constraint_name,
                    semantic_coordinate=resolution.semantic_coordinate,
                    configured_maximum_m=resolution.configured_maximum_m,
                    reason=resolution.reason,
                    profile=profile,
                    suggestion=(
                        "Move the point, increase its search radius, or remove it."
                    ),
                )
            )
            continue
        routed_distance = float(
            line.distance(
                Point(
                    projection.project_position(
                        (approach.coordinate.lon, approach.coordinate.lat)
                    )
                )
            )
        )
        route_progress = (
            float(
                line.project(
                    Point(
                        projection.project_position(
                            (approach.coordinate.lon, approach.coordinate.lat)
                        )
                    )
                )
                / line.length
            )
            if line.length > 0
            else 0.0
        )
        if resolution.status == "reached_approach":
            reached.append(
                ReachedPlanStop(
                    id=resolution.constraint_id,
                    name=resolution.constraint_name,
                    semantic_coordinate=resolution.semantic_coordinate,
                    category="route_waypoint",
                    selection_origin="requested",
                    selection_method="deliberate_insertion",
                    resolved_approach=approach,
                    route_progress=route_progress,
                    route_to_approach_m=routed_distance,
                )
            )
        else:
            semantic_distance = haversine_distance_m(
                (
                    resolution.semantic_coordinate.lon,
                    resolution.semantic_coordinate.lat,
                ),
                (approach.coordinate.lon, approach.coordinate.lat),
            )
            approximated.append(
                ApproximatedPlanStop(
                    id=resolution.constraint_id,
                    name=resolution.constraint_name,
                    semantic_coordinate=resolution.semantic_coordinate,
                    category="route_waypoint",
                    selection_origin="requested",
                    resolved_approach=approach,
                    route_progress=route_progress,
                    distance_m=semantic_distance,
                    normal_tolerance_m=resolution.normal_tolerance_m,
                    configured_maximum_m=resolution.configured_maximum_m,
                    reason=resolution.reason,
                )
            )
            compromises.append(
                PlanCompromise(
                    code="stop_approximated",
                    severity="warning",
                    constraint_id=resolution.constraint_id,
                    constraint_name=resolution.constraint_name,
                    semantic_coordinate=resolution.semantic_coordinate,
                    routed_coordinate=approach.coordinate,
                    distance_m=semantic_distance,
                    normal_tolerance_m=resolution.normal_tolerance_m,
                    configured_maximum_m=resolution.configured_maximum_m,
                    reason=resolution.reason,
                    profile=profile,
                    suggestion=(
                        "Review the fallback or make the point exact and regenerate."
                    ),
                )
            )
        if "access_unknown" in resolution.warnings:
            compromises.append(
                PlanCompromise(
                    code="access_unknown",
                    severity="warning",
                    constraint_id=resolution.constraint_id,
                    constraint_name=resolution.constraint_name,
                    semantic_coordinate=resolution.semantic_coordinate,
                    routed_coordinate=approach.coordinate,
                    reason="Mapped access is unknown and must be checked locally.",
                    profile=profile,
                    suggestion="Check access, opening, and current conditions locally.",
                )
            )
    return tuple(reached), tuple(approximated), tuple(dropped), tuple(compromises)
