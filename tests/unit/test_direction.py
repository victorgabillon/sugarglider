"""Central traversal direction and bounded graph-valid reversal."""

from dataclasses import replace
from typing import cast
from xml.etree import ElementTree

import pytest

from sugarglider.analysis.route import haversine_distance_m
from sugarglider.domain.models import Coordinate, RouteResult
from sugarglider.gpx.writer import GPX_NAMESPACE, write_plan_gpx
from sugarglider.planning.direction.analysis import analyze_route_direction
from sugarglider.planning.direction.anchors import sample_shape_anchors
from sugarglider.planning.direction.models import ReversePlanRequest
from sugarglider.planning.direction.service import ReversePlanner
from sugarglider.planning.direction.transform import transform_reverse_request
from sugarglider.planning.direction.traversal import build_plan_traversal
from sugarglider.planning.drafts import CandidateDraft
from sugarglider.planning.models import (
    PLAN_REQUEST_ADAPTER,
    AutoTourPlanRequest,
    WaypointPlanRequest,
)
from sugarglider.planning.result import (
    ApproximatedPlanStop,
    PlanCandidate,
    PlanCandidateDiagnostics,
    PlanScore,
    PlanTraversal,
    PlanTraversalAnchor,
    ReachedPlanStop,
)
from sugarglider.planning.validation import ExactWaypointNotReachedError
from sugarglider.planning.waypoint.service import WaypointPlanner
from sugarglider.pois.models import PoiApproachCandidate
from sugarglider.routing.backend import AutoTourRoutingBackend, RoutedPath
from sugarglider.routing.errors import RoutingError
from sugarglider.routing.result import RouteResultFactory


class _DirectionalBackend:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[Coordinate, ...], str]] = []

    async def route(
        self,
        points: tuple[Coordinate, ...],
        profile: str,
        *,
        pass_through: bool = False,
    ) -> RoutedPath:
        del pass_through
        self.calls.append((points, profile))
        snapped = tuple((point.lon, point.lat) for point in points)
        geometry_values: list[tuple[float, float]] = []
        for left, right in zip(snapped, snapped[1:], strict=False):
            geometry_values.extend(
                (
                    left,
                    (
                        (left[0] + right[0]) / 2,
                        (left[1] + right[1]) / 2
                        + (0.0001 if right[0] >= left[0] else -0.0001),
                    ),
                )
            )
        geometry_values.append(snapped[-1])
        geometry = tuple(geometry_values)
        distance = sum(
            haversine_distance_m(left, right)
            for left, right in zip(geometry, geometry[1:], strict=False)
        )
        return RoutedPath(
            distance_m=max(1.0, distance),
            duration_ms=600_000,
            ascend_m=None,
            descend_m=None,
            geometry=geometry,
            snapped_points=snapped,
            details={},
        )


class _BestEffortBackend(_DirectionalBackend):
    async def route(
        self,
        points: tuple[Coordinate, ...],
        profile: str,
        *,
        pass_through: bool = False,
    ) -> RoutedPath:
        path = await super().route(points, profile, pass_through=pass_through)
        if len(points) != 2 or abs(points[-1].lon - 2.105) > 1e-9:
            return path
        displaced = (points[-1].lon, points[-1].lat + 0.001)
        assert path.snapped_points is not None
        return replace(
            path,
            geometry=(*path.geometry[:-1], displaced),
            snapped_points=(path.snapped_points[0], displaced),
        )


class _MissExactBackend(_DirectionalBackend):
    async def route(
        self,
        points: tuple[Coordinate, ...],
        profile: str,
        *,
        pass_through: bool = False,
    ) -> RoutedPath:
        path = await super().route(points, profile, pass_through=pass_through)
        assert path.snapped_points is not None
        missed = (path.snapped_points[1][0], path.snapped_points[1][1] + 0.01)
        return replace(
            path,
            snapped_points=(
                path.snapped_points[0],
                missed,
                *path.snapped_points[2:],
            ),
        )


