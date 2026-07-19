"""Bounded deterministic Auto Tour service scenarios with a fake backend."""

from collections import Counter

import pytest

from sugarglider.analysis.projection import LocalMetricProjection
from sugarglider.analysis.route import RouteAnalyzer, haversine_distance_m
from sugarglider.domain.models import Coordinate, PathDetailSegment
from sugarglider.pois.index import PoiIndex
from sugarglider.pois.models import PoiFeature, PoiIndexDocument
from sugarglider.routing.backend import (
    IsochronePolygon,
    IsochroneResult,
    RoutedPath,
)
from sugarglider.routing.errors import RoutingPointError, RoutingUpstreamError
from sugarglider.routing.result import RouteResultFactory
from sugarglider.tours.models import AutoTourRequest, RequestedTourPlace
from sugarglider.tours.poi_selection import TourPoiSettings
from sugarglider.tours.service import (
    ALTERNATIVE_LEG_REQUEST_BUDGET,
    LOCAL_REPAIR_ROUTE_EVALUATION_BUDGET,
    POI_BEAM_WIDTH,
    POI_ROUTE_EVALUATION_BUDGET,
    ROUND_TRIP_CONTROL_REQUEST_BUDGET,
    SKELETON_ROUTE_REQUEST_BUDGET,
    AutoTourMaximumBelowDirectLowerBoundError,
    AutoTourService,
    AutoTourSettings,
)

START = Coordinate(lat=48.87, lon=2.09, name="Station")
PROJECTION = LocalMetricProjection(START.lat)
ORIGIN = PROJECTION.project_position((START.lon, START.lat))


def _coordinate(x: float, y: float) -> Coordinate:
    lon, lat = PROJECTION.unproject_position((ORIGIN[0] + x, ORIGIN[1] + y))
    return Coordinate(lat=lat, lon=lon)


class _Backend:
    def __init__(self, *, fail_isochrone: bool = False) -> None:
        self.fail_isochrone = fail_isochrone
        self.isochrone_calls = 0
        self.route_calls = 0
        self.round_trip_calls = 0

    async def isochrone(
        self,
        start: Coordinate,
        profile: str,
        *,
        distance_limit_m: float,
        buckets: int = 1,
        reverse_flow: bool = False,
    ) -> IsochroneResult:
        self.isochrone_calls += 1
        if self.fail_isochrone:
            raise RoutingUpstreamError("synthetic isochrone failure")
        assert profile == "hike"
        assert distance_limit_m == 5_000
        assert buckets == 1
        assert not reverse_flow
        corners = tuple(
            (coordinate.lon, coordinate.lat)
            for coordinate in (
                _coordinate(-10_000, -10_000),
                _coordinate(10_000, -10_000),
                _coordinate(10_000, 10_000),
                _coordinate(-10_000, 10_000),
                _coordinate(-10_000, -10_000),
            )
        )
        return IsochroneResult((IsochronePolygon(corners),))

    async def route(
        self,
        points: tuple[Coordinate, ...],
        profile: str = "hike",
        *,
        pass_through: bool = False,
    ) -> RoutedPath:
        self.route_calls += 1
        assert profile == "hike"
        assert pass_through
        geometry = tuple((point.lon, point.lat) for point in points)
        distance = sum(
            haversine_distance_m(left, right)
            for left, right in zip(geometry, geometry[1:], strict=False)
        )
        return _path(geometry, distance, snapped=geometry)

    async def round_trip(
        self,
        start: Coordinate,
        distance_m: float,
        seed: int,
        profile: str = "hike",
        *,
        heading_degrees: float | None = None,
    ) -> RoutedPath:
        self.round_trip_calls += 1
        assert profile == "hike"
        assert heading_degrees is not None
        size = distance_m / 4
        # Alternate broad rotation while retaining deterministic heading influence.
        east = _coordinate(size, heading_degrees)
        north_east = _coordinate(size, size + heading_degrees)
        north = _coordinate(0, size)
        points = (
            (start.lon, start.lat),
            (east.lon, east.lat),
            (north_east.lon, north_east.lat),
            (north.lon, north.lat),
            (start.lon, start.lat),
        )
        return _path(points, distance_m, snapped=points)

    async def alternative_routes(
        self,
        start: Coordinate,
        end: Coordinate,
        profile: str = "hike",
        *,
        max_paths: int = 3,
        max_weight_factor: float = 1.6,
        max_share_factor: float = 0.5,
    ) -> tuple[RoutedPath, ...]:
        geometry = ((start.lon, start.lat), (end.lon, end.lat))
        return (_path(geometry, haversine_distance_m(*geometry), snapped=geometry),)


