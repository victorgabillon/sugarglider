"""GraphHopper isochrone and headed round-trip contracts."""

import json
from typing import cast

import httpx
import pytest
from shapely.geometry import MultiPolygon, Polygon

from sugarglider.domain.models import Coordinate
from sugarglider.routing.errors import (
    RoutingTimeoutError,
    RoutingUnavailableError,
    RoutingUpstreamError,
)
from sugarglider.routing.graphhopper import GraphHopperClient


def _feature(geometry: dict[str, object]) -> dict[str, object]:
    return {"type": "Feature", "properties": {"bucket": 0}, "geometry": geometry}


@pytest.mark.asyncio
async def test_isochrone_get_contract_and_polygon_hole() -> None:
    captured: dict[str, object] = {}
    geometry: dict[str, object] = {
        "type": "Polygon",
        "coordinates": [
            [[2.0, 48.8], [2.2, 48.8], [2.2, 49.0], [2.0, 49.0], [2.0, 48.8]],
            [[2.05, 48.85], [2.1, 48.85], [2.1, 48.9], [2.05, 48.9], [2.05, 48.85]],
        ],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["params"] = dict(request.url.params)
        return httpx.Response(
            200, json={"type": "FeatureCollection", "features": [_feature(geometry)]}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await GraphHopperClient("http://test", client=client).isochrone(
            Coordinate(lat=48.87, lon=2.09),
            "hike",
            distance_limit_m=20_500,
        )

    assert captured == {
        "method": "GET",
        "path": "/isochrone",
        "params": {
            "point": "48.87,2.09",
            "profile": "hike",
            "distance_limit": "20500",
            "buckets": "1",
            "reverse_flow": "false",
        },
    }
    assert isinstance(result.geometry, Polygon)
    assert len(result.polygons[0].holes) == 1
    assert not result.geometry_was_repaired


@pytest.mark.asyncio
async def test_isochrone_accepts_graphhopper_polygons_and_multipolygon() -> None:
    geometry: dict[str, object] = {
        "type": "MultiPolygon",
        "coordinates": [
            [[[2.0, 48.8], [2.1, 48.8], [2.1, 48.9], [2.0, 48.9], [2.0, 48.8]]],
            [[[2.2, 48.8], [2.3, 48.8], [2.3, 48.9], [2.2, 48.9], [2.2, 48.8]]],
        ],
    }
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(200, json={"polygons": [_feature(geometry)]})
    )
    async with httpx.AsyncClient(transport=transport) as client:
        result = await GraphHopperClient("http://test", client=client).isochrone(
            Coordinate(lat=48.87, lon=2.09), "hike", distance_limit_m=10_000
        )
    assert isinstance(result.geometry, MultiPolygon)
    assert len(result.polygons) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"type": "FeatureCollection", "features": []},
        {
            "polygons": [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [[2, 48], [3, 49]],
                    },
                }
            ]
        },
        {
            "polygons": [
                {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": []}}
            ]
        },
    ],
)
async def test_isochrone_rejects_malformed_or_non_polygonal_response(
    payload: dict[str, object],
) -> None:
    transport = httpx.MockTransport(lambda _request: httpx.Response(200, json=payload))
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(RoutingUpstreamError):
            await GraphHopperClient("http://test", client=client).isochrone(
                Coordinate(lat=48.87, lon=2.09), "hike", distance_limit_m=10_000
            )


@pytest.mark.asyncio
async def test_isochrone_timeout_and_http_errors_use_routing_mapping() -> None:
    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(timeout)) as client:
        with pytest.raises(RoutingTimeoutError):
            await GraphHopperClient("http://test", client=client).isochrone(
                Coordinate(lat=48.87, lon=2.09), "hike", distance_limit_m=10_000
            )

    transport = httpx.MockTransport(
        lambda _request: httpx.Response(503, json={"message": "offline"})
    )
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(RoutingUnavailableError):
            await GraphHopperClient("http://test", client=client).isochrone(
                Coordinate(lat=48.87, lon=2.09), "hike", distance_limit_m=10_000
            )


@pytest.mark.asyncio
async def test_round_trip_optional_heading_is_sent_once() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/info":
            return httpx.Response(200, json={"profiles": [{"name": "hike"}]})
        captured["payload"] = json.loads(request.read())
        return httpx.Response(
            200,
            json={
                "paths": [
                    {
                        "distance": 10_000,
                        "time": 1,
                        "points": {
                            "type": "LineString",
                            "coordinates": [[2.09, 48.87], [2.1, 48.88], [2.09, 48.87]],
                        },
                        "details": {"edge_id": [[0, 2, 1]]},
                    }
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await GraphHopperClient("http://test", client=client).round_trip(
            Coordinate(lat=48.87, lon=2.09),
            10_000,
            42,
            heading_degrees=135,
        )

    payload = cast(dict[str, object], captured["payload"])
    assert payload["headings"] == [135]
    assert payload["algorithm"] == "round_trip"
    assert payload["details"]
