"""POI approach and selected-or-dropped decision support."""

# mypy: disable-error-code="attr-defined"

from sugarglider.domain.models import Coordinate
from sugarglider.planning.auto_tour.candidate_models import (
    AutoTourCandidate,
)
from sugarglider.planning.auto_tour.controls import (
    routing_points_with_sampled_hard_anchors,
)
from sugarglider.planning.auto_tour.discovered_pois import (
    InsertedPoiRecord,
    PoiOpportunity,
)
from sugarglider.planning.auto_tour.models import (
    AutoTourSearchRequest,
    DiscoveredPoiVisit,
    PoiDropReason,
    PoiRejectionReason,
    RejectedPoiOpportunity,
    RequestedTourPlace,
    TourControlComparison,
)
from sugarglider.planning.auto_tour.state import (
    MAX_CANDIDATE_REJECTIONS,
    _Draft,
    _SearchState,
)


def _approach_evaluation_points(
    request: AutoTourSearchRequest, control: _Draft
) -> tuple[Coordinate, ...]:
    """Build one complete bounded sequence for comparing requested approaches."""
    requested = tuple(
        request.requested_stops[index].routing_coordinate
        for index in request.interior_requested_place_indices
        if request.requested_stops[index].chosen_approach is not None
    )
    excluded = {
        (request.effective_start.lat, request.effective_start.lon),
        (request.effective_end.lat, request.effective_end.lon),
        *((point.lat, point.lon) for point in requested),
        *((point.lat, point.lon) for point in request.interior_hard_waypoints),
    }
    control_anchors = (
        tuple(
            point
            for point in control.routing_points[1:-1]
            if (point.lat, point.lon) not in excluded
        )
        if request.resolved_endpoints.topology == "loop"
        else ()
    )
    return routing_points_with_sampled_hard_anchors(
        (
            request.effective_start,
            *requested,
            *control_anchors,
            request.effective_end,
        ),
        request.interior_hard_waypoints,
    )


def _bounded_discovered_visits(
    visits: tuple[DiscoveredPoiVisit, ...], preferred_ids: frozenset[str]
) -> tuple[DiscoveredPoiVisit, ...]:
    """Apply deterministic category/spatial diminishing returns before selection."""
    limit = 12
    selected: list[DiscoveredPoiVisit] = []
    selected_ids: set[str] = set()

    def retain(visit: DiscoveredPoiVisit) -> None:
        if visit.poi.id not in selected_ids and len(selected) < limit:
            selected.append(visit)
            selected_ids.add(visit.poi.id)

    for visit in visits:
        if visit.poi.id in preferred_ids or visit.inserted:
            retain(visit)
    remaining = [visit for visit in visits if visit.poi.id not in selected_ids]
    category_counts: dict[str, int] = {}
    while remaining and len(selected) < limit:
        water_progress = tuple(
            value.route_progress_share
            for value in selected
            if value.poi.category == "drinking_water"
        )

        def diminishing_key(
            visit: DiscoveredPoiVisit,
            water_progress_snapshot: tuple[float, ...] = water_progress,
        ) -> tuple[object, ...]:
            category_count = category_counts.get(visit.poi.category, 0)
            crowded_water = visit.poi.category == "drinking_water" and any(
                abs(visit.route_progress_share - progress) < 0.04
                for progress in water_progress_snapshot
            )
            return (
                1 if crowded_water else 0,
                category_count,
                -visit.reward,
                visit.route_progress_share,
                visit.poi.id,
            )

        chosen = min(remaining, key=diminishing_key)
        remaining.remove(chosen)
        retain(chosen)
        category_counts[chosen.poi.category] = (
            category_counts.get(chosen.poi.category, 0) + 1
        )
    return tuple(
        sorted(selected, key=lambda visit: (visit.route_progress_share, visit.poi.id))
    )


def _selected_discovered_count(candidate: AutoTourCandidate) -> int:
    return sum(
        stop.semantic_poi.origin != "requested" for stop in candidate.selected_stops
    )


def _dropped_discovered_count(candidate: AutoTourCandidate) -> int:
    return sum(
        stop.semantic_poi.origin != "requested" for stop in candidate.dropped_stops
    )