class _LegOnlyBackend(_Backend):
    def __init__(self) -> None:
        super().__init__(fail_isochrone=True)
        self.point_counts: list[int] = []

    async def route(
        self,
        points: tuple[Coordinate, ...],
        profile: str = "hike",
        *,
        pass_through: bool = False,
    ) -> RoutedPath:
        self.point_counts.append(len(points))
        if len(points) > 2:
            raise RoutingPointError("synthetic multi-point traversal cap")
        return await super().route(points, profile, pass_through=pass_through)


class _CorridorBackend(_Backend):
    def __init__(self, pivot: Coordinate, continuation: Coordinate) -> None:
        super().__init__(fail_isochrone=True)
        self.pivot = pivot
        self.continuation = continuation

    async def route(
        self,
        points: tuple[Coordinate, ...],
        profile: str = "hike",
        *,
        pass_through: bool = False,
    ) -> RoutedPath:
        self.route_calls += 1
        assert profile == "hike" and pass_through
        has_pivot = self.pivot in points
        has_continuation = self.continuation in points
        geometry: list[tuple[float, float]] = [(points[0].lon, points[0].lat)]
        for index, point in enumerate(points[1:], start=1):
            position = (point.lon, point.lat)
            if point == self.pivot and has_pivot and not has_continuation:
                previous = (points[index - 1].lon, points[index - 1].lat)
                geometry.extend((position, previous))
            else:
                geometry.append(position)
        distance = sum(
            haversine_distance_m(left, right)
            for left, right in zip(geometry, geometry[1:], strict=False)
        )
        path = _path(
            tuple(geometry),
            distance,
            snapped=tuple((point.lon, point.lat) for point in points),
        )
        if not (has_pivot and not has_continuation):
            return path
        edge_ids = list(path.details["edge_id"])
        pivot_position = (self.pivot.lon, self.pivot.lat)
        pivot_index = geometry.index(pivot_position)
        edge_ids[pivot_index] = edge_ids[pivot_index - 1].model_copy(
            update={"from_index": pivot_index, "to_index": pivot_index + 1}
        )
        return RoutedPath(
            distance_m=path.distance_m,
            duration_ms=path.duration_ms,
            ascend_m=path.ascend_m,
            descend_m=path.descend_m,
            geometry=path.geometry,
            snapped_points=path.snapped_points,
            details={**path.details, "edge_id": tuple(edge_ids)},
        )


class _MissedRequestedHookBackend(_Backend):
    def __init__(
        self,
        requested: Coordinate,
        snapped_hook: Coordinate,
    ) -> None:
        super().__init__(fail_isochrone=True)
        self.requested = requested
        self.snapped_hook = snapped_hook

    async def route(
        self,
        points: tuple[Coordinate, ...],
        profile: str = "hike",
        *,
        pass_through: bool = False,
    ) -> RoutedPath:
        self.route_calls += 1
        assert profile == "hike" and pass_through
        if self.requested not in points:
            return await super().route(points, profile, pass_through=pass_through)
        requested_index = points.index(self.requested)
        previous = points[requested_index - 1]
        geometry = (
            *((point.lon, point.lat) for point in points[:requested_index]),
            (self.snapped_hook.lon, self.snapped_hook.lat),
            (previous.lon, previous.lat),
            *((point.lon, point.lat) for point in points[requested_index + 1 :]),
        )
        snapped = tuple(
            (self.snapped_hook.lon, self.snapped_hook.lat)
            if point == self.requested
            else (point.lon, point.lat)
            for point in points
        )
        distance = sum(
            haversine_distance_m(left, right)
            for left, right in zip(geometry, geometry[1:], strict=False)
        )
        path = _path(geometry, distance, snapped=snapped)
        edge_ids = list(path.details["edge_id"])
        return_index = requested_index
        edge_ids[return_index] = edge_ids[return_index - 1].model_copy(
            update={"from_index": return_index, "to_index": return_index + 1}
        )
        return RoutedPath(
            distance_m=path.distance_m,
            duration_ms=path.duration_ms,
            ascend_m=path.ascend_m,
            descend_m=path.descend_m,
            geometry=path.geometry,
            snapped_points=path.snapped_points,
            details={**path.details, "edge_id": tuple(edge_ids)},
        )


