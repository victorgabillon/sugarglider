"""Opt-in integration test against a locally running GraphHopper 11 instance."""

import math
import os
from xml.etree import ElementTree

import httpx
import pytest

from sugarglider.analysis.route import haversine_distance_m
from sugarglider.domain.generation import RouteGenerationRequest
from sugarglider.domain.models import Coordinate, RouteRequest
from sugarglider.generation.service import RouteGenerationService
from sugarglider.gpx.writer import GPX_NAMESPACE, write_gpx
from sugarglider.routing.graphhopper import GraphHopperClient
from sugarglider.routing.service import RouteService

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
