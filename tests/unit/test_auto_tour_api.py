"""Separate Auto Tour request, endpoint, response, and export tests."""

from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from sugarglider.api.main import create_app
from sugarglider.domain.generation import RouteGenerationRequest, RouteGenerationResult
from sugarglider.domain.models import RouteRequest, RouteResult
from sugarglider.generation.scoring import score_route
from sugarglider.generation.service import RouteGenerationService
from sugarglider.generation.signatures import candidate_signature
from sugarglider.routing.service import RouteService
from sugarglider.tours.models import (
    AutoTourCandidate,
    AutoTourRequest,
    AutoTourResult,
    AutoTourSearchSummary,
    AutoTourTimings,
)
from sugarglider.tours.scoring import control_comparison
from sugarglider.tours.service import AutoTourService


class _FakeAutoTourService(AutoTourService):
    def __init__(self, result: AutoTourResult) -> None:
        self.result = result
        self.requests: list[AutoTourRequest] = []

    async def generate(self, request: AutoTourRequest) -> AutoTourResult:
        self.requests.append(request)
        return self.result


class _RouteService(RouteService):
    def __init__(self, result: RouteResult) -> None:
        self.result = result

    async def route(self, request: RouteRequest) -> RouteResult:
        return self.result.model_copy(update={"name": request.name})

    async def ready(self) -> bool:
        return True


class _GenerationService(RouteGenerationService):
    def __init__(self, result: RouteGenerationResult) -> None:
        self.result = result

    async def generate(self, request: RouteGenerationRequest) -> RouteGenerationResult:
        return self.result


def _result(route: RouteResult) -> AutoTourResult:
    signature = candidate_signature(route)
    candidate = AutoTourCandidate(
        rank=1,
        route=route,
        signature=signature,
        construction="graphhopper_round_trip",
        direction="clockwise",
        skeleton_id="round-trip-h90",
        skeleton_method="graphhopper_round_trip",
        routing_points=(),
        snapped_routing_points=route.snapped_points,
        hard_point_visits=(),
        poi_visits=(),
        target_error_m=0,
        within_tolerance=True,
        control_eligible=True,
        control_comparison=control_comparison(route, signature),
        total_poi_reward=0,
        inserted_poi_reward=0,
        selected_scenic_count=0,
        selected_verified_water_count=0,
        route_score=score_route(route, route.summary.distance_m),
    )
    timings = AutoTourTimings(
        isochrone_seconds=0,
        skeleton_construction_seconds=0,
        route_call_seconds=0,
        poi_corridor_query_seconds=0,
        poi_insertion_search_seconds=0,
        local_repair_seconds=0,
        total_seconds=0,
    )
    search = AutoTourSearchSummary(
        isochrone_request_count=1,
        round_trip_control_request_count=1,
        skeleton_route_request_count=0,
        skeleton_candidate_count=1,
        retained_skeleton_count=1,
        poi_index_candidate_count=0,
        already_collected_poi_count=0,
        poi_route_evaluation_count=0,
        local_repair_evaluation_count=0,
        alternative_leg_request_count=0,
        total_route_request_budget=92,
        total_route_request_count=1,
        budget_exhausted=False,
        control_signature=signature,
        recommended_signature=signature,
        control_retained=True,
        selected_scenic_count=0,
        selected_verified_water_count=0,
        timings=timings,
        warnings=("auto_tour_poi_index_unavailable",),
    )
    return AutoTourResult(control=candidate, candidates=(candidate,), search=search)


@pytest.fixture
def fake_auto_tour_service(route_result: RouteResult) -> _FakeAutoTourService:
    return _FakeAutoTourService(_result(route_result))


@pytest.fixture
def auto_tour_app(
    route_result: RouteResult,
    generation_result: RouteGenerationResult,
    fake_auto_tour_service: _FakeAutoTourService,
) -> FastAPI:
    return create_app(
        _RouteService(route_result),
        _GenerationService(generation_result),
        auto_tour_service=fake_auto_tour_service,
    )


