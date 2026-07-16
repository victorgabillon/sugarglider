"""FastAPI endpoint and public error mapping tests."""

from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from sugarglider.api.main import create_app
from sugarglider.domain.models import RouteRequest, RouteResult
from sugarglider.routing.graphhopper import (
    RoutingPointError,
    RoutingTimeoutError,
    RoutingUnavailableError,
    RoutingUpstreamError,
)
from sugarglider.routing.service import RouteService


class FakeRouteService(RouteService):
    def __init__(self, result: RouteResult) -> None:
        self.result = result
        self.is_ready = True
        self.error: Exception | None = None
        self.route_calls = 0

    async def route(self, request: RouteRequest) -> RouteResult:
        self.route_calls += 1
        if self.error is not None:
            raise self.error
        return self.result.model_copy(update={"name": request.name})

    async def ready(self) -> bool:
        if self.error is not None:
            raise self.error
        return self.is_ready


@pytest.fixture
def fake_service(route_result: RouteResult) -> FakeRouteService:
    return FakeRouteService(route_result)


@pytest.fixture
def app(fake_service: FakeRouteService) -> FastAPI:
    return create_app(fake_service)


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as http_client:
            yield http_client


def request_body() -> dict[str, object]:
    return {
        "name": "API route",
        "points": [{"lat": 48.87, "lon": 2.09}, {"lat": 48.88, "lon": 2.1}],
    }


@pytest.mark.asyncio
async def test_health_does_not_call_routing(
    client: httpx.AsyncClient, fake_service: FakeRouteService
) -> None:
    fake_service.error = RoutingUnavailableError()
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert fake_service.route_calls == 0


@pytest.mark.asyncio
async def test_ready_success(client: httpx.AsyncClient) -> None:
    response = await client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_ready_unavailable(
    client: httpx.AsyncClient, fake_service: FakeRouteService
) -> None:
    fake_service.is_ready = False
    response = await client.get("/ready")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "routing_unavailable"


@pytest.mark.asyncio
async def test_malformed_readiness_is_unavailable(
    client: httpx.AsyncClient, fake_service: FakeRouteService
) -> None:
    fake_service.error = RoutingUpstreamError()
    response = await client.get("/ready")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "routing_unavailable"


@pytest.mark.asyncio
async def test_json_route(client: httpx.AsyncClient) -> None:
    response = await client.post("/v1/routes", json=request_body())
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "API route"
    assert body["geometry"][0] == [2.096667, 48.871389]
    assert body["summary"]["distance_m"] == 2500.5
    assert body["analysis"]["route_distance_m"] == 2500.5
    assert body["analysis"]["unknown_surface"]["share"] == 1.0


@pytest.mark.asyncio
async def test_gpx_route(client: httpx.AsyncClient) -> None:
    response = await client.post("/v1/routes/gpx", json=request_body())
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/gpx+xml"
    assert response.headers["content-disposition"] == (
        'attachment; filename="API-route.gpx"'
    )
    assert b"<trk>" in response.content
    assert b"<rte>" not in response.content
    assert b"analysis" not in response.content


@pytest.mark.asyncio
async def test_validation_error_is_structured(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/v1/routes", json={"points": [{"lat": 100, "lon": 2}]}
    )
    assert response.status_code == 422
    assert response.json() == {
        "error": {"code": "invalid_request", "message": "The route request is invalid."}
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("exception", "status", "code"),
    [
        (RoutingPointError(), 400, "routing_point_not_found"),
        (RoutingUpstreamError(), 502, "routing_upstream_invalid"),
        (RoutingUnavailableError(), 503, "routing_unavailable"),
        (RoutingTimeoutError(), 504, "routing_timeout"),
    ],
)
async def test_application_errors_are_mapped(
    client: httpx.AsyncClient,
    fake_service: FakeRouteService,
    exception: Exception,
    status: int,
    code: str,
) -> None:
    fake_service.error = exception
    response = await client.post("/v1/routes", json=request_body())
    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    assert "Traceback" not in response.text
