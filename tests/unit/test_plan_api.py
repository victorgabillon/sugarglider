"""Canonical planning endpoints and deliberate legacy removal."""

from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from sugarglider.api.main import create_app
from sugarglider.domain.models import Coordinate, RouteResult
from sugarglider.planning.diagnostics import (
    BudgetDiagnostics,
    CacheDiagnostics,
    PlanSearchDiagnostics,
)
from sugarglider.planning.models import PlanRequest
from sugarglider.planning.pipeline import PlanService
from sugarglider.planning.result import (
    PlanCandidate,
    PlanCandidateDiagnostics,
    PlanResult,
    PlanScore,
)
from sugarglider.routing.service import RouteService


class _RouteService(RouteService):
    def __init__(self) -> None:
        pass

    async def ready(self) -> bool:
        return True


class _PlanService(PlanService):
    def __init__(self, result: PlanResult) -> None:
        self.result = result
        self.request: PlanRequest | None = None

    async def generate(self, request: PlanRequest) -> PlanResult:
        self.request = request
        return self.result.model_copy(update={"kind": request.kind})


@pytest.fixture
def plan_result(route_result: RouteResult) -> PlanResult:
    candidate = PlanCandidate(
        id="candidate-1",
        rank=1,
        roles=("harmonious", "distance_focused"),
        route=route_result,
        score=PlanScore(total=0, components={}),
        diagnostics=PlanCandidateDiagnostics(
            safety_eligible=True,
            target_error_m=499.5,
            within_tolerance=True,
            requested_stop_count=0,
            immediate_backtracking_m=0,
            repeated_distance_m=0,
        ),
    )
    return PlanResult(
        kind="waypoint_route",
        topology="point_to_point",
        effective_start=Coordinate(lat=48.871389, lon=2.096667),
        effective_end=Coordinate(lat=48.871454, lon=2.124421),
        candidates=(candidate,),
        search_diagnostics=PlanSearchDiagnostics(
            budget=BudgetDiagnostics(
                phases={},
                total_used=0,
                total_limit=1,
                total_remaining=1,
                global_exhausted=False,
            ),
            cache=CacheDiagnostics(
                lookup_count=0,
                hit_count=0,
                miss_count=0,
                entry_count=0,
                successful_entry_count=0,
                failed_entry_count=0,
                backend_call_count=0,
            ),
        ),
    )


@pytest.fixture
def plan_service(plan_result: PlanResult) -> _PlanService:
    return _PlanService(plan_result)


@pytest.fixture
def app(plan_service: _PlanService) -> FastAPI:
    return create_app(_RouteService(), plan_service=plan_service)


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as http_client:
            yield http_client


def waypoint_request() -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "waypoint_route",
        "name": "Canonical route",
        "topology": "point_to_point",
        "start": {"lat": 48.871389, "lon": 2.096667},
        "end": {"lat": 48.871454, "lon": 2.124421},
        "routing_profile": "hike",
        "candidate_count": 1,
        "seed": 42,
        "distance_objective": {
            "target_m": 3_000,
            "tolerance_m": 500,
            "maximum_m": None,
            "priority": "flexible",
        },
        "preferences": {
            "nature": "off",
            "loop_geometry": "off",
            "path_selection": "shortest",
        },
        "waypoints": [{"lat": 48.87, "lon": 2.11}],
        "waypoint_order": "fixed",
    }


@pytest.mark.asyncio
async def test_generate_uses_discriminated_canonical_request(
    client: httpx.AsyncClient, plan_service: _PlanService
) -> None:
    response = await client.post("/v2/plans/generate", json=waypoint_request())
    assert response.status_code == 200
    assert response.json()["schema_version"] == 1
    assert response.json()["candidates"][0]["id"] == "candidate-1"
    assert plan_service.request is not None
    assert plan_service.request.kind == "waypoint_route"


@pytest.mark.asyncio
async def test_generate_accepts_direct_point_to_point_route(
    client: httpx.AsyncClient, plan_service: _PlanService
) -> None:
    request = waypoint_request()
    request["waypoints"] = []
    response = await client.post("/v2/plans/generate", json=request)
    assert response.status_code == 200
    assert plan_service.request is not None
    assert plan_service.request.kind == "waypoint_route"
    assert plan_service.request.waypoints == ()


@pytest.mark.asyncio
async def test_obsolete_field_is_rejected(client: httpx.AsyncClient) -> None:
    request = waypoint_request()
    request["closed"] = False
    response = await client.post("/v2/plans/generate", json=request)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"


@pytest.mark.asyncio
async def test_previous_public_endpoints_are_gone(client: httpx.AsyncClient) -> None:
    for path in (
        "/v1/routes",
        "/v1/routes/generate",
        "/v1/routes/generate/gpx",
        "/v1/tours/generate",
        "/v1/tours/gpx/from-candidate",
    ):
        assert (await client.post(path, json={})).status_code == 404


@pytest.mark.asyncio
async def test_gpx_serializes_returned_candidate_without_planning(
    client: httpx.AsyncClient, plan_result: PlanResult, plan_service: _PlanService
) -> None:
    response = await client.post(
        "/v2/plans/gpx",
        json={
            "schema_version": 1,
            "candidate": plan_result.candidates[0].model_dump(mode="json"),
        },
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/gpx+xml"
    assert b"<trk>" in response.content and b"<rte>" not in response.content
    assert plan_service.request is None


@pytest.mark.asyncio
async def test_health_and_ready_remain_separate(client: httpx.AsyncClient) -> None:
    assert (await client.get("/health")).json() == {"status": "ok"}
    assert (await client.get("/ready")).json() == {"status": "ok"}