class _UnreachableSoftBackend(_DirectionalBackend):
    async def route(
        self,
        points: tuple[Coordinate, ...],
        profile: str,
        *,
        pass_through: bool = False,
    ) -> RoutedPath:
        if abs(points[-1].lon - 2.105) < 1e-9:
            raise RoutingError("soft target is unreachable")
        return await super().route(points, profile, pass_through=pass_through)


def _open_request() -> WaypointPlanRequest:
    request = PLAN_REQUEST_ADAPTER.validate_python(
        {
            "schema_version": 1,
            "kind": "waypoint_route",
            "name": "Directional woodland crossing",
            "topology": "point_to_point",
            "start": {"lat": 48.86, "lon": 2.08, "name": "West"},
            "end": {"lat": 48.87, "lon": 2.13, "name": "East"},
            "routing_profile": "city_bike",
            "candidate_count": 1,
            "seed": 9,
            "distance_objective": {
                "target_m": 5_000,
                "tolerance_m": 3_000,
                "maximum_m": None,
                "priority": "flexible",
            },
            "preferences": {
                "nature": "off",
                "path_selection": "shortest",
                "loop_geometry": "off",
            },
            "waypoints": [
                {
                    "id": "middle-a",
                    "name": "Middle A",
                    "coordinate": {"lat": 48.862, "lon": 2.095},
                    "constraint_strength": "exact",
                },
                {
                    "id": "middle-b",
                    "name": "Middle B",
                    "coordinate": {"lat": 48.868, "lon": 2.115},
                    "constraint_strength": "exact",
                },
            ],
            "waypoint_order": "fixed",
        }
    )
    assert isinstance(request, WaypointPlanRequest)
    return request


def _soft_request() -> WaypointPlanRequest:
    document = _open_request().model_dump(mode="json")
    document["waypoints"] = [
        {
            "id": "soft-viewpoint",
            "name": "Soft viewpoint",
            "coordinate": {"lat": 48.865, "lon": 2.105},
            "constraint_strength": "best_effort",
            "access_search_radius_m": 500,
            "maximum_best_effort_distance_m": 500,
            "approach_override": None,
        }
    ]
    request = PLAN_REQUEST_ADAPTER.validate_python(document)
    assert isinstance(request, WaypointPlanRequest)
    return request


def _loop_request() -> WaypointPlanRequest:
    document = _open_request().model_dump(mode="json")
    document.update(topology="loop", end=None)
    document["waypoints"] = document["waypoints"][:1]
    request = PLAN_REQUEST_ADAPTER.validate_python(document)
    assert isinstance(request, WaypointPlanRequest)
    return request


@pytest.mark.parametrize(
    ("geometry", "expected"),
    (
        (
            (
                (2.0, 48.0),
                (2.0, 48.01),
                (2.01, 48.01),
                (2.01, 48.0),
                (2.0, 48.0),
            ),
            "clockwise",
        ),
        (
            (
                (2.0, 48.0),
                (2.01, 48.0),
                (2.01, 48.01),
                (2.0, 48.01),
                (2.0, 48.0),
            ),
            "counterclockwise",
        ),
        (
            (
                (2.0, 48.0),
                (2.01, 48.01),
                (2.0, 48.01),
                (2.01, 48.0),
                (2.0, 48.0),
            ),
            "complex_loop",
        ),
        (
            (
                (2.0, 48.0),
                (2.01, 48.00001),
                (2.02, 48.0),
                (2.0, 48.0),
            ),
            "complex_loop",
        ),
    ),
)
def test_loop_direction_analysis(
    geometry: tuple[tuple[float, float], ...], expected: str
) -> None:
    assert analyze_route_direction(geometry, "loop") == expected


def test_open_direction_is_geometry_order() -> None:
    assert (
        analyze_route_direction(((2.0, 48.0), (2.1, 48.1)), "point_to_point")
        == "start_to_end"
    )


