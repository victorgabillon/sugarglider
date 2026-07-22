"""GraphHopper HTTP adapter tests using an in-memory transport."""

import json
from typing import cast

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
from sugarglider.routing.profiles import RoutingProfileId, routing_profile


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


def info_payload(encoded_values: list[str]) -> dict[str, object]:
    return {
        "profiles": [{"name": "hike"}],
        "encoded_values": encoded_values,
        "elevation": False,
    }


def round_trip_payload() -> dict[str, object]:
    path = {
        "distance": 10_000.0,
        "time": 7_200_000,
        "points": {
            "type": "LineString",
            "coordinates": [[2.09, 48.87], [2.12, 48.89], [2.09, 48.87]],
        },
        "snapped_waypoints": {
            "type": "LineString",
            "coordinates": [
                [2.09, 48.87],
                [2.12, 48.89],
                [2.09, 48.87],
            ],
        },
    }
    return {"paths": [path]}


def requested_details(request: httpx.Request) -> list[str]:
    payload: object = json.loads(request.read())
    if not isinstance(payload, dict):
        raise AssertionError("route request is not an object")
    details = payload.get("details")
    if not isinstance(details, list) or not all(
        isinstance(detail, str) for detail in details
    ):
        raise AssertionError("route request has invalid details")
    return cast(list[str], details)


def alternative_payload(edge_ids: tuple[int, ...]) -> dict[str, object]:
    paths: list[dict[str, object]] = []
    for edge_id in edge_ids:
        payload = route_payload()
        path = cast(list[dict[str, object]], payload["paths"])[0]
        path["details"] = {"edge_id": [[0, 2, edge_id]], "surface": [[0, 2, "PAVED"]]}
        paths.append(path)
    return {"paths": paths}


@pytest.mark.asyncio
async def test_route_sends_lon_lat_and_parses_response() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/info":
            return httpx.Response(
                200,
                json=info_payload(
                    [
                        "surface",
                        "foot_network",
                        "foot_priority",
                        "foot_road_access",
                        "car_access",
                    ]
                ),
            )
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
    assert '"foot_network"' in body
    assert '"foot_priority"' in body
    assert '"foot_road_access"' in body
    assert '"car_access"' in body
    assert path.geometry == ((2.09, 48.87), (2.10, 48.88), (2.11, 48.89))
    assert path.distance_m == 1234.5
    assert path.duration_ms == 456789
    assert path.ascend_m == 12.0
    assert path.details["surface"][0].value == "PAVED"


@pytest.mark.asyncio
async def test_generated_route_sets_pass_through_without_changing_default() -> None:
    bodies: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/info":
            return httpx.Response(200, json=info_payload([]))
        bodies.append(request.read().decode())
        return httpx.Response(200, json=route_payload())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = GraphHopperClient("http://test", client=http_client)
        points = (Coordinate(lat=48.87, lon=2.09), Coordinate(lat=48.89, lon=2.11))
        await client.route(points)
        await client.route(points, pass_through=True)

    assert '"pass_through"' not in bodies[0]
    assert '"pass_through":true' in bodies[1]


