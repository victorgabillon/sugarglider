"""Synthetic PR11 ranking scenarios for conservative POI control gates."""

from sugarglider.analysis.loop_geometry import LoopGeometryRouteAnalyzer
from sugarglider.analysis.route import RouteAnalyzer, haversine_distance_m
from sugarglider.domain.models import Coordinate, PathDetailSegment, RouteResult
from sugarglider.planning.auto_tour.approaches import (
    approach_candidates_for_feature,
    resolve_requested_place,
)
from sugarglider.planning.auto_tour.candidate_models import (
    AutoTourCandidate,
)
from sugarglider.planning.auto_tour.models import (
    DiscoveredPoiVisit,
    DistancePriority,
    RequestedTourPlace,
    RequestedTourPlaceVisit,
    TourControlComparison,
)
from sugarglider.planning.auto_tour.ranking import (
    auto_tour_ranking_key,
    compare_with_control,
    control_comparison,
    maximum_auto_tour_distance_m,
    poi_reward,
    score_route,
    soft_distance_penalty,
)
from sugarglider.pois.models import PoiCategory, PoiFeature
from sugarglider.routing.backend import RoutedPath
from sugarglider.routing.result import RouteResultFactory


def test_only_explicit_distance_maximum_is_hard() -> None:
    assert maximum_auto_tour_distance_m(45_000, 2_000, priority="flexible") == float(
        "inf"
    )
    assert maximum_auto_tour_distance_m(45_000, 2_000, priority="balanced") == float(
        "inf"
    )
    assert maximum_auto_tour_distance_m(45_000, 2_000, priority="strict") == float(
        "inf"
    )
    assert (
        maximum_auto_tour_distance_m(
            45_000,
            2_000,
            priority="flexible",
            requested_maximum_distance_m=61_000,
        )
        == 61_000
    )


RING = (
    (2.05, 48.86),
    (2.10, 48.86),
    (2.10, 48.90),
    (2.05, 48.90),
    (2.05, 48.86),
)
REPEATED = (
    (2.05, 48.86),
    (2.10, 48.86),
    (2.10, 48.90),
    (2.10, 48.86),
    (2.05, 48.90),
    (2.05, 48.86),
)


def _route(
    geometry: tuple[tuple[float, float], ...], edge_ids: tuple[int, ...]
) -> RouteResult:
    distance = sum(
        haversine_distance_m(left, right)
        for left, right in zip(geometry, geometry[1:], strict=False)
    )
    segments = tuple(
        PathDetailSegment(from_index=index, to_index=index + 1, value=value)
        for index, value in enumerate(edge_ids)
    )
    path = RoutedPath(
        distance_m=distance,
        duration_ms=round(distance * 700),
        ascend_m=None,
        descend_m=None,
        geometry=geometry,
        snapped_points=geometry,
        details={
            "edge_id": segments,
            "surface": tuple(
                segment.model_copy(update={"value": "GROUND"}) for segment in segments
            ),
            "road_class": tuple(
                segment.model_copy(update={"value": "PATH"}) for segment in segments
            ),
        },
    )
    return RouteResultFactory(
        RouteAnalyzer(loop_geometry_analyzer=LoopGeometryRouteAnalyzer())
    ).create(
        name="Synthetic Auto Tour",
        path=path,
        input_point_count=2,
        routing_profile="hike",
    )


def _feature(osm_id: int, category: str, *, verified: bool = False) -> PoiFeature:
    return PoiFeature.model_validate(
        {
            "id": f"node/{osm_id}",
            "osm_type": "node",
            "osm_id": osm_id,
            "coordinate": {"lat": 48.88, "lon": 2.08},
            "category": category,
            "group": "hydration" if verified else "scenic",
            "display_name": "Water" if verified else "Castle",
            "name_source": "name",
            "scenic_confidence": "none" if verified else "primary",
            "potability": "verified" if verified else "not_applicable",
            "access_status": "public",
        }
    )


def _visits(*features: PoiFeature) -> tuple[DiscoveredPoiVisit, ...]:
    values: list[DiscoveredPoiVisit] = []
    categories: list[PoiCategory] = []
    water_seen = False
    for index, feature in enumerate(features, start=1):
        reward = poi_reward(
            feature,
            prior_categories=tuple(categories),
            verified_water_already_selected=water_seen,
        )
        categories.append(feature.category)
        water_seen = water_seen or feature.potability == "verified"
        approach = approach_candidates_for_feature(feature)[0]
        values.append(
            DiscoveredPoiVisit(
                poi=feature,
                visit_distance_m=0,
                chosen_approach=approach,
                arrival_tolerance_m=approach.arrival_tolerance_m,
                already_on_route=False,
                inserted=True,
                estimated_detour_m=0,
                actual_distance_delta_m=0,
                reward=reward.total,
                reward_breakdown=reward,
                marginal_utility=reward.total,
                route_progress_share=index / (len(features) + 1),
                reason="inserted_close_enough",
            )
        )
    return tuple(values)