def test_shape_anchor_sampling_is_bounded_spaced_and_stable() -> None:
    outbound = tuple((2.0 + index * 0.01, 48.0) for index in range(10))
    geometry = (*outbound, *reversed(outbound))
    first = sample_shape_anchors(geometry)
    assert first == sample_shape_anchors(geometry)
    assert 1 <= len(first) <= 8
    assert tuple(anchor.source_progress for anchor in first) == tuple(
        sorted({anchor.source_progress for anchor in first})
    )
    assert all(0.1 < anchor.source_progress < 0.9 for anchor in first)
    assert all(
        haversine_distance_m(
            (left.coordinate.lon, left.coordinate.lat),
            (right.coordinate.lon, right.coordinate.lat),
        )
        >= 150
        for index, left in enumerate(first)
        for right in first[index + 1 :]
    )


def test_traversal_keeps_deliberate_stops_and_uses_approximated_target(
    route_result: RouteResult,
) -> None:
    request = _soft_request()
    routed = Coordinate(lat=48.87, lon=2.1)
    approach = PoiApproachCandidate(
        id="approach",
        coordinate=routed,
        kind="strict_graph_snap",
        source="imported_coordinate",
        access="unknown",
        semantic_distance_m=0,
        arrival_tolerance_m=25,
        provenance="imported_coordinate",
    )
    requested = ReachedPlanStop(
        id="soft-viewpoint",
        name="Requested",
        semantic_coordinate=routed,
        category="requested_stop",
        selection_origin="requested",
        selection_method="already_reached",
        resolved_approach=approach,
        route_progress=0.3,
        route_to_approach_m=0,
    )
    incidental = requested.model_copy(
        update={
            "id": "incidental",
            "name": "Incidental",
            "selection_origin": "discovered",
        }
    )
    deliberate = incidental.model_copy(
        update={
            "id": "deliberate",
            "name": "Deliberate",
            "selection_method": "deliberate_insertion",
            "route_progress": 0.5,
        }
    )
    fallback = Coordinate(lat=48.869, lon=2.11)
    approximated = ApproximatedPlanStop(
        id="approx",
        name="Approximation",
        semantic_coordinate=Coordinate(lat=48.87, lon=2.111),
        category="requested_stop",
        selection_origin="requested",
        resolved_approach=approach.model_copy(update={"coordinate": fallback}),
        route_progress=0.7,
        distance_m=100,
        normal_tolerance_m=25,
        configured_maximum_m=500,
        reason="nearest_routeable_point_used",
    )
    traversal = build_plan_traversal(
        request,
        CandidateDraft(
            route=route_result,
            routing_points=(request.start, request.effective_end),
            topology="point_to_point",
            construction="test",
            search_family="reverse",
            reached_stops=(requested, incidental, deliberate),
            approximated_stops=(approximated,),
        ),
    )
    ids = [anchor.id for anchor in traversal.anchors]
    assert "stop/soft-viewpoint" in ids
    assert "stop/deliberate" in ids
    assert "stop/incidental" not in ids
    approximate_anchor = next(
        anchor for anchor in traversal.anchors if anchor.id == "stop/approx"
    )
    assert approximate_anchor.routed_coordinate == fallback
    assert len(ids) == len(set(ids))