def _path(
    geometry: tuple[tuple[float, float], ...],
    distance_m: float,
    *,
    snapped: tuple[tuple[float, float], ...],
) -> RoutedPath:
    details: dict[str, tuple[PathDetailSegment, ...]] = {}
    edge_ids: list[PathDetailSegment] = []
    surfaces: list[PathDetailSegment] = []
    roads: list[PathDetailSegment] = []
    for index, (left, right) in enumerate(zip(geometry, geometry[1:], strict=False)):
        stable = int(
            abs(
                round(left[0] * 1_000_000) * 31
                + round(left[1] * 1_000_000) * 17
                + round(right[0] * 1_000_000) * 13
                + round(right[1] * 1_000_000) * 7
            )
        )
        edge_ids.append(
            PathDetailSegment(from_index=index, to_index=index + 1, value=stable)
        )
        surfaces.append(
            PathDetailSegment(from_index=index, to_index=index + 1, value="GROUND")
        )
        roads.append(
            PathDetailSegment(from_index=index, to_index=index + 1, value="PATH")
        )
    details["edge_id"] = tuple(edge_ids)
    details["surface"] = tuple(surfaces)
    details["road_class"] = tuple(roads)
    return RoutedPath(
        distance_m=distance_m,
        duration_ms=max(1, round(distance_m * 700)),
        ascend_m=None,
        descend_m=None,
        geometry=geometry,
        snapped_points=snapped,
        details=details,
    )


def _feature(
    osm_id: int,
    *,
    coordinate: Coordinate,
    category: str,
    potability: str = "not_applicable",
) -> PoiFeature:
    hydration = category == "drinking_water"
    return PoiFeature.model_validate(
        {
            "id": f"node/{osm_id}",
            "osm_type": "node",
            "osm_id": osm_id,
            "coordinate": coordinate,
            "category": category,
            "group": "hydration" if hydration else "scenic",
            "display_name": "Water" if hydration else "Viewpoint",
            "name_source": "name",
            "scenic_confidence": "none" if hydration else "primary",
            "potability": potability,
            "access_status": "public",
        }
    )


def _poi_index(extra: tuple[PoiFeature, ...] = ()) -> PoiIndex:
    features = tuple(
        sorted(
            (
                _feature(1, coordinate=_coordinate(300, 0), category="viewpoint"),
                _feature(
                    2,
                    coordinate=_coordinate(0, 100),
                    category="drinking_water",
                    potability="verified",
                ),
                *extra,
            ),
            key=lambda feature: feature.id,
        )
    )

    def counts(field: str) -> dict[str, int]:
        return dict(
            sorted(
                Counter(str(getattr(feature, field)) for feature in features).items()
            )
        )

    return PoiIndex(
        PoiIndexDocument.model_validate(
            {
                "metadata": {
                    "source_basename": "synthetic.osm.pbf",
                    "feature_count": len(features),
                    "category_counts": counts("category"),
                    "potability_counts": counts("potability"),
                    "access_counts": counts("access_status"),
                    "bounding_box": [1.0, 47.0, 3.0, 50.0],
                    "skipped_invalid_count": 0,
                },
                "features": features,
            }
        )
    )


