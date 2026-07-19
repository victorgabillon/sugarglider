"""Opt-in integration test against a locally running GraphHopper 11 instance."""

import json
import math
import os
from pathlib import Path
from xml.etree import ElementTree

import httpx
import pytest

from sugarglider.analysis.route import RouteAnalyzer, haversine_distance_m
from sugarglider.domain.generation import RouteGenerationRequest
from sugarglider.domain.models import Coordinate, RouteRequest
from sugarglider.generation.service import RouteGenerationService
from sugarglider.gpx.writer import GPX_NAMESPACE, write_gpx
from sugarglider.routing.graphhopper import GraphHopperClient
from sugarglider.routing.result import RouteResultFactory
from sugarglider.routing.service import RouteService
from sugarglider.tours.models import AutoTourRequest
from sugarglider.tours.service import AutoTourService

pytestmark = pytest.mark.integration


def distance_degrees(left: tuple[float, float], right: tuple[float, float]) -> float:
    """Sufficient local proximity measure for snapped endpoint assertions."""
    return math.hypot(left[0] - right[0], left[1] - right[1])


@pytest.mark.asyncio
async def test_live_marly_route() -> None:
    if os.getenv("RUN_GRAPHHOPPER_INTEGRATION") != "1":
        pytest.skip("set RUN_GRAPHHOPPER_INTEGRATION=1 to use live GraphHopper")

    base_url = os.getenv("GRAPHHOPPER_URL", "http://localhost:8989")
    async with httpx.AsyncClient() as http_client:
        service = RouteService(GraphHopperClient(base_url, client=http_client))
        result = await service.route(
            RouteRequest(
                name="Marly integration",
                points=[
                    Coordinate(lat=48.871389, lon=2.096667),
                    Coordinate(lat=48.871454, lon=2.124421),
                    Coordinate(lat=48.861560, lon=2.108330),
                ],
            )
        )

    assert result.summary.distance_m > 0
    assert len(result.geometry) > 3
    assert result.snapped_points is not None
    assert distance_degrees(result.geometry[0], result.snapped_points[0]) < 0.001
    assert distance_degrees(result.geometry[-1], result.snapped_points[-1]) < 0.001
    analysis = result.analysis
    assert analysis.route_distance_m == pytest.approx(result.summary.distance_m)
    assert analysis.distance_scale_factor > 0
    surface_distance = (
        analysis.paved.distance_m
        + analysis.unpaved.distance_m
        + analysis.unknown_surface.distance_m
    )
    assert surface_distance == pytest.approx(analysis.route_distance_m)
    assert analysis.repetition.edge_id_coverage.share > 0.9
    assert analysis.detail_breakdowns["road_class"].coverage_share > 0
    assert analysis.detail_breakdowns["surface"].coverage_share > 0
    metrics = (
        analysis.paved,
        analysis.unpaved,
        analysis.unknown_surface,
        analysis.trail_like,
        analysis.official_hiking_network,
        analysis.major_road,
        analysis.car_accessible,
        analysis.repetition.edge_id_coverage,
        analysis.repetition.repeated_distance,
    )
    assert all(metric.distance_m >= 0 and metric.share >= 0 for metric in metrics)


