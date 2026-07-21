"""Strict POI arrival, approach, and excursion contract tests."""

import pytest

from sugarglider.analysis.projection import LocalMetricProjection
from sugarglider.domain.models import Coordinate, PathDetailSegment
from sugarglider.planning.auto_tour.approaches import (
    choose_route_dependent_approaches,
    resolve_requested_place,
)
from sugarglider.planning.auto_tour.excursions import analyze_poi_excursions
from sugarglider.planning.auto_tour.models import (
    PoiExcursion,
    RequestedTourPlace,
    SelectedPoiStop,
    SemanticPoi,
    poi_excursion_penalty_m,
)
from sugarglider.planning.auto_tour.requested_stops import (
    measure_requested_place_visits,
)
from sugarglider.pois.index import PoiIndex
from sugarglider.pois.models import (
    PoiApproachCandidate,
    PoiFeature,
    PoiIndexDocument,
    PoiIndexMetadata,
)
from sugarglider.routing.backend import RoutedPath
from sugarglider.routing.result import RouteResultFactory

PROJECTION = LocalMetricProjection(48.87)
ORIGIN = PROJECTION.project_position((2.09, 48.87))


def _coordinate(x: float, y: float) -> Coordinate:
    lon, lat = PROJECTION.unproject_position((ORIGIN[0] + x, ORIGIN[1] + y))
    return Coordinate(lat=lat, lon=lon)


def _approach(coordinate: Coordinate, *, tolerance: float = 20) -> PoiApproachCandidate:
    return PoiApproachCandidate(
        id="way/1/approach/00-entrance",
        coordinate=coordinate,
        kind="mapped_entrance",
        source="osm_entrance",
        access="public",
        semantic_distance_m=150,
        arrival_tolerance_m=tolerance,
        osm_type="node",
        osm_id=2,
    )


def test_mapped_entrance_can_be_far_from_semantic_centroid() -> None:
    approach = _approach(_coordinate(500, 0))
    place = RequestedTourPlace(
        name="Large castle",
        coordinate=_coordinate(500, 150),
        approach_candidates=(approach,),
        chosen_approach=approach,
    )
    visits = measure_requested_place_visits(
        route_geometry=tuple(
            (point.lon, point.lat)
            for point in (_coordinate(0, 0), _coordinate(1_000, 0))
        ),
        requested_stops=(place,),
    )

    assert visits[0].decision == "selected"
    assert visits[0].measured_distance_m == pytest.approx(0, abs=0.1)
    assert visits[0].chosen_approach == approach
    assert "selected" not in visits[0].model_dump(mode="json")


def test_arbitrary_nearby_path_outside_strict_arrival_is_dropped() -> None:
    approach = _approach(_coordinate(500, 30), tolerance=20)
    place = RequestedTourPlace(
        name="Castle gate",
        coordinate=_coordinate(500, 150),
        approach_candidates=(approach,),
        chosen_approach=approach,
    )
    visit = measure_requested_place_visits(
        route_geometry=tuple(
            (point.lon, point.lat)
            for point in (_coordinate(0, 0), _coordinate(1_000, 0))
        ),
        requested_stops=(place,),
    )[0]

    assert visit.decision == "dropped"
    assert visit.drop_reason == "lower_utility_candidate"
    assert visit.measured_distance_m == pytest.approx(30, abs=0.1)


@pytest.mark.parametrize(
    ("repeated", "expected"),
    ((0, 0), (200, 0), (400, 300), (600, 800), (1_000, 2_400)),
)
def test_convex_poi_excursion_penalty(repeated: float, expected: float) -> None:
    assert poi_excursion_penalty_m(repeated) == expected


def test_shared_excursion_is_charged_once_for_two_pois() -> None:
    anchor = _coordinate(0, 0)
    excursion = PoiExcursion(
        id="excursion/1",
        entry_anchor=anchor,
        exit_anchor=anchor,
        selected_poi_ids=("node/1", "node/2"),
        outward_distance_m=0,
        returning_backtrack_distance_m=400,
        physical_spur_distance_m=400,
        penalized_physical_spur_distance_m=200,
        penalty_m_equivalent=300,
        through_route=False,
    )

    assert excursion.penalty_m_equivalent == 300
    assert len(excursion.selected_poi_ids) == 2