@pytest.mark.asyncio
async def test_every_profile_sends_exact_resolved_snap_preventions_and_mapping() -> (
    None
):
    payloads: list[dict[str, object]] = []
    profile_ids: tuple[RoutingProfileId, ...] = (
        "trail_run",
        "hike",
        "city_bike",
        "gravel_bike",
        "mountain_bike",
        "road_bike",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/info":
            return httpx.Response(
                200,
                json={
                    "profiles": [
                        {"name": routing_profile(profile).graphhopper_profile}
                        for profile in profile_ids
                    ],
                    "encoded_values": [],
                },
            )
        payloads.append(cast(dict[str, object], json.loads(request.read())))
        return httpx.Response(200, json=route_payload(include_details=False))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = GraphHopperClient("http://test", client=http_client)
        points = (Coordinate(lat=48, lon=2), Coordinate(lat=49, lon=3))
        for profile in profile_ids:
            await client.route(points, profile)

    for payload, profile_id in zip(payloads, profile_ids, strict=True):
        resolved = routing_profile(profile_id)
        assert payload["profile"] == resolved.graphhopper_profile
        assert payload["snap_preventions"] == list(resolved.snap_preventions)
        assert "steps" not in cast(list[object], payload["snap_preventions"])


@pytest.mark.asyncio
async def test_alternatives_post_full_parameters_and_parse_all_distinct_paths() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/info":
            return httpx.Response(200, json={"profiles": [{"name": "hike"}]})
        captured["method"] = request.method
        captured["payload"] = json.loads(request.read())
        return httpx.Response(200, json=alternative_payload((7, 8, 7)))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        alternatives = await GraphHopperClient(
            "http://test", client=http_client
        ).alternative_routes(
            Coordinate(lat=48.87, lon=2.09),
            Coordinate(lat=48.89, lon=2.11),
            max_paths=3,
            max_weight_factor=1.6,
            max_share_factor=0.5,
        )

    payload = cast(dict[str, object], captured["payload"])
    assert captured["method"] == "POST"
    assert payload["points"] == [[2.09, 48.87], [2.11, 48.89]]
    assert payload["algorithm"] == "alternative_route"
    assert payload["alternative_route.max_paths"] == 3
    assert payload["alternative_route.max_weight_factor"] == 1.6
    assert payload["alternative_route.max_share_factor"] == 0.5
    assert payload["snap_preventions"] == list(routing_profile("hike").snap_preventions)
    assert payload["details"] == [
        "edge_id",
        *routing_profile("hike").requested_path_details,
    ]
    assert [path.details["edge_id"][0].value for path in alternatives] == [7, 8]


@pytest.mark.asyncio
async def test_malformed_later_alternative_rejects_complete_response() -> None:
    payload = alternative_payload((7, 8))
    paths = cast(list[dict[str, object]], payload["paths"])
    paths[1]["points"] = {"type": "LineString", "coordinates": []}
    transport = httpx.MockTransport(lambda _request: httpx.Response(200, json=payload))
    async with httpx.AsyncClient(transport=transport) as http_client:
        with pytest.raises(RoutingUpstreamError):
            await GraphHopperClient(
                "http://test", client=http_client
            ).alternative_routes(
                Coordinate(lat=48.87, lon=2.09),
                Coordinate(lat=48.89, lon=2.11),
            )


@pytest.mark.asyncio
async def test_alternative_requires_exactly_two_snapped_endpoints() -> None:
    payload = alternative_payload((7,))
    path = cast(list[dict[str, object]], payload["paths"])[0]
    path.pop("snapped_waypoints")
    transport = httpx.MockTransport(lambda _request: httpx.Response(200, json=payload))
    async with httpx.AsyncClient(transport=transport) as http_client:
        with pytest.raises(RoutingUpstreamError, match="snapped waypoints"):
            await GraphHopperClient(
                "http://test", client=http_client
            ).alternative_routes(
                Coordinate(lat=48.87, lon=2.09),
                Coordinate(lat=48.89, lon=2.11),
            )


@pytest.mark.asyncio
async def test_alternative_unsupported_detail_retries_complete_request() -> None:
    requests: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/info":
            return httpx.Response(200, json={"profiles": [{"name": "hike"}]})
        requests.append(cast(dict[str, object], json.loads(request.read())))
        if len(requests) == 1:
            return httpx.Response(
                400, json={"message": "Unknown path detail: smoothness"}
            )
        return httpx.Response(200, json=alternative_payload((7, 8)))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        alternatives = await GraphHopperClient(
            "http://test", client=http_client
        ).alternative_routes(
            Coordinate(lat=48.87, lon=2.09),
            Coordinate(lat=48.89, lon=2.11),
        )
    assert len(alternatives) == 2
    assert requests[0]["points"] == requests[1]["points"]
    assert "smoothness" not in cast(list[str], requests[1]["details"])


@pytest.mark.asyncio
async def test_alternative_timeout_uses_existing_error_mapping() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        with pytest.raises(RoutingTimeoutError):
            await GraphHopperClient(
                "http://test", client=http_client
            ).alternative_routes(
                Coordinate(lat=48.87, lon=2.09),
                Coordinate(lat=48.89, lon=2.11),
            )


@pytest.mark.asyncio
async def test_alternative_http_unavailability_uses_existing_error_mapping() -> None:
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(503, json={"message": "unavailable"})
    )
    async with httpx.AsyncClient(transport=transport) as http_client:
        with pytest.raises(RoutingUnavailableError):
            await GraphHopperClient(
                "http://test", client=http_client
            ).alternative_routes(
                Coordinate(lat=48.87, lon=2.09),
                Coordinate(lat=48.89, lon=2.11),
            )


@pytest.mark.asyncio
async def test_round_trip_request_uses_local_post_parameters() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["body"] = request.read().decode()
        return httpx.Response(200, json=round_trip_payload())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        path = await GraphHopperClient("http://test", client=http_client).round_trip(
            Coordinate(lat=48.87, lon=2.09), 10_000, 42
        )

    assert captured["method"] == "POST"
    assert captured["path"] == "/route"
    body = str(captured["body"])
    assert '"points":[[2.09,48.87]]' in body
    assert '"algorithm":"round_trip"' in body
    assert '"round_trip.distance":10000' in body
    assert '"round_trip.seed":42' in body
    assert '"points_encoded":false' in body
    payload = cast(dict[str, object], json.loads(body))
    assert payload["snap_preventions"] == list(routing_profile("hike").snap_preventions)
    assert path.geometry[0] == path.geometry[-1]
    assert path.details == {}