def _settings(**updates: object) -> AutoTourSettings:
    values: dict[str, object] = {
        "round_trip_control_budget": 2,
        "skeleton_route_budget": 4,
        "retained_skeleton_limit": 3,
        "max_inserted_pois": 2,
        "poi_beam_width": 3,
        "poi_route_evaluation_budget": 8,
        "local_repair_route_evaluation_budget": 0,
        "alternative_leg_request_budget": 0,
        "poi": TourPoiSettings(),
    }
    values.update(updates)
    return AutoTourSettings(**values)  # type: ignore[arg-type]


def _service(backend: _Backend, *, poi_index: PoiIndex | None) -> AutoTourService:
    return AutoTourService(
        backend,
        RouteResultFactory(RouteAnalyzer()),
        poi_index=poi_index,
        settings=_settings(),
    )


def test_named_default_budgets_are_exact_and_bounded() -> None:
    settings = AutoTourSettings()
    assert settings.round_trip_control_budget == ROUND_TRIP_CONTROL_REQUEST_BUDGET == 8
    assert settings.skeleton_route_budget == SKELETON_ROUTE_REQUEST_BUDGET == 24
    assert settings.poi_beam_width == POI_BEAM_WIDTH == 6
    assert settings.poi_route_evaluation_budget == POI_ROUTE_EVALUATION_BUDGET == 24
    assert (
        settings.local_repair_route_evaluation_budget
        == LOCAL_REPAIR_ROUTE_EVALUATION_BUDGET
        == 12
    )
    assert (
        settings.alternative_leg_request_budget == ALTERNATIVE_LEG_REQUEST_BUDGET == 24
    )
    assert settings.requested_place_route_evaluation_budget == 60
    assert settings.total_route_request_budget == 152


@pytest.mark.asyncio
async def test_missing_poi_index_returns_deterministic_control() -> None:
    backend = _Backend()
    request = AutoTourRequest(start=START, target_distance_m=10_000, seed=42)
    first = await _service(backend, poi_index=None).generate(request)
    second = await _service(_Backend(), poi_index=None).generate(request)
    assert first.control.signature == second.control.signature
    assert first.candidates[0].signature == second.candidates[0].signature
    assert first.candidates[0].poi_visits == ()
    assert first.search.isochrone_request_count == 1
    assert first.search.skeleton_route_request_count <= 4
    assert first.search.round_trip_control_request_count <= 2
    assert (
        first.search.total_route_request_count
        <= first.search.total_route_request_budget
    )
    assert "auto_tour_poi_index_unavailable" in first.search.warnings


@pytest.mark.asyncio
async def test_isochrone_failure_falls_back_to_round_trip_controls() -> None:
    backend = _Backend(fail_isochrone=True)
    result = await _service(backend, poi_index=None).generate(
        AutoTourRequest(start=START, target_distance_m=10_000)
    )
    assert result.control.skeleton_method == "graphhopper_round_trip"
    assert result.search.skeleton_route_request_count == 2
    assert result.search.sampled_fallback_skeleton_count == 2
    assert result.search.round_trip_control_request_count == 2
    assert len(result.candidates) == 3
    assert "auto_tour_isochrone_unavailable" in result.search.warnings


@pytest.mark.asyncio
async def test_fallback_returns_three_controls_and_deliberately_routes_castle() -> None:
    castle = _feature(
        3,
        coordinate=_coordinate(1_250, 300),
        category="castle",
    ).model_copy(update={"display_name": "Preferred castle"})
    result = await _service(
        _Backend(fail_isochrone=True), poi_index=_poi_index((castle,))
    ).generate(
        AutoTourRequest(
            start=START,
            target_distance_m=10_000,
            candidate_count=3,
            preferred_poi_ids=(castle.id,),
        )
    )
    assert len(result.candidates) == 3
    assert result.search.sampled_fallback_skeleton_count > 0
    assert result.search.poi_route_evaluation_count > 0
    assert any(
        visit.poi.id == castle.id and visit.inserted
        for candidate in result.candidates
        for visit in candidate.poi_visits
    )
    assert (
        result.search.total_route_request_count
        <= result.search.total_route_request_budget
    )


