"""Opt-in canonical planning tests against local GraphHopper 11."""

import json
import os
from pathlib import Path
from xml.etree import ElementTree

import httpx
import pytest

from sugarglider.analysis.route import RouteAnalyzer, haversine_distance_m
from sugarglider.domain.models import Coordinate, RouteRequest
from sugarglider.gpx.writer import GPX_NAMESPACE, write_plan_gpx
from sugarglider.planning.auto_tour.service import AutoTourPlanner, AutoTourService
from sugarglider.planning.models import (
    PLAN_REQUEST_ADAPTER,
    AutoTourPlanRequest,
    WaypointPlanRequest,
)
from sugarglider.planning.waypoint.service import WaypointPlanner
from sugarglider.pois.index import load_poi_index
from sugarglider.routing.graphhopper import GraphHopperClient
from sugarglider.routing.result import RouteResultFactory
from sugarglider.routing.service import RouteService

pytestmark = pytest.mark.integration


def _enabled() -> None:
    if os.getenv("RUN_GRAPHHOPPER_INTEGRATION") != "1":
        pytest.skip("set RUN_GRAPHHOPPER_INTEGRATION=1 to use live GraphHopper")


def _load(path: str) -> AutoTourPlanRequest | WaypointPlanRequest:
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    return PLAN_REQUEST_ADAPTER.validate_python(document)


@pytest.mark.asyncio
async def test_live_routing_adapter_preserves_graphhopper_geometry() -> None:
    _enabled()
    base_url = os.getenv("GRAPHHOPPER_URL", "http://localhost:8989")
    async with httpx.AsyncClient() as client:
        result = await RouteService(GraphHopperClient(base_url, client=client)).route(
            RouteRequest(
                name="Adapter integration",
                points=[
                    Coordinate(lat=48.871389, lon=2.096667),
                    Coordinate(lat=48.871454, lon=2.124421),
                    Coordinate(lat=48.86156, lon=2.10833),
                ],
            )
        )
    assert result.summary.distance_m > 0
    assert len(result.geometry) > 3
    assert result.analysis.route_distance_m == pytest.approx(result.summary.distance_m)
    assert result.analysis.repetition.edge_id_coverage.share > 0.8


@pytest.mark.asyncio
async def test_live_canonical_waypoint_loop() -> None:
    _enabled()
    request = _load("examples/marly/generation-request.json")
    assert isinstance(request, WaypointPlanRequest)
    base_url = os.getenv("GRAPHHOPPER_URL", "http://localhost:8989")
    async with httpx.AsyncClient(timeout=240) as client:
        result = await WaypointPlanner(
            GraphHopperClient(base_url, client=client),
            RouteResultFactory(),
            max_evaluations=48,
        ).generate(request)
    assert result.kind == "waypoint_route"
    assert result.topology == "loop"
    assert result.effective_start == result.effective_end == request.start
    assert result.candidates
    best = result.candidates[0]
    assert best.route.geometry[0] == best.route.geometry[-1] or (
        haversine_distance_m(best.route.geometry[0], best.route.geometry[-1]) < 300
    )
    assert best.diagnostics.safety_eligible
    assert "distance_focused" in {
        role for candidate in result.candidates for role in candidate.roles
    }
    assert result.search_diagnostics.budget.total_used <= (
        result.search_diagnostics.budget.total_limit
    )


@pytest.mark.asyncio
async def test_live_canonical_waypoint_point_to_point_keeps_endpoints() -> None:
    _enabled()
    document = json.loads(
        Path("examples/marly/generation-request.json").read_text(encoding="utf-8")
    )
    document.update(
        {
            "name": "Bastille to Marly waypoint route",
            "topology": "point_to_point",
            "start": {"lat": 48.853, "lon": 2.369},
            "end": {"lat": 48.871389, "lon": 2.096667},
            "waypoints": [{"lat": 48.862849, "lon": 2.099448}],
            "waypoint_order": "optimize",
        }
    )
    document["distance_objective"]["target_m"] = 26_000
    request = PLAN_REQUEST_ADAPTER.validate_python(document)
    assert isinstance(request, WaypointPlanRequest)
    base_url = os.getenv("GRAPHHOPPER_URL", "http://localhost:8989")
    async with httpx.AsyncClient(timeout=240) as client:
        result = await WaypointPlanner(
            GraphHopperClient(base_url, client=client), RouteResultFactory()
        ).generate(request)
    best = result.candidates[0]
    assert best.route.geometry[0] != best.route.geometry[-1]
    assert (
        haversine_distance_m(
            best.route.geometry[0], (request.start.lon, request.start.lat)
        )
        < 300
    )
    assert (
        haversine_distance_m(
            best.route.geometry[-1],
            (request.effective_end.lon, request.effective_end.lat),
        )
        < 300
    )