def test_obsolete_visit_radius_is_rejected_by_private_search_model() -> None:
    with pytest.raises(ValueError, match="visit_radius_m"):
        RequestedTourPlace.model_validate(
            {
                "name": "Obsolete place",
                "coordinate": {"lat": 48.87, "lon": 2.09},
                "visit_radius_m": 200,
            }
        )


def test_imported_exact_name_reuses_indexed_osm_approach() -> None:
    coordinate = _coordinate(0, 0)
    approach = _approach(_coordinate(10, 0))
    feature = PoiFeature(
        id="way/1",
        osm_type="way",
        osm_id=1,
        coordinate=coordinate,
        category="castle",
        group="scenic",
        display_name="Château de Test",
        name_source="name",
        scenic_confidence="primary",
        potability="not_applicable",
        access_status="public",
        approach_candidates=(approach,),
    )
    index = PoiIndex(
        PoiIndexDocument(
            metadata=PoiIndexMetadata(
                source_basename="tiny.osm",
                feature_count=1,
                category_counts={"castle": 1},
                potability_counts={"not_applicable": 1},
                access_counts={"public": 1},
                approach_counts={"mapped_entrance": 1},
                bounding_box=(2.0, 48.0, 3.0, 50.0),
                skipped_invalid_count=0,
            ),
            features=(feature,),
        )
    )
    place = RequestedTourPlace(name="  CHÂTEAU   DE TEST ", coordinate=coordinate)

    resolved = resolve_requested_place(place, index)

    assert resolved.osm_reference == "way/1"
    assert resolved.chosen_approach == approach
    assert resolved.name == place.name


def test_user_override_is_first_and_bounded() -> None:
    place = RequestedTourPlace(
        name="Forest estate",
        coordinate=_coordinate(0, 0),
        approach_override=_coordinate(500, 0),
    )
    resolved = resolve_requested_place(place, None)
    assert resolved.chosen_approach is not None
    assert resolved.chosen_approach.kind == "user_override"

    with pytest.raises(ValueError, match="within 1000 metres"):
        RequestedTourPlace(
            name="Invalid override",
            coordinate=_coordinate(0, 0),
            approach_override=_coordinate(1_100, 0),
        )


def test_route_dependent_choice_can_prefer_the_lower_cost_public_approach() -> None:
    far = _approach(_coordinate(500, 200))
    near = far.model_copy(
        update={
            "id": "way/1/approach/01-gate",
            "coordinate": _coordinate(500, 5),
            "kind": "mapped_gate",
        }
    )
    place = RequestedTourPlace(
        name="Estate",
        coordinate=_coordinate(500, 100),
        approach_candidates=(far, near),
        chosen_approach=far,
    )

    (selected,) = choose_route_dependent_approaches(
        (place,),
        tuple(
            (point.lon, point.lat)
            for point in (_coordinate(0, 0), _coordinate(1_000, 0))
        ),
    )

    assert selected.chosen_approach == near


@pytest.mark.parametrize(
    ("snap_distance_m", "decision", "drop_reason"),
    (
        (20.0, "selected", None),
        (150.0, "dropped", "approach_snap_too_far"),
    ),
)
def test_imported_strict_graph_snap_is_bounded_to_25_metres(
    snap_distance_m: float,
    decision: str,
    drop_reason: str | None,
) -> None:
    target = _coordinate(500, 0)
    place = resolve_requested_place(
        RequestedTourPlace(name="Imported coordinate", coordinate=target), None
    )
    snapped_target = _coordinate(500, snap_distance_m)

    visit = measure_requested_place_visits(
        route_geometry=tuple(
            (point.lon, point.lat)
            for point in (_coordinate(0, 0), target, _coordinate(1_000, 0))
        ),
        requested_stops=(place,),
        deliberately_routed_indices=frozenset({0}),
        routing_points=(_coordinate(0, 0), target, _coordinate(1_000, 0)),
        snapped_routing_points=tuple(
            (point.lon, point.lat)
            for point in (_coordinate(0, 0), snapped_target, _coordinate(1_000, 0))
        ),
    )[0]

    assert visit.decision == decision
    assert visit.drop_reason == drop_reason
    assert visit.graph_snap_distance_m == pytest.approx(snap_distance_m, abs=0.1)