@pytest.mark.asyncio
async def test_requested_place_outside_poi_corridor_drives_fallback_route() -> None:
    requested = RequestedTourPlace(
        name="Imported estate",
        coordinate=_coordinate(1_250, 800),
        visit_radius_m=100,
        importance="must_visit",
        original_index=1,
    )
    result = await _service(_Backend(fail_isochrone=True), poi_index=None).generate(
        AutoTourRequest(
            start=START,
            target_distance_m=10_000,
            requested_places=(requested,),
        )
    )
    recommended = result.candidates[0]
    assert recommended.satisfied_must_visit_count == 1
    assert recommended.requested_place_visits[0].satisfied
    assert recommended.requested_place_visits[0].deliberately_routed
    assert result.search.poi_route_evaluation_count > 0


@pytest.mark.asyncio
async def test_flexible_complete_requested_family_accounts_for_all_22_places() -> None:
    requested = tuple(
        RequestedTourPlace(
            id=f"imported-{index + 1}",
            name=f"Imported place {index + 1}",
            coordinate=_coordinate(400 + index * 55, 250 + (index % 4) * 80),
            visit_radius_m=100,
            importance="must_visit",
            original_index=index + 1,
        )
        for index in range(22)
    )
    service = AutoTourService(
        _Backend(fail_isochrone=True),
        RouteResultFactory(RouteAnalyzer()),
        poi_index=None,
        settings=_settings(max_inserted_pois=0),
    )
    result = await service.generate(
        AutoTourRequest(
            start=START,
            target_distance_m=45_000,
            tolerance_m=2_000,
            candidate_count=3,
            requested_places=requested,
            distance_priority="flexible",
            scenic_preference="off",
            drinking_water_preference="off",
            nature_preference="off",
        )
    )

    recommended = result.candidates[0]
    assert len(recommended.requested_place_visits) == 22
    assert recommended.satisfied_must_visit_count == 22
    assert all(
        visit.deliberately_considered for visit in recommended.requested_place_visits
    )
    assert all(
        visit.deliberately_routed for visit in recommended.requested_place_visits
    )
    assert all(
        visit.failure_reason is None for visit in recommended.requested_place_visits
    )
    assert result.search.requested_place_route_evaluations > 0
    assert result.search.discovered_poi_route_evaluations == 0

    nearby_result = await service.generate(
        AutoTourRequest(
            start=START,
            target_distance_m=46_000,
            tolerance_m=2_000,
            candidate_count=3,
            requested_places=requested,
            distance_priority="flexible",
            scenic_preference="off",
            drinking_water_preference="off",
            nature_preference="off",
        )
    )
    nearby_visits = nearby_result.candidates[0].requested_place_visits
    assert len(nearby_visits) == 22
    assert all(visit.deliberately_considered for visit in nearby_visits)


@pytest.mark.asyncio
async def test_requested_family_composes_legs_after_multi_point_failure() -> None:
    backend = _LegOnlyBackend()
    requested = tuple(
        RequestedTourPlace(
            name=f"Requested {index + 1}",
            coordinate=_coordinate(500 + index * 100, 250),
            importance="must_visit",
            original_index=index + 1,
        )
        for index in range(4)
    )
    result = await _service(backend, poi_index=None).generate(
        AutoTourRequest(
            start=START,
            target_distance_m=10_000,
            requested_places=requested,
            scenic_preference="off",
            drinking_water_preference="off",
            nature_preference="off",
        )
    )

    assert result.candidates[0].satisfied_must_visit_count == 4
    assert any(count > 2 for count in backend.point_counts)
    assert sum(count == 2 for count in backend.point_counts) >= 5