@pytest_asyncio.fixture
async def auto_tour_client(auto_tour_app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with auto_tour_app.router.lifespan_context(auto_tour_app):
        transport = httpx.ASGITransport(app=auto_tour_app, raise_app_exceptions=False)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            yield client


@pytest.mark.asyncio
async def test_auto_tour_endpoint_uses_independent_defaults_and_accounting(
    auto_tour_client: httpx.AsyncClient,
    fake_auto_tour_service: _FakeAutoTourService,
) -> None:
    response = await auto_tour_client.post(
        "/v1/tours/generate",
        json={
            "name": "Soft tour",
            "start": {"lat": 48.87, "lon": 2.09},
            "target_distance_m": 41_000,
        },
    )
    assert response.status_code == 200
    request = fake_auto_tour_service.requests[0]
    assert request.direction_preference == "any"
    assert request.distance_priority == "flexible"
    assert request.scenic_preference == "prefer"
    assert request.drinking_water_preference == "prefer"
    assert request.nature_preference == "prefer"
    assert request.loop_geometry_preference == "prefer"
    assert request.path_selection_mode == "low_overlap"
    body = response.json()
    assert body["search"]["control_retained"] is True
    assert body["search"]["warnings"] == ["auto_tour_poi_index_unavailable"]
    assert body["control"]["signature"] == body["candidates"][0]["signature"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "update",
    [
        {"direction_preference": "north"},
        {"scenic_preference": "required"},
        {
            "hard_points": [
                {"lat": 48.8 + index / 100, "lon": 2.0} for index in range(7)
            ]
        },
        {"preferred_poi_ids": [f"node/{index}" for index in range(9)]},
        {
            "requested_places": [
                {
                    "name": f"Place {index}",
                    "coordinate": {"lat": 48.8, "lon": 2.0 + index / 1_000},
                }
                for index in range(31)
            ]
        },
    ],
)
async def test_auto_tour_request_limits_are_structured(
    auto_tour_client: httpx.AsyncClient, update: dict[str, object]
) -> None:
    payload: dict[str, object] = {
        "start": {"lat": 48.87, "lon": 2.09},
        "target_distance_m": 41_000,
    }
    payload.update(update)
    response = await auto_tour_client.post("/v1/tours/generate", json=payload)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"


@pytest.mark.asyncio
async def test_requested_close_enough_place_is_preserved_by_api(
    auto_tour_client: httpx.AsyncClient,
    fake_auto_tour_service: _FakeAutoTourService,
) -> None:
    response = await auto_tour_client.post(
        "/v1/tours/generate",
        json={
            "start": {"lat": 48.87, "lon": 2.09},
            "target_distance_m": 41_000,
            "distance_priority": "balanced",
            "requested_places": [
                {
                    "name": "Château de Monte-Cristo",
                    "coordinate": {"lat": 48.88, "lon": 2.10},
                    "visit_radius_m": 200,
                    "importance": "must_visit",
                    "original_index": 7,
                }
            ],
        },
    )
    assert response.status_code == 200
    request = fake_auto_tour_service.requests[-1]
    assert request.distance_priority == "balanced"
    assert request.requested_places[0].name == "Château de Monte-Cristo"
    assert request.requested_places[0].visit_radius_m == 200
    assert request.requested_places[0].original_index == 7


@pytest.mark.asyncio
async def test_selected_result_gpx_export_does_not_generate_again(
    auto_tour_client: httpx.AsyncClient,
    fake_auto_tour_service: _FakeAutoTourService,
) -> None:
    route = fake_auto_tour_service.result.candidates[0].route
    response = await auto_tour_client.post(
        "/v1/routes/gpx/from-result",
        json=route.model_dump(mode="json"),
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/gpx+xml")
    assert fake_auto_tour_service.requests == []