def _candidate(
    route: RouteResult,
    signature: str,
    visits: tuple[DiscoveredPoiVisit, ...],
    comparison: TourControlComparison,
    *,
    requested_visits: tuple[RequestedTourPlaceVisit, ...] = (),
    distance_priority: DistancePriority = "flexible",
    target_error_m: float = 0,
    within_tolerance: bool = True,
    distance_penalty: float = 0,
) -> AutoTourCandidate:
    reward = sum(visit.reward for visit in visits)
    start = Coordinate(lat=route.geometry[0][1], lon=route.geometry[0][0])
    return AutoTourCandidate(
        rank=1,
        route=route,
        signature=signature,
        construction="poi_insertion" if visits else "graphhopper_round_trip",
        direction="clockwise",
        skeleton_id=signature,
        skeleton_method="graphhopper_round_trip",
        routing_points=(start,),
        snapped_routing_points=route.snapped_points,
        hard_point_visits=(),
        poi_visits=visits,
        requested_place_visits=requested_visits,
        target_error_m=target_error_m,
        within_tolerance=within_tolerance,
        distance_priority=distance_priority,
        soft_distance_penalty=distance_penalty,
        control_eligible=comparison.eligible,
        control_comparison=comparison,
        total_poi_reward=reward,
        discovered_poi_reward=reward,
        selected_scenic_count=sum(visit.poi.group == "scenic" for visit in visits),
        selected_verified_water_count=sum(
            visit.poi.potability == "verified" for visit in visits
        ),
        selected_must_visit_count=sum(
            visit.selected and visit.requested_place.importance == "must_visit"
            for visit in requested_visits
        ),
        selected_preferred_place_count=sum(
            visit.selected and visit.requested_place.importance == "prefer"
            for visit in requested_visits
        ),
        route_score=score_route(route, route.summary.distance_m),
    )


def test_smooth_control_beats_higher_reward_zigzag() -> None:
    control_route = _route(RING, (1, 2, 3, 4))
    zigzag_route = _route(REPEATED, (1, 2, 2, 5, 6))
    control = _candidate(
        control_route,
        "control",
        (),
        control_comparison(control_route, "control"),
    )
    visits = _visits(
        _feature(1, "castle"), _feature(2, "drinking_water", verified=True)
    )
    comparison = compare_with_control(
        route=zigzag_route,
        within_tolerance=True,
        hard_waypoints_selected=True,
        discovered_poi_reward=sum(visit.reward for visit in visits),
        control=control_route,
        control_within_tolerance=True,
        control_signature="control",
    )
    zigzag = _candidate(zigzag_route, "zigzag", visits, comparison)
    assert not zigzag.control_eligible
    assert min((control, zigzag), key=auto_tour_ranking_key) is control


def test_equal_route_quality_with_castle_and_water_wins() -> None:
    route = _route(RING, (1, 2, 3, 4))
    control = _candidate(route, "control", (), control_comparison(route, "control"))
    visits = _visits(
        _feature(1, "castle"), _feature(2, "drinking_water", verified=True)
    )
    comparison = compare_with_control(
        route=route,
        within_tolerance=True,
        hard_waypoints_selected=True,
        discovered_poi_reward=sum(visit.reward for visit in visits),
        control=route,
        control_within_tolerance=True,
        control_signature="control",
    )
    poi_candidate = _candidate(route, "poi", visits, comparison)
    assert poi_candidate.control_eligible
    assert min((control, poi_candidate), key=auto_tour_ranking_key) is poi_candidate


def _requested_visits(count: int) -> tuple[RequestedTourPlaceVisit, ...]:
    visits: list[RequestedTourPlaceVisit] = []
    for index in range(count):
        place = RequestedTourPlace(
            name=f"Requested {index}",
            coordinate=Coordinate(lat=48.88, lon=2.08 + index / 1_000),
            importance="must_visit",
            original_index=index,
        )
        approach = resolve_requested_place(place, None).chosen_approach
        assert approach is not None
        visits.append(
            RequestedTourPlaceVisit(
                requested_place=place,
                measured_distance_m=0,
                closest_route_distance_m=0,
                chosen_approach=approach,
                arrival_tolerance_m=approach.arrival_tolerance_m,
                route_progress_share=(index + 1) / (count + 1),
                decision="selected",
                deliberately_routed=True,
                graph_snap_distance_m=0,
                selection_reason="requested_must_visit",
            )
        )
    return tuple(visits)


def test_flexible_requested_stops_beat_target_error_but_strict_does_not() -> None:
    route = _route(RING, (1, 2, 3, 4))
    comparison = control_comparison(route, "control")
    close = _candidate(
        route,
        "41-km",
        (),
        comparison,
        target_error_m=0,
        within_tolerance=True,
        distance_penalty=0,
    )
    requested = _candidate(
        route,
        "44-km",
        (),
        comparison,
        requested_visits=_requested_visits(3),
        target_error_m=3_000,
        within_tolerance=False,
        distance_penalty=soft_distance_penalty(
            distance_m=44_000,
            target_distance_m=41_000,
            tolerance_m=2_000,
            priority="flexible",
        ),
    )
    assert min((close, requested), key=auto_tour_ranking_key) is requested

    strict_close = close.model_copy(update={"distance_priority": "strict"})
    strict_requested = requested.model_copy(update={"distance_priority": "strict"})
    assert (
        min((strict_close, strict_requested), key=auto_tour_ranking_key) is strict_close
    )


def test_soft_distance_penalty_is_continuous_at_tolerance_boundary() -> None:
    inside = soft_distance_penalty(
        distance_m=42_999.999,
        target_distance_m=41_000,
        tolerance_m=2_000,
        priority="flexible",
    )
    outside = soft_distance_penalty(
        distance_m=43_000.001,
        target_distance_m=41_000,
        tolerance_m=2_000,
        priority="flexible",
    )
    assert outside - inside < 1e-6