@pytest.mark.asyncio
async def test_distance_ceiling_keeps_maximum_requested_subset_with_reasons() -> None:
    requested = tuple(
        RequestedTourPlace(
            name=f"Far requested {index + 1}",
            coordinate=_coordinate(6_000 + index * 1_000, 0),
            importance="must_visit",
            original_index=index + 1,
        )
        for index in range(3)
    )
    result = await _service(_Backend(fail_isochrone=True), poi_index=None).generate(
        AutoTourRequest(
            start=START,
            target_distance_m=10_000,
            maximum_distance_m=15_000,
            requested_places=requested,
            scenic_preference="off",
            drinking_water_preference="off",
            nature_preference="off",
        )
    )

    recommended = result.candidates[0]
    assert 0 < recommended.satisfied_must_visit_count < 3
    assert recommended.route.summary.distance_m <= recommended.maximum_distance_m
    assert result.search.complete_set_candidate_distance_m is not None
    assert (
        result.search.complete_set_candidate_distance_m
        > result.search.maximum_distance_m
    )
    assert all(
        visit.failure_reason == "requested_place_user_maximum_rejected"
        for visit in recommended.requested_place_visits
        if not visit.satisfied
    )


@pytest.mark.asyncio
async def test_missed_soft_requested_hook_is_removed_inside_repair_budget() -> None:
    reachable = RequestedTourPlace(
        name="Reachable estate",
        coordinate=_coordinate(1_000, 300),
        visit_radius_m=100,
        importance="must_visit",
        original_index=1,
    )
    missed = RequestedTourPlace(
        name="Soft coordinate beyond the path",
        coordinate=_coordinate(1_500, 300),
        visit_radius_m=100,
        importance="must_visit",
        original_index=2,
    )
    backend = _MissedRequestedHookBackend(
        missed.coordinate,
        _coordinate(1_500, 700),
    )
    service = AutoTourService(
        backend,
        RouteResultFactory(RouteAnalyzer()),
        poi_index=None,
        settings=_settings(
            poi_route_evaluation_budget=4,
            local_repair_route_evaluation_budget=2,
        ),
    )
    result = await service.generate(
        AutoTourRequest(
            start=START,
            target_distance_m=10_000,
            requested_places=(reachable, missed),
        )
    )
    recommended = result.candidates[0]
    assert result.search.local_repair_evaluation_count > 0
    assert recommended.construction == "local_repair"
    assert recommended.route.analysis.immediate_backtrack.distance_m == 0
    assert recommended.satisfied_must_visit_count == 1
    assert recommended.requested_place_visits[0].deliberately_routed
    assert not recommended.requested_place_visits[1].deliberately_routed
    assert reachable.coordinate in recommended.routing_points
    assert missed.coordinate not in recommended.routing_points


@pytest.mark.asyncio
async def test_corridor_continuation_repairs_singleton_out_and_back() -> None:
    pivot_coordinate = _coordinate(1_000, 300)
    continuation_coordinate = _coordinate(1_600, 300)
    pivot = _feature(10, coordinate=pivot_coordinate, category="castle").model_copy(
        update={"display_name": "River castle"}
    )
    continuation = _feature(
        11, coordinate=continuation_coordinate, category="viewpoint"
    ).model_copy(update={"display_name": "River continuation"})
    backend = _CorridorBackend(pivot_coordinate, continuation_coordinate)
    service = AutoTourService(
        backend,
        RouteResultFactory(RouteAnalyzer()),
        poi_index=_poi_index((pivot, continuation)),
        settings=_settings(
            max_inserted_pois=1,
            poi_route_evaluation_budget=6,
            local_repair_route_evaluation_budget=4,
        ),
    )
    result = await service.generate(
        AutoTourRequest(
            start=START,
            target_distance_m=10_000,
            preferred_poi_ids=(pivot.id,),
        )
    )
    repaired = tuple(
        candidate
        for candidate in result.candidates
        if candidate.repair is not None
        and candidate.repair.reason == "corridor_continuation"
    )
    assert result.search.corridor_repair_evaluation_count > 0
    assert repaired
    assert repaired[0].repair is not None
    assert repaired[0].repair.immediate_backtracking_removed_m > 0
    assert repaired[0].route.analysis.immediate_backtrack.distance_m == 0
    assert all(
        visit.actual_distance_delta_m is None
        for visit in repaired[0].poi_visits
        if visit.inserted
    )