@pytest.mark.asyncio
async def test_live_marly_target_distance_generation() -> None:
    if os.getenv("RUN_GRAPHHOPPER_INTEGRATION") != "1":
        pytest.skip("set RUN_GRAPHHOPPER_INTEGRATION=1 to use live GraphHopper")

    request = RouteGenerationRequest(
        name="Marly 41 km trail",
        points=[
            Coordinate(lat=48.871389, lon=2.096667),
            Coordinate(lat=48.871454, lon=2.124421),
            Coordinate(lat=48.861560, lon=2.108330),
            Coordinate(lat=48.862849, lon=2.099448),
            Coordinate(lat=48.871500, lon=2.043000),
            Coordinate(lat=48.890810, lon=2.021530),
        ],
        target_distance_m=41_000,
        tolerance_m=2_000,
        candidate_count=3,
        seed=42,
    )
    base_url = os.getenv("GRAPHHOPPER_URL", "http://localhost:8989")
    async with httpx.AsyncClient() as http_client:
        result = await RouteGenerationService(
            GraphHopperClient(base_url, client=http_client), max_evaluations=48
        ).generate(request)

    assert result.candidates
    assert result.search.evaluated_candidate_count <= result.search.search_budget
    assert len({candidate.signature for candidate in result.candidates}) == len(
        result.candidates
    )
    best = result.candidates[0]
    baseline_error = abs(result.baseline.summary.distance_m - 41_000)
    assert best.target_error_m < baseline_error
    assert best.route.summary.distance_m > result.baseline.summary.distance_m
    assert any(candidate.within_tolerance for candidate in result.candidates)

    required = tuple((point.lon, point.lat) for point in request.points)
    for candidate in result.candidates:
        route = candidate.route
        assert candidate.optional_points
        assert route.summary.input_point_count == request.required_point_count
        assert route.analysis.route_distance_m == pytest.approx(
            route.summary.distance_m
        )
        assert route.snapped_points is not None
        assert len(route.snapped_points) > request.required_point_count
        required_index = 0
        for snapped in route.snapped_points:
            if required_index >= len(required):
                break
            if haversine_distance_m(required[required_index], snapped) < 500:
                required_index += 1
        assert required_index == len(required)
        assert route.analysis.repetition.edge_id_coverage.share > 0.8
        metrics = (
            route.analysis.paved,
            route.analysis.unpaved,
            route.analysis.unknown_surface,
            route.analysis.trail_like,
            route.analysis.major_road,
            route.analysis.repetition.repeated_distance,
        )
        assert all(
            metric.distance_m >= 0 and 0 <= metric.share <= 1 for metric in metrics
        )

    root = ElementTree.fromstring(write_gpx(best.route))
    namespace = {"g": GPX_NAMESPACE}
    assert len(root.findall("g:trk", namespace)) == 1
    assert len(root.findall("g:trk/g:trkseg", namespace)) == 1
    assert len(root.findall("g:trk/g:trkseg/g:trkpt", namespace)) > 1
    assert root.findall("g:rte", namespace) == []


@pytest.mark.asyncio
async def test_live_bastille_to_marly_is_a_genuine_open_path() -> None:
    if os.getenv("RUN_GRAPHHOPPER_INTEGRATION") != "1":
        pytest.skip("set RUN_GRAPHHOPPER_INTEGRATION=1 to use live GraphHopper")

    start = Coordinate(lat=48.853, lon=2.369, name="Place de la Bastille")
    end = Coordinate(lat=48.871389, lon=2.096667, name="Gare de Marly-le-Roi")
    request = RouteGenerationRequest(
        name="Bastille to Marly",
        start=start,
        end=end,
        points=[],
        route_topology="point_to_point",
        target_distance_m=26_000,
        tolerance_m=2_000,
        candidate_count=3,
        path_selection_mode="low_overlap",
        loop_geometry_preference="off",
    )
    base_url = os.getenv("GRAPHHOPPER_URL", "http://localhost:8989")
    async with httpx.AsyncClient() as http_client:
        result = await RouteGenerationService(
            GraphHopperClient(base_url, client=http_client), max_evaluations=48
        ).generate(request)

    assert result.topology == "point_to_point"
    assert result.endpoint_warnings == ()
    assert all(visit.satisfied for visit in result.endpoint_visits)
    best = result.candidates[0]
    assert result.baseline.analysis.loop_geometry is None
    assert best.route.analysis.loop_geometry is None
    assert best.route.geometry[0] != best.route.geometry[-1]
    assert haversine_distance_m(best.route.geometry[0], (start.lon, start.lat)) < 300
    assert haversine_distance_m(best.route.geometry[-1], (end.lon, end.lat)) < 300
    root = ElementTree.fromstring(write_gpx(best.route))
    namespace = {"g": GPX_NAMESPACE}
    points = root.findall("g:trk/g:trkseg/g:trkpt", namespace)
    assert len(root.findall("g:trk", namespace)) == 1
    assert len(root.findall("g:trk/g:trkseg", namespace)) == 1
    assert root.findall("g:rte", namespace) == []
    assert points[0].attrib != points[-1].attrib


