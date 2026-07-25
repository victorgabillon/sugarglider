"""Auto Tour semantic-anchor inputs for shared global optimization."""

from sugarglider.planning.auto_tour.approaches import (
    approach_candidates_for_feature,
)
from sugarglider.planning.auto_tour.candidate_models import AutoTourCandidate
from sugarglider.planning.auto_tour.models import (
    AutoTourSearchRequest,
)
from sugarglider.planning.models import AutoTourPlanRequest
from sugarglider.planning.optimization import (
    SemanticOptimizationSource,
    SemanticRoutingAnchor,
    normalized_anchor_progress,
)
from sugarglider.planning.result import PlanCandidate
from sugarglider.pois.index import PoiIndex


def auto_tour_optimization_source(
    *,
    request: AutoTourPlanRequest,
    resolved_request: AutoTourSearchRequest,
    source: AutoTourCandidate,
    evaluated: PlanCandidate,
    poi_index: PoiIndex | None,
) -> SemanticOptimizationSource:
    """Build shared exact/fixed/soft anchors from one finalized Auto Tour."""
    assert source.routed_path is not None
    point_count = len(source.routing_points)
    if point_count == 0:
        raise ValueError(
            "Auto Tour optimization requires at least one semantic routing point"
        )
    exact_coordinates = {
        (anchor.routed_coordinate.lat, anchor.routed_coordinate.lon)
        for anchor in evaluated.traversal.anchors
        if anchor.kind in {"start", "end", "exact_waypoint"}
    }
    exact_coordinates.update(
        (coordinate.lat, coordinate.lon)
        for coordinate in resolved_request.hard_waypoints
    )
    public_reached = {stop.id: stop for stop in evaluated.reached_stops}
    public_approximated = {stop.id: stop for stop in evaluated.approximated_stops}
    requested_by_id = {
        place.id: place
        for place in resolved_request.requested_stops
        if place.id is not None
    }
    internal_by_coordinate: dict[tuple[float, float], str] = {}
    for visit in source.requested_place_visits:
        if (
            visit.deliberately_routed
            and visit.requested_place.id is not None
            and visit.chosen_approach is not None
        ):
            coordinate = visit.chosen_approach.coordinate
            internal_by_coordinate[(coordinate.lat, coordinate.lon)] = (
                visit.requested_place.id
            )
    for stop in source.selected_stops:
        if stop.deliberately_inserted:
            coordinate = stop.chosen_approach.coordinate
            internal_by_coordinate[(coordinate.lat, coordinate.lon)] = (
                stop.semantic_poi.id
            )

    anchors: list[SemanticRoutingAnchor] = []
    exact_indices: list[int] = []
    final_index = point_count - 1
    for index, coordinate in enumerate(source.routing_points):
        route_progress = normalized_anchor_progress(index, point_count)
        key = (coordinate.lat, coordinate.lon)
        if key in exact_coordinates or index in {0, final_index}:
            exact_indices.append(index)
            anchors.append(
                SemanticRoutingAnchor(
                    id=f"exact/{index}",
                    name=coordinate.name or f"Exact anchor {index}",
                    coordinate=coordinate,
                    semantic_coordinate=coordinate,
                    kind="exact",
                    route_progress=route_progress,
                )
            )
            continue
        stop_id = internal_by_coordinate.get(key)
        reached = public_reached.get(stop_id or "")
        approximated = public_approximated.get(stop_id or "")
        public_stop = reached or approximated
        if stop_id is None or public_stop is None:
            anchors.append(
                SemanticRoutingAnchor(
                    id=f"fixed/{index}",
                    name=coordinate.name or f"Routing point {index}",
                    coordinate=coordinate,
                    semantic_coordinate=coordinate,
                    kind="fixed",
                    route_progress=route_progress,
                )
            )
            continue
        requested = requested_by_id.get(stop_id)
        if requested is not None:
            candidates = requested.approach_candidates
            strength = requested.constraint_strength
            maximum = (
                requested.maximum_best_effort_distance_m
                or requested.access_search_radius_m
            )
        else:
            feature = poi_index.get_feature(stop_id) if poi_index is not None else None
            candidates = (
                approach_candidates_for_feature(feature) if feature is not None else ()
            )
            strength = "approach"
            maximum = max(
                (approach.semantic_distance_m for approach in candidates),
                default=25.0,
            )
        current = public_stop.resolved_approach
        candidates = tuple(
            {approach.id: approach for approach in (current, *candidates)}.values()
        )
        if requested is None:
            maximum = max(
                (approach.semantic_distance_m for approach in candidates),
                default=maximum,
            )
        anchors.append(
            SemanticRoutingAnchor(
                id=stop_id,
                name=public_stop.name,
                coordinate=coordinate,
                semantic_coordinate=public_stop.semantic_coordinate,
                kind="soft",
                route_progress=public_stop.route_progress,
                constraint_strength=strength,
                outcome="approximated" if approximated is not None else "reached",
                current_approach=current,
                approach_candidates=candidates,
                maximum_semantic_distance_m=max(25.0, maximum),
            )
        )
    return SemanticOptimizationSource(
        source_candidate_id=evaluated.id,
        route=evaluated.route,
        routed_path=source.routed_path,
        source_anchor_order=tuple(anchors),
        exact_boundary_indices=tuple(exact_indices),
        topology=request.topology,
        profile=request.routing_profile,
        target_distance_m=request.distance_objective.target_m,
        tolerance_m=request.distance_objective.tolerance_m,
        distance_priority=request.distance_objective.priority,
        maximum_distance_m=request.distance_objective.maximum_m,
    )
