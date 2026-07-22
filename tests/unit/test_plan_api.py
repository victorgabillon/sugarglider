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
from sugarglider.planning.direction.models import (
    ReversePlanRequest,
    ReversePlanResponse,
)
from sugarglider.planning.direction.service import ReverseRouteUnavailableError
from sugarglider.planning.direction.validation import ReverseSourceInvalidError
from sugarglider.planning.models import PlanRequest
from sugarglider.planning.pipeline import PlanService
from sugarglider.planning.profiles import (
    RoutingProfileCatalog,
    RoutingProfileId,
    routing_profile_catalog,
)
from sugarglider.planning.result import (
    PlanCandidate,
    PlanCandidateDiagnostics,
    PlanResult,
    PlanScore,
    PlanTraversal,
    PlanTraversalAnchor,
)
from sugarglider.planning.validation import ExactWaypointNotReachedError
from sugarglider.routing.errors import RoutingProfileUnavailableError
from sugarglider.routing.service import RouteService


class _RouteService(RouteService):
    def __init__(self) -> None:
        self.available = True

    async def ready(self) -> bool:
        return True

    async def ensure_profile_available(self, profile: RoutingProfileId) -> None:
        if not self.available:
            raise RoutingProfileUnavailableError(profile)

    async def profile_catalog(self) -> RoutingProfileCatalog:
        available = frozenset(
            {"hike", "trail_run", "bike", "gravel_bike", "mtb", "racingbike"}
            if self.available
            else set()
        )
        return routing_profile_catalog(available)


class _PlanService(PlanService):
    def __init__(self, result: PlanResult) -> None:
        self.result = result
        self.request: PlanRequest | None = None
        self.error: Exception | None = None
        self.reverse_request: ReversePlanRequest | None = None

    async def generate(self, request: PlanRequest) -> PlanResult:
        self.request = request
        if self.error is not None:
            raise self.error
        return self.result.model_copy(update={"kind": request.kind})

    async def reverse(self, request: ReversePlanRequest) -> ReversePlanResponse:
        self.reverse_request = request
        if self.error is not None:
            raise self.error
        return ReversePlanResponse(
            transformed_request=request.source_request,
            result=self.result.model_copy(update={"kind": request.source_request.kind}),
            source_candidate_id=request.candidate.id,
        )