def _discovered_decision_count(candidate: AutoTourCandidate) -> int:
    return _selected_discovered_count(candidate) + _dropped_discovered_count(candidate)


def _with_requested_coverage_warning(
    candidate: AutoTourCandidate,
    request: AutoTourSearchRequest,
    control: AutoTourCandidate,
) -> AutoTourCandidate:
    requested_count = (
        candidate.selected_must_visit_count + candidate.selected_preferred_place_count
    )
    control_count = (
        control.selected_must_visit_count + control.selected_preferred_place_count
    )
    if (
        request.distance_priority != "flexible"
        or candidate.route.summary.distance_m
        <= request.target_distance_m + request.tolerance_m
        or requested_count <= control_count
    ):
        return candidate
    return candidate.model_copy(
        update={
            "warnings": tuple(
                sorted(
                    {
                        *candidate.warnings,
                        "target_distance_exceeded_for_requested_coverage",
                    }
                )
            )
        }
    )


def _mark_cross_candidate_requested_routing(
    candidates: tuple[AutoTourCandidate, ...],
) -> tuple[AutoTourCandidate, ...]:
    routed_indices = {
        index
        for candidate in candidates
        for index, visit in enumerate(candidate.requested_place_visits)
        if visit.deliberately_routed
    }
    return tuple(
        candidate.model_copy(
            update={
                "requested_place_visits": tuple(
                    visit.model_copy(
                        update={
                            "deliberately_routed_in_another_retained_candidate": (
                                not visit.deliberately_routed
                                and index in routed_indices
                            )
                        }
                    )
                    for index, visit in enumerate(candidate.requested_place_visits)
                ),
                "dropped_stops": tuple(
                    stop.model_copy(
                        update={
                            "selected_in_another_retained_candidate": (
                                stop.semantic_poi.origin == "requested"
                                and any(
                                    index in routed_indices
                                    and _requested_semantic_id(visit.requested_place)
                                    == stop.semantic_poi.id
                                    for index, visit in enumerate(
                                        candidate.requested_place_visits
                                    )
                                )
                            )
                        }
                    )
                    for stop in candidate.dropped_stops
                ),
            }
        )
        for candidate in candidates
    )


def _apply_requested_search_failure_context(
    candidates: tuple[AutoTourCandidate, ...],
    state: _SearchState,
) -> tuple[AutoTourCandidate, ...]:
    reason = state.full_set_rejection_reason
    if reason not in {
        "requested_place_user_maximum_rejected",
        "requested_place_server_maximum_rejected",
        "requested_place_graph_unreachable",
        "requested_place_search_budget_exhausted",
    }:
        return candidates
    return tuple(
        candidate.model_copy(
            update={
                "requested_place_visits": tuple(
                    visit.model_copy(
                        update={"drop_reason": _requested_drop_reason(reason)}
                    )
                    if not visit.selected
                    and not visit.deliberately_routed
                    and visit.drop_reason
                    in {
                        "route_safety_rejected",
                        "lower_utility_candidate",
                        "maximum_distance_rejected",
                    }
                    else visit
                    for visit in candidate.requested_place_visits
                ),
                "dropped_stops": tuple(
                    stop.model_copy(
                        update={"drop_reason": _requested_drop_reason(reason)}
                    )
                    if stop.semantic_poi.origin == "requested"
                    and stop.drop_reason
                    in {
                        "route_safety_rejected",
                        "lower_utility_candidate",
                        "maximum_distance_rejected",
                    }
                    else stop
                    for stop in candidate.dropped_stops
                ),
            }
        )
        for candidate in candidates
    )


def _remove_coordinate(
    points: tuple[Coordinate, ...], coordinate: Coordinate
) -> tuple[Coordinate, ...] | None:
    for index in range(1, len(points) - 1):
        if _same_coordinate(points[index], coordinate):
            return (*points[:index], *points[index + 1 :])
    return None