def test_exact_shared_spur_attribution_uses_returning_edges_once() -> None:
    points = tuple(
        (point.lon, point.lat)
        for point in (
            _coordinate(0, 0),
            _coordinate(100, 0),
            _coordinate(200, 0),
            _coordinate(100, 0),
            _coordinate(0, 0),
        )
    )
    route = RouteResultFactory().create(
        name="Shared spur",
        input_point_count=3,
        path=RoutedPath(
            distance_m=400,
            duration_ms=1,
            ascend_m=None,
            descend_m=None,
            geometry=points,
            snapped_points=(points[0], points[2], points[-1]),
            details={
                "edge_id": tuple(
                    PathDetailSegment(
                        from_index=index,
                        to_index=index + 1,
                        value=edge_id,
                    )
                    for index, edge_id in enumerate((1, 2, 2, 1))
                )
            },
        ),
    )
    approach = PoiApproachCandidate(
        id="node/1/approach/00-exact",
        coordinate=_coordinate(200, 0),
        kind="viewpoint_location",
        source="osm_feature",
        access="public",
        semantic_distance_m=0,
        arrival_tolerance_m=20,
        osm_type="node",
        osm_id=1,
    )
    selected = tuple(
        SelectedPoiStop(
            semantic_poi=SemanticPoi(
                id=f"node/{poi_id}",
                name=f"Stop {poi_id}",
                coordinate=approach.coordinate,
                category="viewpoint",
                origin="discovered_scenic",
            ),
            chosen_approach=approach,
            route_progress_share=0.5,
            measured_route_to_approach_m=0,
            selection_reason="shared_excursion",
            deliberately_inserted=True,
        )
        for poi_id in (1, 2)
    )

    analysis = analyze_poi_excursions(
        route, selected, free_physical_spur_allowance_m=200
    )

    assert len(analysis.excursions) == 1
    assert analysis.excursions[0].selected_poi_ids == ("node/1", "node/2")
    assert analysis.excursions[0].physical_spur_distance_m == pytest.approx(400)
    assert analysis.excursions[0].penalty_m_equivalent == pytest.approx(300)
    assert analysis.attributed_immediate_backtracking_m == pytest.approx(200)


def test_short_dead_end_excursion_is_selected_inside_free_allowance() -> None:
    points = tuple(
        (point.lon, point.lat)
        for point in (_coordinate(0, 0), _coordinate(100, 0), _coordinate(0, 0))
    )
    route = RouteResultFactory().create(
        name="Short dead end",
        input_point_count=3,
        path=RoutedPath(
            distance_m=200,
            duration_ms=1,
            ascend_m=None,
            descend_m=None,
            geometry=points,
            snapped_points=points,
            details={
                "edge_id": (
                    PathDetailSegment(from_index=0, to_index=1, value=1),
                    PathDetailSegment(from_index=1, to_index=2, value=1),
                )
            },
        ),
    )
    approach = PoiApproachCandidate(
        id="node/9/approach/00-exact",
        coordinate=_coordinate(100, 0),
        kind="viewpoint_location",
        source="osm_feature",
        access="public",
        semantic_distance_m=0,
        arrival_tolerance_m=20,
        osm_type="node",
        osm_id=9,
    )
    stop = SelectedPoiStop(
        semantic_poi=SemanticPoi(
            id="node/9",
            name="Short dead-end viewpoint",
            coordinate=approach.coordinate,
            category="viewpoint",
            origin="discovered_scenic",
        ),
        chosen_approach=approach,
        route_progress_share=0.5,
        measured_route_to_approach_m=0,
        selection_reason="low_cost_insertion",
        deliberately_inserted=True,
    )

    analysis = analyze_poi_excursions(
        route, (stop,), free_physical_spur_allowance_m=200
    )

    assert len(analysis.excursions) == 1
    assert analysis.excursions[0].selected_poi_ids == ("node/9",)
    assert analysis.excursions[0].physical_spur_distance_m == pytest.approx(200)
    assert analysis.excursions[0].penalized_physical_spur_distance_m == 0
    assert analysis.excursions[0].penalty_m_equivalent == 0
    assert analysis.excursions[0].warnings == ()