@pytest.mark.asyncio
async def test_live_bastille_to_marly_45km_attempts_all_22_requested_places() -> None:
    if os.getenv("RUN_GRAPHHOPPER_INTEGRATION") != "1":
        pytest.skip("set RUN_GRAPHHOPPER_INTEGRATION=1 to use live GraphHopper")

    document = json.loads(
        Path("examples/marly/bastille-to-marly-22-places-auto-tour.json").read_text(
            encoding="utf-8"
        )
    )
    points = document.pop("points")
    end = document["end"]
    requested_points = [
        point
        for point in points
        if (point["lat"], point["lon"]) != (end["lat"], end["lon"])
    ]
    document["requested_places"] = [
        {
            "id": f"marly-{index}",
            "name": point["name"],
            "coordinate": {"lat": point["lat"], "lon": point["lon"]},
            "visit_radius_m": 100,
            "importance": "must_visit",
            "original_index": index,
        }
        for index, point in enumerate(requested_points, start=1)
    ]
    request = AutoTourRequest.model_validate(document)
    assert len(request.requested_places) == 22
    assert all(
        place.coordinate != request.effective_end for place in request.requested_places
    )

    base_url = os.getenv("GRAPHHOPPER_URL", "http://localhost:8989")
    async with httpx.AsyncClient(timeout=240) as http_client:
        result = await AutoTourService(
            GraphHopperClient(base_url, client=http_client),
            RouteResultFactory(RouteAnalyzer()),
        ).generate(request)

    recommended = result.candidates[0]
    visits = recommended.requested_place_visits
    missed = tuple(visit for visit in visits if not visit.satisfied)
    assert len(visits) == 22
    assert result.topology == "point_to_point"
    assert result.effective_start == request.start
    assert result.effective_end == request.end
    assert recommended.route.geometry[0] != recommended.route.geometry[-1]
    assert (
        haversine_distance_m(
            recommended.route.geometry[0],
            (request.effective_start.lon, request.effective_start.lat),
        )
        < 300
    )
    assert (
        haversine_distance_m(
            recommended.route.geometry[-1],
            (request.effective_end.lon, request.effective_end.lat),
        )
        < 300
    )
    assert all(visit.deliberately_considered for visit in visits)
    assert any(visit.deliberately_routed for visit in visits)
    assert recommended.satisfied_must_visit_count > 0
    assert recommended.route.summary.distance_m <= recommended.maximum_distance_m
    assert result.search.requested_place_route_evaluations > 0
    assert result.search.discovered_poi_route_evaluations == 0
    assert result.search.complete_set_candidate_distance_m is not None
    assert result.search.full_set_route_attempted
    assert result.search.maximum_distance_m == 200_000
    assert all(visit.failure_reason is not None for visit in missed)
    root = ElementTree.fromstring(write_gpx(recommended.route))
    namespace = {"g": GPX_NAMESPACE}
    track_points = root.findall("g:trk/g:trkseg/g:trkpt", namespace)
    assert root.findall("g:rte", namespace) == []
    assert track_points[0].attrib != track_points[-1].attrib