@pytest.mark.asyncio
async def test_soft_pois_can_win_without_quality_regression() -> None:
    backend = _Backend()
    result = await _service(backend, poi_index=_poi_index()).generate(
        AutoTourRequest(start=START, target_distance_m=10_000, tolerance_m=2_000)
    )
    recommended = result.candidates[0]
    assert recommended.control_eligible
    assert recommended.route.analysis.immediate_backtrack.share <= (
        result.control.route.analysis.immediate_backtrack.share + 1e-12
    )
    assert recommended.route.analysis.repetition.repeated_distance.share <= (
        result.control.route.analysis.repetition.repeated_distance.share + 1e-12
    )
    assert recommended.inserted_poi_reward >= 0
    assert result.search.poi_route_evaluation_count <= 8
    assert sum(visit.inserted for visit in recommended.poi_visits) <= 2
    if any(
        visit.poi.category == "drinking_water" and visit.poi.potability == "verified"
        for visit in result.control.poi_visits
    ):
        assert "auto_tour_no_safe_water_insertion" not in result.search.warnings


@pytest.mark.asyncio
async def test_explicit_direction_preference_is_respected_after_route_analysis() -> (
    None
):
    result = await _service(_Backend(), poi_index=None).generate(
        AutoTourRequest(
            start=START,
            target_distance_m=10_000,
            direction_preference="clockwise",
        )
    )
    assert result.control.direction == "clockwise"
    assert all(candidate.direction == "clockwise" for candidate in result.candidates)


@pytest.mark.asyncio
async def test_open_auto_tour_uses_direct_graph_route_and_never_returns_to_start() -> (
    None
):
    backend = _Backend()
    end = _coordinate(12_000, 2_000)
    request = AutoTourRequest(
        start=START,
        end=end,
        route_topology="point_to_point",
        target_distance_m=8_000,
        scenic_preference="off",
        drinking_water_preference="off",
        nature_preference="off",
        path_selection_mode="shortest",
    )
    result = await AutoTourService(
        backend,
        RouteResultFactory(RouteAnalyzer()),
        settings=AutoTourSettings(
            max_inserted_pois=0,
            poi_route_evaluation_budget=0,
            local_repair_route_evaluation_budget=0,
        ),
    ).generate(request)

    recommended = result.candidates[0]
    assert result.topology == "point_to_point"
    assert result.effective_start == START
    assert result.effective_end == end
    assert backend.isochrone_calls == 0
    assert backend.round_trip_calls == 0
    assert recommended.route.geometry[0] == (START.lon, START.lat)
    assert recommended.route.geometry[-1] == (end.lon, end.lat)
    assert recommended.route.geometry[-1] != recommended.route.geometry[0]
    assert result.control.route.analysis.loop_geometry is None
    assert recommended.route.analysis.loop_geometry is None
    assert recommended.direct_distance_m == recommended.route.summary.distance_m
    assert recommended.detour_ratio == pytest.approx(1.0)
    assert recommended.destination_progress_monotonicity == pytest.approx(1.0)
    assert "target_below_point_to_point_lower_bound" in result.search.warnings


@pytest.mark.asyncio
async def test_flexible_open_route_retains_complete_coverage_above_old_ceiling() -> (
    None
):
    end = _coordinate(12_000, 0)
    requested = tuple(
        RequestedTourPlace(
            id=f"cluster-{index}",
            name=f"Cluster place {index}",
            coordinate=_coordinate(3_000 + index * 2_000, 5_000),
            importance="must_visit",
            original_index=index,
        )
        for index in range(1, 4)
    )
    request = AutoTourRequest(
        start=START,
        end=end,
        route_topology="point_to_point",
        target_distance_m=12_000,
        tolerance_m=2_000,
        candidate_count=3,
        requested_places=requested,
        distance_priority="flexible",
        scenic_preference="off",
        drinking_water_preference="off",
        nature_preference="off",
        path_selection_mode="shortest",
    )
    result = await _service(_Backend(), poi_index=None).generate(request)

    recommended = result.candidates[0]
    old_target_ceiling = 15_000
    assert recommended.satisfied_must_visit_count == 3
    assert recommended.route.summary.distance_m > old_target_ceiling
    assert recommended.maximum_distance_m == 200_000
    assert result.search.full_set_route_attempted
    assert result.search.full_set_route_succeeded
    assert result.search.full_set_safety_eligible is True
    assert result.search.full_set_distance_m is not None
    assert result.control.signature in {
        candidate.signature for candidate in result.candidates
    }
    assert "target_distance_exceeded_for_requested_coverage" in (result.search.warnings)