def test_unknown_edge_inside_spur_is_unverified_and_gets_no_allowance() -> None:
    route_points = tuple(_coordinate(x, 0) for x in (0, 100, 200, 300, 200, 100, 0))
    geometry = tuple((point.lon, point.lat) for point in route_points)
    edge_ids: tuple[int | str, ...] = (1, "unknown", 3, 3, "unknown", 1)
    route = RouteResultFactory().create(
        name="Partially unknown spur",
        input_point_count=3,
        path=RoutedPath(
            distance_m=600,
            duration_ms=1,
            ascend_m=None,
            descend_m=None,
            geometry=geometry,
            snapped_points=(geometry[0], geometry[3], geometry[-1]),
            details={
                "edge_id": tuple(
                    PathDetailSegment(
                        from_index=index,
                        to_index=index + 1,
                        value=edge_id,
                    )
                    for index, edge_id in enumerate(edge_ids)
                )
            },
        ),
    )
    approach = PoiApproachCandidate(
        id="node/20/approach/exact",
        coordinate=route_points[3],
        kind="viewpoint_location",
        source="osm_feature",
        access="public",
        semantic_distance_m=0,
        arrival_tolerance_m=20,
        osm_type="node",
        osm_id=20,
    )
    stop = SelectedPoiStop(
        semantic_poi=SemanticPoi(
            id="node/20",
            name="Unknown-edge stop",
            coordinate=approach.coordinate,
            category="viewpoint",
            origin="discovered_scenic",
        ),
        chosen_approach=approach,
        route_progress_share=0.5,
        measured_route_to_approach_m=0,
        selection_reason="low_cost_insertion",
        deliberately_inserted=True,
    )

    analysis = analyze_poi_excursions(
        route, (stop,), free_physical_spur_allowance_m=200
    )

    (excursion,) = analysis.excursions
    assert not excursion.verified
    assert excursion.free_physical_spur_allowance_m == 0
    assert excursion.physical_spur_distance_m == pytest.approx(
        excursion.outward_distance_m + excursion.returning_backtrack_distance_m
    )
    assert "poi_excursion_unverified" in excursion.warnings


def test_spur_at_stack_depth_is_unverified_without_duplicate_allowance() -> None:
    outward = tuple(_coordinate(index * 10, 0) for index in range(66))
    route_points = (*outward, *reversed(outward[:-1]))
    geometry = tuple((point.lon, point.lat) for point in route_points)
    edge_ids = (*range(65), *reversed(range(65)))
    route = RouteResultFactory().create(
        name="Long bounded-stack spur",
        input_point_count=3,
        path=RoutedPath(
            distance_m=1_300,
            duration_ms=1,
            ascend_m=None,
            descend_m=None,
            geometry=geometry,
            snapped_points=(geometry[0], geometry[65], geometry[-1]),
            details={
                "edge_id": tuple(
                    PathDetailSegment(
                        from_index=index, to_index=index + 1, value=edge_id
                    )
                    for index, edge_id in enumerate(edge_ids)
                )
            },
        ),
    )
    approach = PoiApproachCandidate(
        id="node/30/approach/exact",
        coordinate=outward[-1],
        kind="viewpoint_location",
        source="osm_feature",
        access="public",
        semantic_distance_m=0,
        arrival_tolerance_m=20,
        osm_type="node",
        osm_id=30,
    )
    stop = SelectedPoiStop(
        semantic_poi=SemanticPoi(
            id="node/30",
            name="Long-spur stop",
            coordinate=approach.coordinate,
            category="viewpoint",
            origin="discovered_scenic",
        ),
        chosen_approach=approach,
        route_progress_share=0.5,
        measured_route_to_approach_m=0,
        selection_reason="low_cost_insertion",
        deliberately_inserted=True,
    )

    analysis = analyze_poi_excursions(
        route, (stop,), free_physical_spur_allowance_m=200
    )

    assert len(analysis.excursions) == 1
    assert not analysis.excursions[0].verified
    assert analysis.excursions[0].free_physical_spur_allowance_m == 0
