"""Static application, UI configuration, and no-reroute export tests."""

import re
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from sugarglider.api.main import create_app
from sugarglider.config import Settings
from sugarglider.domain.generation import RouteGenerationRequest, RouteGenerationResult
from sugarglider.domain.models import RouteRequest, RouteResult
from sugarglider.generation.service import RouteGenerationService
from sugarglider.routing.service import RouteService
from sugarglider.web.routes import STATIC_DIRECTORY


class _FakeRouteService(RouteService):
    def __init__(self, result: RouteResult) -> None:
        self.result = result
        self.route_calls = 0

    async def route(self, request: RouteRequest) -> RouteResult:
        self.route_calls += 1
        return self.result.model_copy(update={"name": request.name})

    async def ready(self) -> bool:
        return True


class _FakeGenerationService(RouteGenerationService):
    def __init__(self, result: RouteGenerationResult) -> None:
        self.result = result
        self.last_request: RouteGenerationRequest | None = None

    async def generate(self, request: RouteGenerationRequest) -> RouteGenerationResult:
        self.last_request = request
        return self.result


@pytest.fixture
def fake_service(route_result: RouteResult) -> _FakeRouteService:
    return _FakeRouteService(route_result)


@pytest.fixture
def fake_generation_service(
    generation_result: RouteGenerationResult,
) -> _FakeGenerationService:
    return _FakeGenerationService(generation_result)


@pytest.fixture
def app(
    fake_service: _FakeRouteService,
    fake_generation_service: _FakeGenerationService,
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


@pytest.mark.asyncio
async def test_application_and_static_assets_are_served(
    client: httpx.AsyncClient,
) -> None:
    index = await client.get("/")
    css = await client.get("/static/styles.css")
    javascript = await client.get("/static/app.js")
    missing = await client.get("/static/missing.js")
    assert index.status_code == css.status_code == javascript.status_code == 200
    assert index.headers["content-type"].startswith("text/html")
    assert "<main" in index.text and "<nav" in index.text and "<footer" in index.text
    assert "maplibre-gl@4.7.1" in index.text
    assert "latest" not in index.text.lower()
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_every_referenced_local_module_exists(client: httpx.AsyncClient) -> None:
    index = (await client.get("/")).text
    references = re.findall(r'(?:src|href)="(/static/[^"]+)"', index)
    for javascript_path in STATIC_DIRECTORY.rglob("*.js"):
        javascript = javascript_path.read_text(encoding="utf-8")
        relative_parent = javascript_path.relative_to(STATIC_DIRECTORY).parent
        references.extend(
            f"/static/{relative_parent / module}"
            for module in re.findall(r'(?:from|import)\s+"\./([^"]+)"', javascript)
        )
    for reference in references:
        response = await client.get(reference)
        assert response.status_code == 200, reference


@pytest.mark.asyncio
async def test_static_paths_do_not_depend_on_current_working_directory(
    fake_service: _FakeRouteService,
    fake_generation_service: _FakeGenerationService,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    independent_app = create_app(fake_service, fake_generation_service)
    async with independent_app.router.lifespan_context(independent_app):
        transport = httpx.ASGITransport(app=independent_app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as independent_client:
            assert (await independent_client.get("/")).status_code == 200
            assert (
                await independent_client.get("/static/styles.css")
            ).status_code == 200


@pytest.mark.asyncio
async def test_ui_config_uses_injected_map_settings(
    fake_service: _FakeRouteService,
    fake_generation_service: _FakeGenerationService,
) -> None:
    settings = Settings(
        map_tile_url="https://tiles.example/{z}/{x}/{y}.png",
        map_attribution="Required map credit",
        map_initial_lat=49.1,
        map_initial_lon=2.4,
        map_initial_zoom=9.5,
    )
    app = create_app(fake_service, fake_generation_service, settings=settings)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as config_client:
            response = await config_client.get("/v1/ui/config")
    assert response.json() == {
        "tile_url_template": "https://tiles.example/{z}/{x}/{y}.png",
        "tile_attribution": "Required map credit",
        "initial_center": [2.4, 49.1],
        "initial_zoom": 9.5,
        "max_required_points": 30,
    }


@pytest.mark.asyncio
async def test_single_injected_settings_instance_wires_pr5_and_pr6() -> None:
    settings = Settings(
        low_overlap_max_paths=5,
        low_overlap_max_weight_factor=2.2,
        low_overlap_max_share_factor=0.3,
        low_overlap_beam_width=17,
        low_overlap_max_leg_requests=31,
        low_overlap_source_count=3,
        map_initial_zoom=8.0,
    )
    app = create_app(settings=settings)
    async with app.router.lifespan_context(app):
        service: RouteGenerationService = app.state.generation_service
        configured = service._low_overlap_settings
        assert configured.max_paths == 5
        assert configured.max_weight_factor == 2.2
        assert configured.max_share_factor == 0.3
        assert configured.beam_width == 17
        assert configured.max_leg_requests == 31
        assert configured.source_count == 3
        assert app.state.ui_config.initial_zoom == 8.0


@pytest.mark.asyncio
async def test_result_gpx_export_never_calls_services(
    client: httpx.AsyncClient,
    route_result: RouteResult,
    fake_service: _FakeRouteService,
    fake_generation_service: _FakeGenerationService,
) -> None:
    response = await client.post(
        "/v1/routes/gpx/from-result",
        json=route_result.model_dump(mode="json"),
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/gpx+xml"
    assert response.content.count(b"<trk>") == 1
    assert response.content.count(b"<trkseg>") == 1
    assert b'lat="48.87138900" lon="2.09666700"' in response.content
    assert fake_service.route_calls == 0
    assert fake_generation_service.last_request is None


@pytest.mark.asyncio
async def test_malformed_result_export_is_structured(client: httpx.AsyncClient) -> None:
    response = await client.post("/v1/routes/gpx/from-result", json={"name": "bad"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"


@pytest.mark.asyncio
async def test_visualization_endpoint_returns_typed_geojson(
    client: httpx.AsyncClient, route_result: RouteResult
) -> None:
    response = await client.post(
        "/v1/routes/visualization", json=route_result.model_dump(mode="json")
    )
    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "FeatureCollection"
    assert body["features"][0]["geometry"]["type"] == "LineString"
    assert body["features"][0]["geometry"]["coordinates"][0] == [
        2.096667,
        48.871389,
    ]
    assert body["features"][0]["properties"]["kind"] == "normal"
    assert body["features"][0]["properties"]["edge_id"] is None


@pytest.mark.asyncio
async def test_semantically_malformed_visualization_is_structured(
    client: httpx.AsyncClient, route_result: RouteResult
) -> None:
    body = route_result.model_dump(mode="json")
    body["path_details"] = {"edge_id": [{"from_index": 0, "to_index": 999, "value": 1}]}
    response = await client.post("/v1/routes/visualization", json=body)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "route_visualization_invalid"


def test_packaged_static_directory_contains_application() -> None:
    assert (STATIC_DIRECTORY / "index.html").is_file()
    assert (STATIC_DIRECTORY / "styles.css").is_file()
    assert (STATIC_DIRECTORY / "app.js").is_file()