@pytest.mark.asyncio
async def test_open_reverse_reroutes_and_supports_second_reverse() -> None:
    backend = _DirectionalBackend()
    request = _open_request()
    generated = await WaypointPlanner(
        cast(AutoTourRoutingBackend, backend),
        RouteResultFactory(),
        max_evaluations=4,
    ).generate(request)
    source = generated.candidates[0]
    source_calls = len(backend.calls)
    planner = ReversePlanner(
        cast(AutoTourRoutingBackend, backend), RouteResultFactory()
    )
    reversed_response = await planner.reverse(
        ReversePlanRequest(
            schema_version=1,
            source_request=request,
            candidate=source,
        )
    )
    transformed = reversed_response.transformed_request
    assert isinstance(transformed, WaypointPlanRequest)
    assert transformed.start == request.end
    assert transformed.end == request.start
    assert [point.id for point in transformed.waypoints] == ["middle-b", "middle-a"]
    reversed_candidate = reversed_response.result.candidates[0]
    assert reversed_candidate.id != source.id
    assert reversed_candidate.route.geometry != tuple(reversed(source.route.geometry))
    assert backend.calls[source_calls][1] == "city_bike"
    assert (
        reversed_response.result.search_diagnostics.budget.phases["reverse"].used == 1
    )
    assert reversed_response.result.search_diagnostics.cache.backend_call_count == 1
    assert reversed_candidate.diagnostics.details["construction"] == "reversed_route"
    assert reversed_candidate.route.geometry[0] == (
        request.end.lon,
        request.end.lat,
    )
    assert reversed_candidate.route.geometry[-1] == (
        request.start.lon,
        request.start.lat,
    )

    twice = await planner.reverse(
        ReversePlanRequest(
            schema_version=1,
            source_request=transformed,
            candidate=reversed_candidate,
        )
    )
    twice_request = twice.transformed_request
    assert isinstance(twice_request, WaypointPlanRequest)
    assert twice_request.start == request.start
    assert twice_request.end == request.end
    assert [point.id for point in twice_request.waypoints] == [
        "middle-a",
        "middle-b",
    ]

    namespace = {"g": GPX_NAMESPACE}
    gpx = ElementTree.fromstring(write_plan_gpx(reversed_candidate))
    trackpoints = gpx.findall("g:trk/g:trkseg/g:trkpt", namespace)
    assert gpx.findall("g:rte", namespace) == []
    assert len(gpx.findall("g:trk", namespace)) == 1
    assert len(gpx.findall("g:trk/g:trkseg", namespace)) == 1
    assert float(trackpoints[0].attrib["lon"]) == pytest.approx(
        reversed_candidate.route.geometry[0][0], abs=1e-8
    )
    assert float(trackpoints[-1].attrib["lon"]) == pytest.approx(
        reversed_candidate.route.geometry[-1][0], abs=1e-8
    )


@pytest.mark.asyncio
async def test_optimized_waypoints_reverse_actual_traversal_order() -> None:
    backend = _DirectionalBackend()
    request = _open_request().model_copy(update={"waypoint_order": "optimize"})
    source = (
        await WaypointPlanner(
            cast(AutoTourRoutingBackend, backend),
            RouteResultFactory(),
            max_evaluations=4,
        ).generate(request)
    ).candidates[0]
    start, first, second, end = source.traversal.anchors
    actual = source.model_copy(
        update={
            "traversal": PlanTraversal(
                direction="start_to_end",
                anchors=(
                    start,
                    second.model_copy(update={"route_progress": 0.3}),
                    first.model_copy(update={"route_progress": 0.6}),
                    end,
                ),
            )
        }
    )
    transformed = transform_reverse_request(request, actual, candidate_count=2)
    assert isinstance(transformed, WaypointPlanRequest)
    assert [waypoint.id for waypoint in transformed.waypoints] == [
        "middle-a",
        "middle-b",
    ]
    assert transformed.candidate_count == 2
    assert transformed.distance_objective == request.distance_objective
    assert transformed.preferences == request.preferences


@pytest.mark.asyncio
async def test_reverse_source_tampering_is_rejected() -> None:
    backend = _DirectionalBackend()
    request = _open_request()
    generated = await WaypointPlanner(
        cast(AutoTourRoutingBackend, backend), RouteResultFactory(), max_evaluations=3
    ).generate(request)
    candidate = generated.candidates[0].model_copy(update={"id": "forged"})
    with pytest.raises(ValueError, match="signature"):
        await ReversePlanner(
            cast(AutoTourRoutingBackend, backend), RouteResultFactory()
        ).reverse(
            ReversePlanRequest(
                schema_version=1,
                source_request=request,
                candidate=candidate,
            )
        )

    wrong_kind = generated.candidates[0].model_copy(update={"kind": "auto_tour"})
    with pytest.raises(ValueError, match="kind"):
        await ReversePlanner(
            cast(AutoTourRoutingBackend, backend), RouteResultFactory()
        ).reverse(
            ReversePlanRequest(
                schema_version=1,
                source_request=request,
                candidate=wrong_kind,
            )
        )

    source = generated.candidates[0]
    altered_anchor = source.traversal.anchors[1].model_copy(
        update={"name": "Client-supplied detour"}
    )
    altered_traversal = source.traversal.model_copy(
        update={
            "anchors": (
                source.traversal.anchors[0],
                altered_anchor,
                *source.traversal.anchors[2:],
            )
        }
    )
    with pytest.raises(ValueError, match="traversal metadata"):
        await ReversePlanner(
            cast(AutoTourRoutingBackend, backend), RouteResultFactory()
        ).reverse(
            ReversePlanRequest(
                schema_version=1,
                source_request=request,
                candidate=source.model_copy(update={"traversal": altered_traversal}),
            )
        )