@pytest.mark.asyncio
async def test_open_user_maximum_prunes_with_specific_reasons() -> None:
    end = _coordinate(12_000, 0)
    requested = tuple(
        RequestedTourPlace(
            name=f"Far place {index}",
            coordinate=_coordinate(3_000 + index * 2_000, 5_000),
            importance="must_visit",
            original_index=index,
        )
        for index in range(1, 4)
    )
    result = await _service(_Backend(), poi_index=None).generate(
        AutoTourRequest(
            start=START,
            end=end,
            route_topology="point_to_point",
            target_distance_m=12_000,
            maximum_distance_m=15_000,
            requested_places=requested,
            scenic_preference="off",
            drinking_water_preference="off",
            nature_preference="off",
        )
    )

    recommended = result.candidates[0]
    assert recommended.route.summary.distance_m <= 15_000
    assert recommended.satisfied_must_visit_count < 3
    assert all(
        visit.failure_reason == "requested_place_user_maximum_rejected"
        for visit in recommended.requested_place_visits
        if not visit.satisfied
    )


@pytest.mark.asyncio
async def test_open_user_maximum_below_direct_route_is_rejected() -> None:
    with pytest.raises(AutoTourMaximumBelowDirectLowerBoundError):
        await _service(_Backend(), poi_index=None).generate(
            AutoTourRequest(
                start=START,
                end=_coordinate(12_000, 0),
                route_topology="point_to_point",
                target_distance_m=12_000,
                maximum_distance_m=10_000,
            )
        )


@pytest.mark.asyncio
async def test_open_flexible_server_maximum_has_specific_rejection_reason() -> None:
    requested = RequestedTourPlace(
        name="Remote requested place",
        coordinate=_coordinate(150_000, 150_000),
        importance="must_visit",
        original_index=1,
    )
    result = await _service(_Backend(), poi_index=None).generate(
        AutoTourRequest(
            start=START,
            end=_coordinate(30_000, 0),
            route_topology="point_to_point",
            target_distance_m=45_000,
            requested_places=(requested,),
            scenic_preference="off",
            drinking_water_preference="off",
            nature_preference="off",
        )
    )

    assert result.search.maximum_distance_m == 200_000
    assert result.search.full_set_safety_eligible is False
    assert (
        result.search.full_set_rejection_reason
        == "requested_place_server_maximum_rejected"
    )
    assert (
        result.candidates[0].requested_place_visits[0].failure_reason
        == "requested_place_server_maximum_rejected"
    )


@pytest.mark.asyncio
async def test_open_balanced_retains_target_derived_maximum() -> None:
    requested = tuple(
        RequestedTourPlace(
            name=f"Balanced place {index}",
            coordinate=_coordinate(3_000 + index * 2_000, 5_000),
            importance="must_visit",
            original_index=index,
        )
        for index in range(1, 4)
    )
    result = await _service(_Backend(), poi_index=None).generate(
        AutoTourRequest(
            start=START,
            end=_coordinate(12_000, 0),
            route_topology="point_to_point",
            target_distance_m=12_000,
            tolerance_m=2_000,
            distance_priority="balanced",
            requested_places=requested,
            scenic_preference="off",
            drinking_water_preference="off",
            nature_preference="off",
        )
    )

    assert result.search.maximum_distance_m == 16_000
    assert result.candidates[0].route.summary.distance_m <= 16_000
    assert result.candidates[0].satisfied_must_visit_count < 3
