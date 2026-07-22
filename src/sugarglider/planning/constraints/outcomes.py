"""Shared final soft-constraint outcome construction."""

from shapely.geometry import Point

from sugarglider.analysis.projection import LocalMetricProjection
from sugarglider.analysis.route import haversine_distance_m
from sugarglider.planning.constraints.resolver import ConstraintResolution
from sugarglider.planning.profiles import RoutingProfileId
from sugarglider.planning.result import (
    ApproximatedPlanStop,
    DroppedPlanStop,
    PlanCompromise,
    ReachedPlanStop,
)


def constraint_outcomes(
    geometry: tuple[tuple[float, float], ...],
    profile: RoutingProfileId,
    resolutions: tuple[ConstraintResolution, ...],
    *,
    category: str = "requested_stop",
) -> tuple[
    tuple[ReachedPlanStop, ...],
    tuple[ApproximatedPlanStop, ...],
    tuple[DroppedPlanStop, ...],
    tuple[PlanCompromise, ...],
]:
    """Measure final reached, approximated, and dropped soft constraints."""
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
                    category=category,
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
        route_point = Point(
            projection.project_position(
                (approach.coordinate.lon, approach.coordinate.lat)
            )
        )
        routed_distance = float(line.distance(route_point))
        route_progress = (
            float(line.project(route_point) / line.length) if line.length > 0 else 0.0
        )
        if resolution.status == "reached_approach":
            reached.append(
                ReachedPlanStop(
                    id=resolution.constraint_id,
                    name=resolution.constraint_name,
                    semantic_coordinate=resolution.semantic_coordinate,
                    category=category,
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
                    category=category,
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