@pytest.mark.asyncio
async def test_round_trip_uses_existing_error_mapping() -> None:
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(400, json={"message": "round trip failed"})
    )
    async with httpx.AsyncClient(transport=transport) as http_client:
        with pytest.raises(RoutingPointError):
            await GraphHopperClient("http://test", client=http_client).round_trip(
                Coordinate(lat=48.87, lon=2.09), 10_000, 42
            )


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
async def test_unsupported_optional_detail_retry_retains_other_details() -> None:
    route_requests = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal route_requests
        if request.url.path == "/info":
            return httpx.Response(200, json={"profiles": [{"name": "hike"}]})
        route_requests += 1
        if route_requests == 1:
            return httpx.Response(
                400, json={"message": "Unknown path detail: smoothness"}
            )
        details = requested_details(request)
        assert "smoothness" not in details
        assert "edge_id" in details
        assert "surface" in details
        return httpx.Response(200, json=route_payload(include_details=False))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        path = await GraphHopperClient("http://test", client=http_client).route(
            (Coordinate(lat=48, lon=2), Coordinate(lat=49, lon=3))
        )
    assert route_requests == 2
    assert path.details == {}


@pytest.mark.asyncio
async def test_info_excludes_unsupported_optional_details_and_is_cached() -> None:
    info_requests = 0
    captured_details: list[list[str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal info_requests
        if request.url.path == "/info":
            info_requests += 1
            return httpx.Response(200, json=info_payload(["surface", "car_access"]))
        captured_details.append(requested_details(request))
        return httpx.Response(200, json=route_payload())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = GraphHopperClient("http://test", client=http_client)
        points = (Coordinate(lat=48, lon=2), Coordinate(lat=49, lon=3))
        await client.route(points)
        await client.route(points)

    assert info_requests == 1
    assert captured_details == [
        ["edge_id", "surface", "car_access"],
        ["edge_id", "surface", "car_access"],
    ]


@pytest.mark.asyncio
async def test_optional_detail_fallback_is_isolated_per_backend_profile() -> None:
    requests: list[dict[str, object]] = []
    rejected_trail_detail = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal rejected_trail_detail
        if request.url.path == "/info":
            return httpx.Response(
                200,
                json={
                    "profiles": [
                        {"name": profile.graphhopper_profile}
                        for profile in (
                            routing_profile("trail_run"),
                            routing_profile("city_bike"),
                        )
                    ],
                    "encoded_values": [
                        "surface",
                        "road_class",
                        "smoothness",
                        "hike_rating",
                        "bike_network",
                        "bike_access",
                    ],
                },
            )
        payload = cast(dict[str, object], json.loads(request.read()))
        requests.append(payload)
        details = cast(list[str], payload["details"])
        if (
            payload["profile"] == "trail_run"
            and "hike_rating" in details
            and not rejected_trail_detail
        ):
            rejected_trail_detail = True
            return httpx.Response(
                400, json={"message": "Unknown path detail: hike_rating"}
            )
        return httpx.Response(200, json=route_payload(include_details=False))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = GraphHopperClient("http://test", client=http_client)
        points = (Coordinate(lat=48, lon=2), Coordinate(lat=49, lon=3))
        await client.route(points, "trail_run")
        await client.route(points, "city_bike")

    assert [request["profile"] for request in requests] == [
        "trail_run",
        "trail_run",
        "bike",
    ]
    assert "hike_rating" not in cast(list[str], requests[1]["details"])
    assert "bike_network" in cast(list[str], requests[2]["details"])


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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid_segments",
    [
        [[0, 0, 1]],
        [[1, 0, 1]],
        [[0, 3, 1]],
        [[0, 2, 1], [1, 2, 2]],
    ],
)
async def test_malformed_detail_intervals_are_rejected(
    invalid_segments: list[list[object]],
) -> None:
    payload = route_payload()
    paths = cast(list[dict[str, object]], payload["paths"])
    paths[0]["details"] = {"edge_id": invalid_segments}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/info":
            return httpx.Response(200, json=info_payload([]))
        return httpx.Response(200, json=payload)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        with pytest.raises(RoutingUpstreamError):
            await GraphHopperClient("http://test", client=http_client).route(
                (Coordinate(lat=48, lon=2), Coordinate(lat=49, lon=3))
            )