@pytest.mark.asyncio
async def test_live_marly_all_pois_optimized_loop() -> None:
    if os.getenv("RUN_GRAPHHOPPER_INTEGRATION") != "1":
        pytest.skip("set RUN_GRAPHHOPPER_INTEGRATION=1 to use live GraphHopper")

    request = RouteGenerationRequest.model_validate_json(
        Path("examples/marly/all-pois-generation-request.json").read_text(
            encoding="utf-8"
        )
    )
    assert request.required_point_count == 23
    assert request.path_selection_mode == "low_overlap"
    shortest_request = request.model_copy(update={"path_selection_mode": "shortest"})
    base_url = os.getenv("GRAPHHOPPER_URL", "http://localhost:8989")
    async with httpx.AsyncClient() as http_client:
        backend = GraphHopperClient(base_url, client=http_client)
        service = RouteGenerationService(backend, max_evaluations=48)
        standard_result = await service.generate(shortest_request)
        result = await service.generate(request)

    assert standard_result.candidates
    assert result.candidates
    assert result.search.evaluated_candidate_count <= result.search.search_budget
    assert (
        result.search.alternative_leg_request_count
        <= result.search.low_overlap_request_budget
    )
    best = result.candidates[0]
    for candidate in (*standard_result.candidates, *result.candidates):
        indices = [visit.original_index for visit in candidate.required_point_order]
        assert indices[0] == 0
        assert sorted(indices) == list(range(23))
        assert len(indices) == len(set(indices))
        assert (
            candidate.routing_points[0] == candidate.required_point_order[0].coordinate
        )
        assert len(candidate.routing_points) == 23 + len(candidate.optional_points)
        assert candidate.route.snapped_points is not None
        assert len(candidate.route.snapped_points) == len(candidate.routing_points) + 1
    refined = tuple(
        candidate
        for candidate in result.candidates
        if candidate.construction == "alternative_leg_beam"
    )
    standard_control = next(
        candidate
        for candidate in result.candidates
        if candidate.construction != "alternative_leg_beam"
    )
    assert standard_control.signature in {
        candidate.signature for candidate in standard_result.candidates
    }
    if best.construction == "alternative_leg_beam":
        assert 39_000 <= best.route.summary.distance_m <= 43_000
        assert (
            best.route.analysis.repetition.repeated_distance.share
            < standard_control.route.analysis.repetition.repeated_distance.share
        )
        assert (
            best.route.analysis.immediate_backtrack.share
            <= standard_control.route.analysis.immediate_backtrack.share
        )
    else:
        assert "low_overlap_no_natural_improvement" in result.search.warnings
    if not refined:
        assert "low_overlap_no_complete_candidate" in result.search.warnings
    pre_repeated = result.search.pre_low_overlap_repeated_share
    best_repeated = result.search.best_low_overlap_repeated_share
    assert pre_repeated is not None
    assert best_repeated is not None
    assert (
        best_repeated < pre_repeated
        or "low_overlap_no_repetition_improvement" in result.search.warnings
        or "low_overlap_no_complete_candidate" in result.search.warnings
    )
    assert (
        result.search.best_order_repeated_share
        < result.search.fixed_order_repeated_share
        or "order_optimization_no_repetition_improvement" in result.search.warnings
    )
    assert (
        result.search.best_order_backtrack_share
        < result.search.fixed_order_backtrack_share
        or "order_optimization_no_backtrack_improvement" in result.search.warnings
    )

    snapped = best.route.snapped_points
    assert snapped is not None
    required_index = 0
    for snapped_point in snapped:
        if required_index >= len(best.required_point_order):
            break
        required = best.required_point_order[required_index].coordinate
        if haversine_distance_m((required.lon, required.lat), snapped_point) < 1_000:
            required_index += 1
    assert required_index == 23
    assert haversine_distance_m(snapped[0], snapped[-1]) < 500
    assert best.route.analysis.repetition.edge_id_coverage.share > 0.8
    assert 0 <= best.route.analysis.immediate_backtrack.share <= 1
    assert best.route.path_details

    root = ElementTree.fromstring(write_gpx(best.route))
    namespace = {"g": GPX_NAMESPACE}
    assert len(root.findall("g:trk", namespace)) == 1
    assert len(root.findall("g:trk/g:trkseg", namespace)) == 1
    assert len(root.findall("g:trk/g:trkseg/g:trkpt", namespace)) > 1
    assert root.findall("g:rte", namespace) == []