def _replace_coordinate(
    points: tuple[Coordinate, ...],
    old_coordinate: Coordinate,
    new_coordinate: Coordinate,
) -> tuple[Coordinate, ...] | None:
    for index in range(1, len(points) - 1):
        if _same_coordinate(points[index], old_coordinate):
            return (*points[:index], new_coordinate, *points[index + 1 :])
    return None


def _same_coordinate(left: Coordinate, right: Coordinate) -> bool:
    return (left.lat, left.lon) == (right.lat, right.lon)


def _records_without_final_deltas(
    records: dict[str, InsertedPoiRecord],
) -> dict[str, InsertedPoiRecord]:
    """Mark marginal deltas unavailable after a global route repair."""
    return {
        poi_id: record
        if record.actual_distance_delta_m is None
        else InsertedPoiRecord(
            estimated_detour_m=record.estimated_detour_m,
            actual_distance_delta_m=None,
            marginal_utility=record.marginal_utility,
        )
        for poi_id, record in records.items()
    }


def _record_rejection(
    state: _SearchState,
    skeleton_id: str,
    opportunity: PoiOpportunity,
    reason: PoiRejectionReason,
    *,
    nearest_distance_m: float | None = None,
) -> None:
    values = state.rejected_by_skeleton.setdefault(skeleton_id, [])
    rejection = RejectedPoiOpportunity(
        poi_id=opportunity.match.feature.id,
        display_name=opportunity.match.feature.display_name,
        category=opportunity.match.feature.category,
        reason_code=reason,
        estimated_detour_m=opportunity.estimated_detour_m,
        nearest_route_distance_m=(
            opportunity.match.distance_m
            if nearest_distance_m is None
            else nearest_distance_m
        ),
    )
    if rejection not in values and len(values) < MAX_CANDIDATE_REJECTIONS:
        values.append(rejection)


def _comparison_rejection_reason(
    comparison: TourControlComparison,
) -> PoiRejectionReason:
    if "distance_tolerance" in comparison.rejection_reasons:
        return "distance_tolerance"
    if "backtracking_regression" in comparison.rejection_reasons:
        return "backtracking_regression"
    if "repetition_regression" in comparison.rejection_reasons:
        return "repetition_regression"
    if "geometry_regression" in comparison.rejection_reasons:
        return "geometry_regression"
    return "reward_too_low"


def _poi_drop_reason(reason: PoiRejectionReason) -> PoiDropReason:
    if reason == "private_access":
        return "private_or_restricted"
    if reason in {"route_budget_exhausted"}:
        return "search_budget_exhausted"
    if reason == "snap_too_far":
        return "approach_snap_too_far"
    if reason in {"distance_tolerance"}:
        return "maximum_distance_rejected"
    if reason in {
        "backtracking_regression",
        "repetition_regression",
        "geometry_regression",
    }:
        return "route_safety_rejected"
    if reason in {"reward_too_low", "duplicate_category_value"}:
        return "spur_cost_too_high"
    return "lower_utility_candidate"


def _requested_drop_reason(reason: str) -> PoiDropReason:
    if reason == "requested_place_graph_unreachable":
        return "graph_unreachable"
    if reason == "requested_place_search_budget_exhausted":
        return "search_budget_exhausted"
    if reason in {
        "requested_place_user_maximum_rejected",
        "requested_place_server_maximum_rejected",
    }:
        return "maximum_distance_rejected"
    return "lower_utility_candidate"


def _requested_semantic_id(place: RequestedTourPlace) -> str:
    if place.id is not None:
        return place.id
    if place.original_index is not None:
        return f"requested/original/{place.original_index}"
    return (
        f"requested/{place.coordinate.lat:.7f},{place.coordinate.lon:.7f}/{place.name}"
    )


def _force_trade_off(candidate: AutoTourCandidate, reason: str) -> AutoTourCandidate:
    comparison = candidate.control_comparison.model_copy(
        update={
            "eligible": False,
            "rejection_reasons": tuple(
                sorted({*candidate.control_comparison.rejection_reasons, reason})
            ),
        }
    )
    return candidate.model_copy(
        update={
            "control_eligible": False,
            "control_comparison": comparison,
            "warnings": tuple(sorted({*candidate.warnings, reason})),
        }
    )