@pytest.mark.asyncio
async def test_exact_reverse_failure_is_not_weakened() -> None:
    source_backend = _DirectionalBackend()
    request = _open_request()
    source = (
        await WaypointPlanner(
            cast(AutoTourRoutingBackend, source_backend),
            RouteResultFactory(),
            max_evaluations=4,
        ).generate(request)
    ).candidates[0]
    with pytest.raises(ExactWaypointNotReachedError) as caught:
        await ReversePlanner(
            cast(AutoTourRoutingBackend, _MissExactBackend()), RouteResultFactory()
        ).reverse(
            ReversePlanRequest(
                schema_version=1,
                source_request=request,
                candidate=source,
            )
        )
    assert caught.value.point_id == "middle-b"


@pytest.mark.asyncio
async def test_unresolved_soft_stop_is_dropped_not_routed_semantically() -> None:
    source_backend = _BestEffortBackend()
    request = _soft_request()
    source = (
        await WaypointPlanner(
            cast(AutoTourRoutingBackend, source_backend),
            RouteResultFactory(),
            max_evaluations=4,
        ).generate(request)
    ).candidates[0]
    reverse_backend = _UnreachableSoftBackend()
    response = await ReversePlanner(
        cast(AutoTourRoutingBackend, reverse_backend), RouteResultFactory()
    ).reverse(
        ReversePlanRequest(
            schema_version=1,
            source_request=request,
            candidate=source,
        )
    )
    candidate = response.result.candidates[0]
    assert [stop.id for stop in candidate.dropped_stops] == ["soft-viewpoint"]
    assert not candidate.reached_stops
    assert not candidate.approximated_stops
    assert reverse_backend.calls == [((request.end, request.start), "city_bike")]


@pytest.mark.asyncio
async def test_soft_outcome_is_recalculated_and_remains_a_traversal_anchor() -> None:
    backend = _BestEffortBackend()
    request = _soft_request()
    source_result = await WaypointPlanner(
        cast(AutoTourRoutingBackend, backend), RouteResultFactory(), max_evaluations=4
    ).generate(request)
    source = source_result.candidates[0]
    assert [stop.id for stop in source.approximated_stops] == ["soft-viewpoint"]
    assert [
        anchor.id
        for anchor in source.traversal.anchors
        if anchor.kind == "approximated_stop"
    ] == ["stop/soft-viewpoint"]
    response = await ReversePlanner(
        cast(AutoTourRoutingBackend, backend), RouteResultFactory()
    ).reverse(
        ReversePlanRequest(
            schema_version=1,
            source_request=request,
            candidate=source,
        )
    )
    reversed_candidate = response.result.candidates[0]
    assert [stop.id for stop in reversed_candidate.approximated_stops] == [
        "soft-viewpoint"
    ]
    assert not reversed_candidate.dropped_stops
    assert response.result.search_diagnostics.budget.phases["approach"].used == 1
    assert response.result.search_diagnostics.budget.phases["reverse"].used == 1
    assert response.result.search_diagnostics.cache.backend_call_count == 2


@pytest.mark.asyncio
async def test_loop_reverse_keeps_start_and_uses_private_shape_anchors() -> None:
    backend = _DirectionalBackend()
    request = _loop_request()
    source_result = await WaypointPlanner(
        cast(AutoTourRoutingBackend, backend), RouteResultFactory(), max_evaluations=4
    ).generate(request)
    response = await ReversePlanner(
        cast(AutoTourRoutingBackend, backend), RouteResultFactory()
    ).reverse(
        ReversePlanRequest(
            schema_version=1,
            source_request=request,
            candidate=source_result.candidates[0],
        )
    )
    transformed = response.transformed_request
    assert isinstance(transformed, WaypointPlanRequest)
    assert transformed.start == request.start
    candidate = response.result.candidates[0]
    assert candidate.route.geometry[0] == candidate.route.geometry[-1]
    assert response.result.search_diagnostics.details["internal_shape_anchor_count"] > 0
    assert not candidate.reached_stops
    assert all(
        not anchor.id.startswith("shape/") for anchor in candidate.traversal.anchors
    )
    assert response.result.search_diagnostics.budget.phases["reverse"].used == 1
    assert [anchor.kind for anchor in candidate.traversal.anchors].count("start") == 1
    assert all(anchor.kind != "end" for anchor in candidate.traversal.anchors)


