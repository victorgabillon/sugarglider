"""Static application, UI configuration, and no-reroute export tests."""

import gzip
import json
import re
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from sugarglider.analysis.route import RouteAnalyzer
from sugarglider.api.main import create_app
from sugarglider.config import Settings
from sugarglider.domain.generation import RouteGenerationRequest, RouteGenerationResult
from sugarglider.domain.models import RouteRequest, RouteResult
from sugarglider.generation.service import RouteGenerationService
from sugarglider.nature.analysis import NatureRouteAnalyzer
from sugarglider.nature.index import NatureIndex
from sugarglider.nature.models import (
    NatureIndexDocument,
    NatureIndexFeature,
    NatureIndexMetadata,
    PolygonGeometry,
)
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


def _nature_document() -> NatureIndexDocument:
    feature = NatureIndexFeature(
        feature_id="way/1",
        osm_id=1,
        osm_source="way",
        primary_class="woodland",
        park_or_protected=True,
        tags={"natural": "wood", "leisure": "park"},
        geometry=PolygonGeometry(
            coordinates=(
                (
                    (2.08, 48.86),
                    (2.14, 48.86),
                    (2.14, 48.89),
                    (2.08, 48.89),
                    (2.08, 48.86),
                ),
            )
        ),
    )
    return NatureIndexDocument(
        metadata=NatureIndexMetadata(
            source_basename="test.osm",
            reference_latitude=48.875,
            bounding_box=(2.08, 48.86, 2.14, 48.89),
            category_counts={"park_or_protected": 1, "woodland": 1},
            feature_count=1,
        ),
        features=(feature,),
    )


def _nature_index() -> NatureIndex:
    return NatureIndex(_nature_document())


def _write_nature_index(path: Path) -> None:
    payload = _nature_document().model_dump(mode="json")
    with gzip.open(path, "wt", encoding="utf-8") as output:
        json.dump(payload, output)


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
        "nature_index_available": False,
        "nature_water_buffer_m": 100.0,
        "nature_preference_values": ["off", "prefer"],
    }


@pytest.mark.asyncio
async def test_nature_status_works_without_index(client: httpx.AsyncClient) -> None:
    response = await client.get("/v1/nature/status")
    assert response.status_code == 200
    body = response.json()
    assert body["configured"] is True
    assert body["available"] is False
    assert body["index_path_basename"] == ("ile-de-france-nature-index.json.gz")
    assert body["feature_count"] is None
    assert body["warnings"] == ["nature_index_unavailable"]
    assert "/data/" not in response.text


@pytest.mark.asyncio
async def test_available_nature_status_ui_route_visualization_and_clean_gpx(
    route_result: RouteResult,
    generation_result: RouteGenerationResult,
    tmp_path: Path,
) -> None:
    index_path = tmp_path / "regional.json.gz"
    _write_nature_index(index_path)
    nature = NatureRouteAnalyzer(_nature_index(), water_buffer_m=125)
    enriched = route_result.model_copy(
        update={
            "analysis": RouteAnalyzer(nature).analyze(
                route_result.geometry,
                route_result.summary.distance_m,
                route_result.path_details,
            )
        }
    )
    app = create_app(
        _FakeRouteService(enriched),
        _FakeGenerationService(generation_result),
        settings=Settings(
            nature_index_path=index_path,
            nature_water_buffer_m=125,
        ),
    )
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as nature_client:
            status = await nature_client.get("/v1/nature/status")
            config = await nature_client.get("/v1/ui/config")
            route = await nature_client.post(
                "/v1/routes",
                json={
                    "name": "Nature route",
                    "points": [
                        {"lat": 48.87, "lon": 2.09},
                        {"lat": 48.88, "lon": 2.1},
                    ],
                },
            )
            visualization = await nature_client.post(
                "/v1/routes/visualization",
                json=enriched.model_dump(mode="json"),
            )
            gpx = await nature_client.post(
                "/v1/routes/gpx/from-result",
                json=enriched.model_dump(mode="json"),
            )
    assert status.json()["available"] is True
    assert status.json()["index_path_basename"] == "regional.json.gz"
    assert status.json()["feature_count"] == 1
    assert status.json()["water_buffer_m"] == 125
    assert config.json()["nature_index_available"] is True
    assert config.json()["nature_preference_values"] == ["off", "prefer"]
    assert route.json()["analysis"]["nature"]["woodland"]["share"] == 1
    properties = visualization.json()["features"][0]["properties"]
    assert properties["nature_class"] == "woodland"
    assert properties["park_or_protected"] is True
    assert properties["near_water"] is False
    assert b"nature" not in gpx.content.lower()
    assert gpx.content.count(b"<trk>") == 1
    assert gpx.content.count(b"<trkseg>") == 1


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


def test_frontend_exposes_nature_without_raw_polygon_requests() -> None:
    html = (STATIC_DIRECTORY / "index.html").read_text(encoding="utf-8")
    app = (STATIC_DIRECTORY / "app.js").read_text(encoding="utf-8")
    state = (STATIC_DIRECTORY / "state.js").read_text(encoding="utf-8")
    map_code = (STATIC_DIRECTORY / "map.js").read_text(encoding="utf-8")
    assert 'id="nature-preference"' in html
    assert "Prefer mapped nature" in html
    assert 'id="show-nature"' in html
    for label in (
        "Woodland",
        "Open natural",
        "Agriculture",
        "Urban/developed",
        "Water crossing",
        "Unknown land cover",
    ):
        assert label in html or label in app
    assert "nature ? `${nature.nature_score" in app
    assert '"not evaluated"' in app
    assert 'state.request.status !== "running"' in app
    assert "state.request.startedAt === null" in app
    assert "nature_preference" in state
    assert "value.nature_preference" in app
    assert "nature_class" in map_code
    assert "selected-section-nature" in map_code
    assert "Object.entries(styles)" in map_code
    assert "/v1/nature/polygons" not in app + map_code
    assert "maplibre-gl@4.7.1" in html
