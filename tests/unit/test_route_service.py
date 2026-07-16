"""Application service integration with the pure route analyzer."""

import pytest

from sugarglider.domain.models import Coordinate, PathDetailSegment, RouteRequest
from sugarglider.routing.graphhopper import (
    GraphHopperClient,
    GraphHopperPath,
    RoutingUpstreamError,
)
from sugarglider.routing.service import RouteService


class FakeGraphHopperClient(GraphHopperClient):
    def __init__(self, path: GraphHopperPath) -> None:
        self.path = path

    async def route(
        self, points: tuple[Coordinate, ...], profile: str = "hike"
    ) -> GraphHopperPath:
        return self.path

    async def is_ready(self, profile: str = "hike") -> bool:
        return True


def request() -> RouteRequest:
    return RouteRequest(
        points=[Coordinate(lat=48.0, lon=2.0), Coordinate(lat=48.1, lon=2.1)]
    )


@pytest.mark.asyncio
async def test_service_returns_raw_details_and_deterministic_analysis() -> None:
    geometry = ((2.0, 48.0), (2.01, 48.0), (2.02, 48.0))
    details = {
        "surface": (
            PathDetailSegment(from_index=0, to_index=1, value="ASPHALT"),
            PathDetailSegment(from_index=1, to_index=2, value="GRAVEL"),
        ),
        "edge_id": (PathDetailSegment(from_index=0, to_index=2, value=42),),
    }
    path = GraphHopperPath(
        distance_m=1000.0,
        duration_ms=500_000,
        ascend_m=None,
        descend_m=None,
        geometry=geometry,
        snapped_points=(geometry[0], geometry[-1]),
        details=details,
    )

    result = await RouteService(FakeGraphHopperClient(path)).route(request())

    assert result.path_details == details
    assert result.analysis.route_distance_m == result.summary.distance_m
    assert result.analysis.paved.distance_m == pytest.approx(500.0)
    assert result.analysis.unpaved.distance_m == pytest.approx(500.0)
    first_json = result.analysis.model_dump_json()
    second = await RouteService(FakeGraphHopperClient(path)).route(request())
    assert second.analysis.model_dump_json() == first_json


@pytest.mark.asyncio
async def test_impossible_geometry_is_an_upstream_error() -> None:
    coordinate = (2.0, 48.0)
    path = GraphHopperPath(
        distance_m=100.0,
        duration_ms=1000,
        ascend_m=None,
        descend_m=None,
        geometry=(coordinate, coordinate),
        snapped_points=None,
        details={},
    )
    with pytest.raises(RoutingUpstreamError):
        await RouteService(FakeGraphHopperClient(path)).route(request())