def test_auto_loop_direction_preference_inverts_from_selected_orientation(
    route_result: RouteResult,
) -> None:
    request = PLAN_REQUEST_ADAPTER.validate_python(
        {
            "schema_version": 1,
            "kind": "auto_tour",
            "name": "Loop",
            "topology": "loop",
            "start": {"lat": 48.871389, "lon": 2.096667},
            "end": None,
            "routing_profile": "hike",
            "candidate_count": 1,
            "seed": 1,
            "distance_objective": {
                "target_m": 5_000,
                "tolerance_m": 1_000,
                "maximum_m": None,
                "priority": "flexible",
            },
            "preferences": {
                "nature": "off",
                "path_selection": "shortest",
                "scenic": "off",
                "drinking_water": "off",
                "loop_geometry": "off",
                "direction": "any",
            },
            "hard_waypoints": [
                {
                    "id": "hard-a",
                    "name": "Hard A",
                    "coordinate": {"lat": 48.872, "lon": 2.10},
                },
                {
                    "id": "hard-b",
                    "name": "Hard B",
                    "coordinate": {"lat": 48.873, "lon": 2.11},
                },
            ],
            "requested_stops": [
                {
                    "id": "soft-a",
                    "name": "Soft A",
                    "semantic_coordinate": {"lat": 48.874, "lon": 2.112},
                    "importance": "prefer",
                    "constraint_strength": "approach",
                },
                {
                    "id": "soft-b",
                    "name": "Soft B",
                    "semantic_coordinate": {"lat": 48.875, "lon": 2.114},
                    "importance": "must_visit",
                    "constraint_strength": "best_effort",
                    "maximum_best_effort_distance_m": 500,
                },
            ],
            "preferred_discovered_poi_ids": [],
            "free_poi_spur_physical_m": 200,
        }
    )
    assert isinstance(request, AutoTourPlanRequest)
    start = request.start
    candidate = PlanCandidate(
        id="source",
        kind="auto_tour",
        topology="loop",
        routing_profile="hike",
        rank=1,
        roles=("harmonious",),
        route=route_result,
        score=PlanScore(total=0),
        traversal=PlanTraversal(
            direction="clockwise",
            anchors=(
                PlanTraversalAnchor(
                    id="endpoint/start",
                    name="Start",
                    kind="start",
                    routed_coordinate=start,
                    semantic_coordinate=start,
                    route_progress=0,
                    constraint_strength="exact",
                    outcome="reached",
                ),
            ),
        ),
        diagnostics=PlanCandidateDiagnostics(
            safety_eligible=True,
            target_error_m=0,
            within_tolerance=True,
            requested_stop_count=0,
            immediate_backtracking_m=0,
            repeated_distance_m=0,
        ),
    )
    transformed = transform_reverse_request(request, candidate, candidate_count=1)
    assert isinstance(transformed, AutoTourPlanRequest)
    assert transformed.start == request.start
    assert transformed.preferences.direction == "counterclockwise"
    assert [waypoint.id for waypoint in transformed.hard_waypoints] == [
        "hard-b",
        "hard-a",
    ]
    assert [stop.id for stop in transformed.requested_stops] == [
        "soft-b",
        "soft-a",
    ]
    assert [stop.constraint_strength for stop in transformed.requested_stops] == [
        "best_effort",
        "approach",
    ]
    assert (
        PLAN_REQUEST_ADAPTER.validate_python(transformed.model_dump(mode="json"))
        == transformed
    )