@pytest.fixture
def plan_result(route_result: RouteResult) -> PlanResult:
    candidate = PlanCandidate(
        id="candidate-1",
        kind="waypoint_route",
        topology="point_to_point",
        routing_profile="hike",
        rank=1,
        roles=("harmonious", "distance_focused"),
        route=route_result,
        score=PlanScore(total=0, components={}),
        traversal=PlanTraversal(
            direction="start_to_end",
            anchors=(
                PlanTraversalAnchor(
                    id="endpoint/start",
                    name="Start",
                    kind="start",
                    routed_coordinate=Coordinate(
                        lat=route_result.geometry[0][1],
                        lon=route_result.geometry[0][0],
                    ),
                    semantic_coordinate=Coordinate(
                        lat=route_result.geometry[0][1],
                        lon=route_result.geometry[0][0],
                    ),
                    route_progress=0,
                    constraint_strength="exact",
                    outcome="reached",
                ),
                PlanTraversalAnchor(
                    id="endpoint/end",
                    name="End",
                    kind="end",
                    routed_coordinate=Coordinate(
                        lat=route_result.geometry[-1][1],
                        lon=route_result.geometry[-1][0],
                    ),
                    semantic_coordinate=Coordinate(
                        lat=route_result.geometry[-1][1],
                        lon=route_result.geometry[-1][0],
                    ),
                    route_progress=1,
                    constraint_strength="exact",
                    outcome="reached",
                ),
            ),
        ),
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
        routing_profile="hike",
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
def route_service() -> _RouteService:
    return _RouteService()


@pytest.fixture
def app(plan_service: _PlanService, route_service: _RouteService) -> FastAPI:
    return create_app(route_service, plan_service=plan_service)


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
        "waypoints": [
            {
                "id": "woodland-gate",
                "name": "Woodland gate",
                "coordinate": {"lat": 48.87, "lon": 2.11},
                "constraint_strength": "exact",
            }
        ],
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
async def test_reverse_endpoint_uses_strict_canonical_wrapper(
    client: httpx.AsyncClient,
    plan_service: _PlanService,
    plan_result: PlanResult,
) -> None:
    response = await client.post(
        "/v2/plans/reverse",
        json={
            "schema_version": 1,
            "source_request": waypoint_request(),
            "candidate": plan_result.candidates[0].model_dump(mode="json"),
        },
    )
    assert response.status_code == 200
    assert response.json()["source_candidate_id"] == "candidate-1"
    assert response.json()["transformed_request"]["routing_profile"] == "hike"
    assert plan_service.reverse_request is not None
    assert plan_service.reverse_request.candidate_count == 1


@pytest.mark.asyncio
async def test_reverse_endpoint_rejects_unknown_fields(
    client: httpx.AsyncClient, plan_result: PlanResult
) -> None:
    response = await client.post(
        "/v2/plans/reverse",
        json={
            "schema_version": 1,
            "source_request": waypoint_request(),
            "candidate": plan_result.candidates[0].model_dump(mode="json"),
            "candidate_count": 1,
            "reverse_geometry_locally": True,
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "code", "status_code"),
    (
        (
            ReverseSourceInvalidError("forged details"),
            "reverse_source_invalid",
            422,
        ),
        (
            ReverseRouteUnavailableError("upstream details"),
            "reverse_route_unavailable",
            503,
        ),
    ),
)
async def test_reverse_failures_use_safe_stable_public_errors(
    client: httpx.AsyncClient,
    plan_service: _PlanService,
    plan_result: PlanResult,
    error: Exception,
    code: str,
    status_code: int,
) -> None:
    plan_service.error = error
    response = await client.post(
        "/v2/plans/reverse",
        json={
            "schema_version": 1,
            "source_request": waypoint_request(),
            "candidate": plan_result.candidates[0].model_dump(mode="json"),
        },
    )
    assert response.status_code == status_code
    body = response.json()["error"]
    assert body["code"] == code
    assert "details" not in body
    assert "forged" not in body["message"]
    assert "upstream" not in body["message"]


@pytest.mark.asyncio
async def test_exact_waypoint_failure_has_safe_structured_public_fields(
    client: httpx.AsyncClient, plan_service: _PlanService
) -> None:
    plan_service.error = ExactWaypointNotReachedError(
        point_index=3,
        point_id="woodland-gate",
        point_name="Woodland gate",
        snap_distance_m=487.25,
        maximum_snap_distance_m=300,
        profile="mountain_bike",
    )
    response = await client.post("/v2/plans/generate", json=waypoint_request())
    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "exact_waypoint_not_reached",
            "message": (
                "An exact mandatory waypoint is too far from the selected routing "
                "network."
            ),
            "point_index": 3,
            "point_id": "woodland-gate",
            "point_name": "Woodland gate",
            "snap_distance_m": 487.25,
            "maximum_snap_distance_m": 300.0,
            "profile": "mountain_bike",
            "suggestion": (
                "Move or remove the exact waypoint, or explicitly convert it to "
                "best effort."
            ),
        }
    }


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


@pytest.mark.asyncio
async def test_profile_catalog_and_unavailable_profile_error(
    client: httpx.AsyncClient, route_service: _RouteService
) -> None:
    catalog = (await client.get("/v2/routing-profiles")).json()
    assert [value["profile"]["id"] for value in catalog["profiles"]] == [
        "trail_run",
        "hike",
        "city_bike",
        "gravel_bike",
        "mountain_bike",
        "road_bike",
    ]
    route_service.available = False
    response = await client.post("/v2/plans/generate", json=waypoint_request())
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "routing_profile_unavailable"
