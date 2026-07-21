"""Pure Auto Tour search support and beam pruning."""

# mypy: disable-error-code="attr-defined"

from shapely.geometry import Point

from sugarglider.analysis.open_route import analyze_open_route
from sugarglider.analysis.projection import LocalMetricProjection
from sugarglider.analysis.route import haversine_distance_m
from sugarglider.domain.models import Coordinate, RouteResult
from sugarglider.planning.auto_tour.candidate_models import (
    AutoTourCandidate,
)
from sugarglider.planning.auto_tour.models import (
    AutoTourSearchRequest,
)
from sugarglider.planning.auto_tour.ranking import (
    auto_tour_ranking_key,
    maximum_auto_tour_distance_m,
    score_route,
    soft_distance_penalty,
)
from sugarglider.planning.auto_tour.state import (
    ROUTE_CLOSURE_TOLERANCE_M,
    _Draft,
    _InsertionState,
)
from sugarglider.routing.backend import (
    RoutedPath,
)


def _valid_closed_geometry(path: RoutedPath) -> bool:
    return (
        len(path.geometry) >= 4
        and haversine_distance_m(path.geometry[0], path.geometry[-1])
        <= ROUTE_CLOSURE_TOLERANCE_M
    )


def _hard_waypoints_selected(draft: _Draft) -> bool:
    return all(visit.selected for visit in draft.hard_point_visits)


def _control_key(draft: _Draft, request: AutoTourSearchRequest) -> tuple[object, ...]:
    route = draft.route
    error = abs(route.summary.distance_m - request.target_distance_m)
    within = error <= request.tolerance_m
    geometry = route.analysis.loop_geometry
    nature = route.analysis.nature
    common = (
        0 if _hard_waypoints_selected(draft) else 1,
        route.analysis.immediate_backtrack.share,
        route.analysis.repetition.repeated_distance.share,
        (0, geometry.penalty_breakdown.total) if geometry is not None else (1, 0.0),
        (
            (0, -nature.nature_score)
            if request.nature_preference == "prefer" and nature is not None
            else (1, 0.0)
            if request.nature_preference == "prefer"
            else (0, 0.0)
        ),
        score_route(route, request.target_distance_m).total,
        draft.signature,
    )
    if request.distance_priority == "strict":
        return (
            common[0],
            0 if within else 1,
            0.0 if within else error,
            *common[1:],
        )
    highly_mixed = (
        draft.direction == "mixed"
        and "auto_tour_direction_highly_mixed" in draft.direction_warnings
    )
    return (
        common[0],
        1 if highly_mixed else 0,
        common[1],
        geometry.outbound_return_proximity.share if geometry is not None else 1.0,
        common[2],
        common[3],
        soft_distance_penalty(
            distance_m=route.summary.distance_m,
            target_distance_m=request.target_distance_m,
            tolerance_m=request.tolerance_m,
            priority=request.distance_priority,
        ),
        *common[4:],
    )


def _retain_diverse_controls(
    controls: tuple[_Draft, ...], limit: int, request: AutoTourSearchRequest
) -> tuple[_Draft, ...]:
    retained: list[_Draft] = []

    def retain(candidate: _Draft | None) -> None:
        if (
            candidate is not None
            and len(retained) < limit
            and candidate.signature not in {value.signature for value in retained}
        ):
            retained.append(candidate)

    retain(min(controls, key=lambda value: _control_key(value, request)))
    sampled_controls = tuple(
        value
        for value in controls
        if value.skeleton_method == "graphhopper_round_trip_sampled"
    )
    retain(
        min(
            sampled_controls,
            key=lambda value: _control_key(value, request),
            default=None,
        )
    )
    retain(
        min(
            controls,
            key=lambda value: (
                value.route.analysis.immediate_backtrack.share,
                value.route.analysis.repetition.repeated_distance.share,
                value.signature,
            ),
        )
    )
    retain(
        min(
            controls,
            key=lambda value: (
                value.route.analysis.repetition.repeated_distance.share,
                value.route.analysis.immediate_backtrack.share,
                value.signature,
            ),
        )
    )
    geometry_controls = tuple(
        value for value in controls if value.route.analysis.loop_geometry is not None
    )
    retain(
        min(
            geometry_controls,
            key=lambda value: (
                value.route.analysis.loop_geometry.penalty_breakdown.total  # type: ignore[union-attr]
            ),
            default=None,
        )
    )
    for direction in ("clockwise", "counterclockwise"):
        matching = tuple(value for value in controls if value.direction == direction)
        retain(
            min(matching, key=lambda value: _control_key(value, request), default=None)
        )
    for candidate in sorted(controls, key=lambda value: _control_key(value, request)):
        retain(candidate)
    return tuple(retained)


