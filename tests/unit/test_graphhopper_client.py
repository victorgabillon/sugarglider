"""GraphHopper HTTP adapter tests using an in-memory transport."""

import httpx
import pytest

from sugarglider.domain.models import Coordinate
from sugarglider.routing.graphhopper import (
    GraphHopperClient,
    RoutingPointError,
    RoutingTimeoutError,
    RoutingUnavailableError,
    RoutingUpstreamError,
)


def route_payload(*, include_details: bool = True) -> dict[str, object]:
    """Build a representative unencoded GraphHopper response."""
    path: dict[str, object] = {
        "distance": 1234.5,
        "time": 456789,
        "ascend": 12.0,
        "descend": 9.0,
        "points": {
            "type": "LineString",
            "coordinates": [[2.09, 48.87], [2.10, 48.88], [2.11, 48.89]],
        },
        "snapped_waypoints": {
            "type": "LineString",
            "coordinates": [[2.09, 48.87], [2.11, 48.89]],
        },
    }
    if include_details:
        path["details"] = {"surface": [[0, 2, "PAVED"]], "edge_id": [[0, 2, 7]]}
    return {"paths": [path]}


@pytest.mark.asyncio
async def test_route_sends_lon_lat_and_parses_response() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        payload = request.read().decode()
        captured["body"] = payload
        return httpx.Response(200, json=route_payload())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = GraphHopperClient("http://graphhopper:8989", client=http_client)
        path = await client.route(
            (Coordinate(lat=48.87, lon=2.09), Coordinate(lat=48.89, lon=2.11))
        )

    body = str(captured["body"])
    assert '"points":[[2.09,48.87],[2.11,48.89]]' in body
    assert '"profile":"hike"' in body
    assert '"points_encoded":false' in body
    assert path.geometry == ((2.09, 48.87), (2.10, 48.88), (2.11, 48.89))
    assert path.distance_m == 1234.5
    assert path.duration_ms == 456789
    assert path.ascend_m == 12.0
    assert path.details["surface"][0].value == "PAVED"


@pytest.mark.asyncio
async def test_missing_details_are_tolerated() -> None:
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(200, json=route_payload(include_details=False))
    )
    async with httpx.AsyncClient(transport=transport) as http_client:
        path = await GraphHopperClient("http://test", client=http_client).route(
            (Coordinate(lat=48, lon=2), Coordinate(lat=49, lon=3))
        )
    assert path.details == {}


@pytest.mark.asyncio
async def test_unsupported_optional_details_are_retried_without_details() -> None:
    requests = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        if requests == 1:
            return httpx.Response(
                400, json={"message": "Unknown path detail: smoothness"}
            )
        assert b'"details"' not in request.read()
        return httpx.Response(200, json=route_payload(include_details=False))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        path = await GraphHopperClient("http://test", client=http_client).route(
            (Coordinate(lat=48, lon=2), Coordinate(lat=49, lon=3))
        )
    assert requests == 2
    assert path.details == {}


@pytest.mark.asyncio
async def test_timeout_is_mapped() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        with pytest.raises(RoutingTimeoutError):
            await GraphHopperClient("http://test", client=http_client).route(
                (Coordinate(lat=48, lon=2), Coordinate(lat=49, lon=3))
            )


@pytest.mark.asyncio
async def test_connection_failure_is_mapped() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        with pytest.raises(RoutingUnavailableError):
            await GraphHopperClient("http://test", client=http_client).route(
                (Coordinate(lat=48, lon=2), Coordinate(lat=49, lon=3))
            )


@pytest.mark.asyncio
async def test_graphhopper_400_error_is_mapped() -> None:
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(
            400, json={"message": "Point 1 is out of bounds", "hints": []}
        )
    )
    async with httpx.AsyncClient(transport=transport) as http_client:
        with pytest.raises(RoutingPointError):
            await GraphHopperClient("http://test", client=http_client).route(
                (Coordinate(lat=48, lon=2), Coordinate(lat=49, lon=3))
            )


@pytest.mark.asyncio
async def test_graphhopper_504_is_mapped_to_timeout() -> None:
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(504, json={"message": "routing timeout"})
    )
    async with httpx.AsyncClient(transport=transport) as http_client:
        with pytest.raises(RoutingTimeoutError):
            await GraphHopperClient("http://test", client=http_client).route(
                (Coordinate(lat=48, lon=2), Coordinate(lat=49, lon=3))
            )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"paths": []},
        {"paths": [{}]},
        {"paths": [{"distance": 2, "time": 3, "points": {"type": "LineString"}}]},
    ],
)
async def test_malformed_success_response_is_rejected(
    payload: dict[str, object],
) -> None:
    transport = httpx.MockTransport(lambda _request: httpx.Response(200, json=payload))
    async with httpx.AsyncClient(transport=transport) as http_client:
        with pytest.raises(RoutingUpstreamError):
            await GraphHopperClient("http://test", client=http_client).route(
                (Coordinate(lat=48, lon=2), Coordinate(lat=49, lon=3))
            )


@pytest.mark.asyncio
async def test_readiness_requires_hike_profile() -> None:
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(
            200, json={"profiles": [{"name": "hike"}], "elevation": False}
        )
    )
    async with httpx.AsyncClient(transport=transport) as http_client:
        assert await GraphHopperClient("http://test", client=http_client).is_ready()
