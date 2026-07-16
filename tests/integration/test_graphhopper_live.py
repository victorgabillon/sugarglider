"""Opt-in integration test against a locally running GraphHopper 11 instance."""

import math
import os

import httpx
import pytest

from sugarglider.domain.models import Coordinate, RouteRequest
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