def _prune_insertion_beam(
    states: tuple[_InsertionState, ...], width: int
) -> tuple[_InsertionState, ...]:
    retained: list[_InsertionState] = []

    def retain(value: _InsertionState | None) -> None:
        if (
            value is not None
            and len(retained) < width
            and value.candidate.signature
            not in {state.candidate.signature for state in retained}
        ):
            retained.append(value)

    retain(min(states, key=lambda value: auto_tour_ranking_key(value.candidate)))
    retain(
        max(
            states,
            key=lambda value: (
                value.candidate.discovered_poi_reward,
                -value.candidate.target_error_m,
                value.candidate.signature,
            ),
        )
    )
    retain(
        max(
            states,
            key=lambda value: (
                len({visit.poi.category for visit in value.candidate.poi_visits}),
                value.candidate.discovered_poi_reward,
                value.candidate.signature,
            ),
        )
    )
    water = tuple(
        value for value in states if value.candidate.selected_verified_water_count > 0
    )
    retain(
        max(
            water,
            key=lambda value: (
                value.candidate.discovered_poi_reward,
                value.candidate.signature,
            ),
            default=None,
        )
    )
    retain(
        min(
            states,
            key=lambda value: (
                value.candidate.target_error_m,
                value.candidate.signature,
            ),
        )
    )
    for value in sorted(states, key=lambda item: auto_tour_ranking_key(item.candidate)):
        retain(value)
    return tuple(retained)


def _deduplicate_drafts(drafts: tuple[_Draft, ...]) -> tuple[_Draft, ...]:
    distinct: dict[str, _Draft] = {}
    for draft in drafts:
        distinct.setdefault(draft.signature, draft)
    return tuple(distinct.values())


def _deduplicate_candidates(
    candidates: tuple[AutoTourCandidate, ...],
) -> tuple[AutoTourCandidate, ...]:
    distinct: dict[str, AutoTourCandidate] = {}
    for candidate in candidates:
        distinct.setdefault(candidate.signature, candidate)
    return tuple(distinct.values())


def _with_open_metrics(
    candidate: AutoTourCandidate, direct_route: RouteResult
) -> AutoTourCandidate:
    metrics = analyze_open_route(
        geometry=candidate.route.geometry,
        route_distance_m=candidate.route.summary.distance_m,
        direct_geometry=direct_route.geometry,
        direct_distance_m=direct_route.summary.distance_m,
    )
    return candidate.model_copy(
        update={
            "direct_distance_m": metrics.direct_distance_m,
            "detour_ratio": metrics.detour_ratio,
            "destination_progress_monotonicity": (
                metrics.destination_progress_monotonicity
            ),
            "reverse_progress_distance_m": metrics.reverse_progress_distance_m,
            "reverse_progress_share": metrics.reverse_progress_share,
            "endpoint_axis_lateral_deviation_m": (
                metrics.endpoint_axis_lateral_deviation_m
            ),
            "near_parallel_corridor_share": metrics.near_parallel_corridor_share,
        }
    )


def _without_loop_geometry(route: RouteResult) -> RouteResult:
    """Mark loop-only analysis not applicable on a public open route."""
    if route.analysis.loop_geometry is None:
        return route
    return route.model_copy(
        update={"analysis": route.analysis.model_copy(update={"loop_geometry": None})}
    )


def _hard_waypoints_by_direct_progress(
    points: tuple[Coordinate, ...],
    direct_geometry: tuple[tuple[float, float], ...],
) -> tuple[Coordinate, ...]:
    """Deterministically seed open hard-point order from direct-route progress."""
    if len(points) < 2:
        return points
    projection = LocalMetricProjection(
        sum(latitude for _, latitude in direct_geometry) / len(direct_geometry)
    )
    line = projection.project_line(direct_geometry)
    return tuple(
        point
        for _, _, point in sorted(
            (
                line.project(
                    Point(projection.project_position((point.lon, point.lat)))
                ),
                index,
                point,
            )
            for index, point in enumerate(points)
        )
    )


def _maximum_distance(request: AutoTourSearchRequest) -> float:
    return maximum_auto_tour_distance_m(
        request.target_distance_m,
        request.tolerance_m,
        priority=request.distance_priority,
        requested_maximum_distance_m=request.maximum_distance_m,
    )
