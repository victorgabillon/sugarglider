"""FastAPI endpoint and public error mapping tests."""

from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from sugarglider.api.main import create_app
from sugarglider.domain.generation import (
    RouteGenerationRequest,
    RouteGenerationResult,
)
from sugarglider.domain.models import RouteRequest, RouteResult
from sugarglider.generation.service import RouteGenerationService
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


class FakeGenerationService(RouteGenerationService):
    def __init__(self, result: RouteGenerationResult) -> None:
        self.result = result
        self.last_request: RouteGenerationRequest | None = None

    async def generate(self, request: RouteGenerationRequest) -> RouteGenerationResult:
        self.last_request = request
        return self.result


@pytest.fixture
def fake_service(route_result: RouteResult) -> FakeRouteService:
    return FakeRouteService(route_result)


@pytest.fixture
def fake_generation_service(
    generation_result: RouteGenerationResult,
) -> FakeGenerationService:
    return FakeGenerationService(generation_result)


@pytest.fixture
def app(
    fake_service: FakeRouteService,
    fake_generation_service: FakeGenerationService,
) -> FastAPI:
    return create_app(fake_service, fake_generation_service)


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


def generation_request_body() -> dict[str, object]:
    return {
        "name": "Generated API route",
        "points": [{"lat": 48.87, "lon": 2.09}, {"lat": 48.88, "lon": 2.1}],
        "target_distance_m": 3_000,
        "tolerance_m": 500,
        "candidate_count": 1,
        "seed": 42,
        "close_loop": True,
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
async def test_successful_generation_json(client: httpx.AsyncClient) -> None:
    response = await client.post("/v1/routes/generate", json=generation_request_body())
    assert response.status_code == 200
    body = response.json()
    assert body["baseline"]["summary"]["distance_m"] == 2500.5
    assert len(body["candidates"]) == 1
    assert body["search"]["status"] == "within_tolerance"
    assert body["candidates"][0]["construction"] == "alternative_leg_beam"
    assert len(body["candidates"][0]["routing_points"]) == 2
    assert body["search"]["alternative_leg_request_count"] == 0
    assert body["search"]["low_overlap_requested"] is False
    assert body["search"]["pre_low_overlap_repeated_share"] is None
    assert body["search"]["best_low_overlap_repeated_share"] is None
    assert [
        visit["original_index"]
        for visit in body["candidates"][0]["required_point_order"]
    ] == [0, 1]


@pytest.mark.asyncio
async def test_generation_request_defaults_to_fixed_order(
    client: httpx.AsyncClient,
    fake_generation_service: FakeGenerationService,
) -> None:
    response = await client.post("/v1/routes/generate", json=generation_request_body())
    assert response.status_code == 200
    assert fake_generation_service.last_request is not None
    assert fake_generation_service.last_request.point_order_mode == "fixed"
    assert fake_generation_service.last_request.nature_preference == "off"
    assert fake_generation_service.last_request.loop_geometry_preference == "off"


@pytest.mark.asyncio
async def test_generation_request_accepts_nature_preference(
    client: httpx.AsyncClient,
    fake_generation_service: FakeGenerationService,
) -> None:
    body = generation_request_body()
    body["nature_preference"] = "prefer"
    response = await client.post("/v1/routes/generate", json=body)
    assert response.status_code == 200
    assert fake_generation_service.last_request is not None
    assert fake_generation_service.last_request.nature_preference == "prefer"


@pytest.mark.asyncio
async def test_invalid_nature_preference_is_structured_validation(
    client: httpx.AsyncClient,
) -> None:
    body = generation_request_body()
    body["nature_preference"] = "scenic"
    response = await client.post("/v1/routes/generate", json=body)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"


@pytest.mark.asyncio
async def test_generation_request_accepts_loop_geometry_preference(
    client: httpx.AsyncClient,
    fake_generation_service: FakeGenerationService,
) -> None:
    body = generation_request_body()
    body["loop_geometry_preference"] = "prefer"
    response = await client.post("/v1/routes/generate", json=body)
    assert response.status_code == 200
    assert fake_generation_service.last_request is not None
    assert fake_generation_service.last_request.loop_geometry_preference == "prefer"


@pytest.mark.asyncio
async def test_invalid_loop_geometry_preference_is_structured_validation(
    client: httpx.AsyncClient,
) -> None:
    body = generation_request_body()
    body["loop_geometry_preference"] = "beautiful"
    response = await client.post("/v1/routes/generate", json=body)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"


@pytest.mark.asyncio
async def test_generation_request_accepts_optimized_loop_order(
    client: httpx.AsyncClient,
    fake_generation_service: FakeGenerationService,
) -> None:
    body = generation_request_body()
    body["point_order_mode"] = "optimize_loop"
    response = await client.post("/v1/routes/generate", json=body)
    assert response.status_code == 200
    assert fake_generation_service.last_request is not None
    assert fake_generation_service.last_request.point_order_mode == "optimize_loop"


@pytest.mark.asyncio
async def test_invalid_generation_order_mode_is_structured_validation(
    client: httpx.AsyncClient,
) -> None:
    body = generation_request_body()
    body["point_order_mode"] = "fastest"
    response = await client.post("/v1/routes/generate", json=body)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"


@pytest.mark.asyncio
async def test_generation_request_accepts_low_overlap_mode(
    client: httpx.AsyncClient,
    fake_generation_service: FakeGenerationService,
) -> None:
    body = generation_request_body()
    body["path_selection_mode"] = "low_overlap"
    response = await client.post("/v1/routes/generate", json=body)
    assert response.status_code == 200
    assert fake_generation_service.last_request is not None
    assert fake_generation_service.last_request.path_selection_mode == "low_overlap"


@pytest.mark.asyncio
async def test_invalid_path_selection_mode_is_structured_validation(
    client: httpx.AsyncClient,
) -> None:
    body = generation_request_body()
    body["path_selection_mode"] = "magic"
    response = await client.post("/v1/routes/generate", json=body)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"


@pytest.mark.asyncio
async def test_successful_generation_gpx_is_track_only(
    client: httpx.AsyncClient,
) -> None:
    response = await client.post(
        "/v1/routes/generate/gpx", json=generation_request_body()
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/gpx+xml"
    assert b"<trk>" in response.content
    assert b"<rte>" not in response.content
    assert b"analysis" not in response.content


@pytest.mark.asyncio
async def test_infeasible_generation_json_returns_baseline(
    client: httpx.AsyncClient,
    fake_generation_service: FakeGenerationService,
) -> None:
    fake_generation_service.result = fake_generation_service.result.model_copy(
        update={
            "candidates": (),
            "search": fake_generation_service.result.search.model_copy(
                update={"status": "infeasible"}
            ),
        }
    )
    response = await client.post("/v1/routes/generate", json=generation_request_body())
    assert response.status_code == 200
    assert response.json()["search"]["status"] == "infeasible"
    assert response.json()["candidates"] == []


@pytest.mark.asyncio
async def test_infeasible_generation_gpx_is_structured_422(
    client: httpx.AsyncClient,
    fake_generation_service: FakeGenerationService,
) -> None:
    fake_generation_service.result = fake_generation_service.result.model_copy(
        update={
            "candidates": (),
            "search": fake_generation_service.result.search.model_copy(
                update={"status": "infeasible"}
            ),
        }
    )
    response = await client.post(
        "/v1/routes/generate/gpx", json=generation_request_body()
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "target_distance_infeasible"


@pytest.mark.asyncio
async def test_no_candidate_generation_gpx_is_structured_422(
    client: httpx.AsyncClient,
    fake_generation_service: FakeGenerationService,
) -> None:
    fake_generation_service.result = fake_generation_service.result.model_copy(
        update={
            "candidates": (),
            "search": fake_generation_service.result.search.model_copy(
                update={"status": "best_effort"}
            ),
        }
    )
    response = await client.post(
        "/v1/routes/generate/gpx", json=generation_request_body()
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "route_generation_no_candidate"


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


@pytest.mark.asyncio
async def test_endpoint_validation_errors_use_stable_safe_codes(
    client: httpx.AsyncClient,
) -> None:
    response = await client.post(
        "/v1/routes/generate",
        json={
            "start": {"lat": 48.85, "lon": 2.36},
            "points": [],
            "route_topology": "point_to_point",
            "target_distance_m": 10_000,
        },
    )
    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "endpoint_end_unresolved",
            "message": "A hard end could not be resolved.",
        }
    }
    assert "traceback" not in response.text.lower()
    assert "graphhopper" not in response.text.lower()