@pytest.mark.asyncio
async def test_live_bastille_to_marly_accounts_for_22_requested_stops() -> None:
    _enabled()
    request = _load("examples/marly/bastille-to-marly-22-places-auto-tour.json")
    assert isinstance(request, AutoTourPlanRequest)
    assert len(request.requested_stops) == 22
    base_url = os.getenv("GRAPHHOPPER_URL", "http://localhost:8989")
    poi_index = load_poi_index(Path("data/pois/ile-de-france-poi-index.json.gz"))
    async with httpx.AsyncClient(timeout=300) as client:
        backend = GraphHopperClient(base_url, client=client)
        result = await AutoTourPlanner(
            AutoTourService(
                backend,
                RouteResultFactory(RouteAnalyzer()),
                poi_index=poi_index,
                structural_result_factory=RouteResultFactory(RouteAnalyzer()),
            )
        ).generate(request)
    best = result.candidates[0]
    requested_decisions = {
        stop.id for stop in best.selected_stops if stop.selection_origin == "requested"
    } | {stop.id for stop in best.dropped_stops if stop.selection_origin == "requested"}
    assert requested_decisions == {stop.id for stop in request.requested_stops}
    assert best.route.geometry[0] != best.route.geometry[-1]
    assert 20_000 <= best.route.summary.distance_m <= 50_000
    # The accepted local PR14 graph snapshot is 2,761.1 m / 48,696.2 m.
    assert best.route.analysis.immediate_backtrack.share <= 0.06
    assert best.route.analysis.repetition.repeated_distance.share <= 0.06
    assert all(
        stop.route_to_approach_m <= stop.resolved_approach.arrival_tolerance_m
        for stop in best.selected_stops
    )
    root = ElementTree.fromstring(write_plan_gpx(best))
    namespace = {"g": GPX_NAMESPACE}
    assert len(root.findall("g:wpt", namespace)) == len(best.selected_stops)
    assert len(root.findall("g:trk", namespace)) == 1
    assert len(root.findall("g:trk/g:trkseg", namespace)) == 1
    assert root.findall("g:rte", namespace) == []


@pytest.mark.asyncio
async def test_live_marly_auto_tour_is_deterministic() -> None:
    _enabled()
    request = _load("examples/marly/auto-tour-request.json")
    assert isinstance(request, AutoTourPlanRequest)
    base_url = os.getenv("GRAPHHOPPER_URL", "http://localhost:8989")
    poi_index = load_poi_index(Path("data/pois/ile-de-france-poi-index.json.gz"))

    async def generate() -> tuple[str, ...]:
        async with httpx.AsyncClient(timeout=300) as client:
            result = await AutoTourPlanner(
                AutoTourService(
                    GraphHopperClient(base_url, client=client),
                    RouteResultFactory(RouteAnalyzer()),
                    poi_index=poi_index,
                    structural_result_factory=RouteResultFactory(RouteAnalyzer()),
                )
            ).generate(request)
        best = result.candidates[0]
        requested_selected = sum(
            stop.selection_origin == "requested" for stop in best.selected_stops
        )
        assert requested_selected >= 1
        assert 30_000 <= best.route.summary.distance_m <= 50_000
        assert best.route.analysis.immediate_backtrack.share <= 0.05
        assert best.route.analysis.repetition.repeated_distance.share <= 0.05
        return tuple(candidate.id for candidate in result.candidates)

    assert await generate() == await generate()
