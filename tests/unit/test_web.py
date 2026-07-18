"""Static application, UI configuration, and no-reroute export tests."""

import gzip
import hashlib
import json
import re
import struct
import subprocess
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from zipfile import ZipFile

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

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CANONICAL_BRAND_DIRECTORY = REPOSITORY_ROOT / "assets" / "brand"
RUNTIME_BRAND_DIRECTORY = STATIC_DIRECTORY / "brand"
FONT_DIRECTORY = STATIC_DIRECTORY / "fonts" / "Open Sans Semibold"
BRAND_ASSET_FILENAMES = (
    "sugarglider-app-icon.png",
    "sugarglider-banner.png",
    "sugarglider-compact-icon.png",
    "sugarglider-flying-map.png",
    "sugarglider-map-pin.png",
    "sugarglider-water-pin.png",
)
FONT_GLYPH_HASHES: dict[str, str] = {
    "0-255.pbf": "64da7011e07531351a249a3d26aad76e2f22e4e321e50833f742697b453e8365",
    "256-511.pbf": "78298bbd8198c117ccdffe66bf9bbf646fdc1210b7e1bf222f5a9b29b366d7a5",
    "8192-8447.pbf": "ee80ee7ef05e77bea017bcb387d970d61823fc37fdb0a51c446ae322c5974990",
}


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


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _png_dimensions(path: Path) -> tuple[int, int]:
    payload = path.read_bytes()
    assert payload.startswith(b"\x89PNG\r\n\x1a\n")
    assert payload[12:16] == b"IHDR"
    return struct.unpack(">II", payload[16:24])


def test_brand_asset_manifest_is_exact_and_byte_identical() -> None:
    expected = set(BRAND_ASSET_FILENAMES)
    canonical = {
        path.name for path in CANONICAL_BRAND_DIRECTORY.glob("*.png") if path.is_file()
    }
    runtime = {
        path.name for path in RUNTIME_BRAND_DIRECTORY.glob("*.png") if path.is_file()
    }
    assert canonical == runtime == expected
    for filename in BRAND_ASSET_FILENAMES:
        assert _sha256(CANONICAL_BRAND_DIRECTORY / filename) == _sha256(
            RUNTIME_BRAND_DIRECTORY / filename
        )
    assert _png_dimensions(CANONICAL_BRAND_DIRECTORY / "sugarglider-map-pin.png") == (
        1024,
        1536,
    )
    assert _png_dimensions(CANONICAL_BRAND_DIRECTORY / "sugarglider-water-pin.png") == (
        1024,
        1536,
    )


def test_brand_asset_sync_is_independent_of_current_working_directory(
    tmp_path: Path,
) -> None:
    result = subprocess.run(
        [sys.executable, REPOSITORY_ROOT / "scripts" / "sync_web_brand_assets.py"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )
    assert all(filename in result.stdout for filename in BRAND_ASSET_FILENAMES)


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
async def test_every_runtime_brand_asset_is_served_as_png(
    client: httpx.AsyncClient,
) -> None:
    for filename in BRAND_ASSET_FILENAMES:
        response = await client.get(f"/static/brand/{filename}")
        assert response.status_code == 200, filename
        assert response.headers["content-type"] == "image/png"
        assert response.content.startswith(b"\x89PNG\r\n\x1a\n")
    missing = await client.get("/static/brand/not-a-brand-asset.png")
    assert missing.status_code == 404

    for filename, expected_hash in FONT_GLYPH_HASHES.items():
        glyphs = await client.get(f"/static/fonts/Open%20Sans%20Semibold/{filename}")
        assert glyphs.status_code == 200
        assert glyphs.headers["content-type"] == "application/octet-stream"
        assert hashlib.sha256(glyphs.content).hexdigest() == expected_hash

    for filename in ("README.md", "LICENSE.txt"):
        document = await client.get(f"/static/fonts/Open%20Sans%20Semibold/{filename}")
        assert document.status_code == 200
        assert document.text


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
            assert (
                await independent_client.get("/static/brand/sugarglider-map-pin.png")
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
        "loop_geometry_preference_values": ["off", "prefer"],
        "poi_index_available": False,
        "poi_default_limit": 500,
        "poi_max_limit": 1000,
        "default_planning_mode": "auto_tour",
        "auto_tour_max_hard_points": 6,
        "auto_tour_max_preferred_pois": 8,
        "auto_tour_scenic_corridor_radius_m": 600.0,
        "auto_tour_water_corridor_radius_m": 350.0,
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


def test_font_license_provenance_and_glyphs_are_in_wheel(tmp_path: Path) -> None:
    provenance = (FONT_DIRECTORY / "README.md").read_text(encoding="utf-8")
    license_text = (FONT_DIRECTORY / "LICENSE.txt").read_text(encoding="utf-8")
    assert "2026-07-18" in provenance
    assert "ef4389e954d46e97cd9d3b0130881d9fb789ae2e" in provenance
    assert "0bcd6431ec82fbb74b3a5b697ce315ebf795ad8e" in provenance
    assert "U+0000–U+00FF" in provenance
    assert "U+0100–U+01FF" in provenance
    assert "U+2000–U+20FF" in provenance
    for filename, expected_hash in FONT_GLYPH_HASHES.items():
        glyph_bytes = (FONT_DIRECTORY / filename).read_bytes()
        assert hashlib.sha256(glyph_bytes).hexdigest() == expected_hash
        assert expected_hash in provenance
    assert "Apache License" in license_text
    assert "Version 2.0, January 2004" in license_text

    wheel_directory = tmp_path / "wheel"
    subprocess.run(
        [
            "uv",
            "build",
            "--wheel",
            "--offline",
            "--out-dir",
            str(wheel_directory),
        ],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    wheel = next(wheel_directory.glob("*.whl"))
    with ZipFile(wheel) as archive:
        packaged_files = set(archive.namelist())
    prefix = "sugarglider/web/static/fonts/Open Sans Semibold/"
    assert {
        f"{prefix}README.md",
        f"{prefix}LICENSE.txt",
        *(f"{prefix}{filename}" for filename in FONT_GLYPH_HASHES),
    } <= packaged_files


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


def test_frontend_exposes_loop_geometry_request_metrics_and_nulls() -> None:
    html = (STATIC_DIRECTORY / "index.html").read_text(encoding="utf-8")
    app = (STATIC_DIRECTORY / "app.js").read_text(encoding="utf-8")
    state = (STATIC_DIRECTORY / "state.js").read_text(encoding="utf-8")
    formatting = (STATIC_DIRECTORY / "format.js").read_text(encoding="utf-8")
    assert 'id="loop-geometry-preference"' in html
    assert "Prefer balanced loops" in html
    assert "outbound/return" in app.lower()
    assert 'loopGeometryPreference: "off"' in state
    assert "loop_geometry_preference: state.options.loopGeometryPreference" in state
    assert 'value.loop_geometry_preference ?? "off"' in app
    assert "loopGeometryCardSummary" in app
    assert "loopGeometryCardDetails" in app
    assert "loopGeometrySection" in app
    assert '<details class="loop-geometry-exact">' in app
    assert "Exact geometry details" in app
    assert "loop-sector-grid" in app
    assert "Sector ${index + 1}" in app
    assert "Base evaluation budget" in app
    assert "Geometry extra evaluations" in app
    for label in (
        "Shape penalty (lower is better)",
        "Compactness",
        "Sector balance",
        "Near-parallel corridor",
        "Self-crossings",
        "Elongation",
        "Enclosed area",
        "Maximum radius",
    ):
        assert label in app
    assert "Shape metrics are unknown, not zero" in app
    assert "loop_geometry_analysis_incomplete" in formatting
    assert "loop_geometry_no_candidate_improvement" in formatting
    assert "natureSection(analysis.nature, search)" in app
    assert 'id="show-nature"' in html
    assert "/v1/nature/polygons" not in app


def test_frontend_places_are_bounded_safe_and_separate_from_routing_state() -> None:
    html = (STATIC_DIRECTORY / "index.html").read_text(encoding="utf-8")
    app = (STATIC_DIRECTORY / "app.js").read_text(encoding="utf-8")
    api = (STATIC_DIRECTORY / "api.js").read_text(encoding="utf-8")
    state_code = (STATIC_DIRECTORY / "state.js").read_text(encoding="utf-8")
    map_code = (STATIC_DIRECTORY / "map.js").read_text(encoding="utf-8")

    for control in (
        "place-scenic",
        "place-verified-water",
        "place-unknown-water",
        "place-broad",
        "place-restricted",
        "place-private",
        "place-non-potable",
    ):
        assert f'id="{control}"' in html
    assert 'id="place-scenic" type="checkbox" checked' in html
    assert 'id="place-verified-water" type="checkbox" checked' in html
    assert 'id="place-unknown-water" type="checkbox">' in html
    assert 'class="places-advanced"' in html
    assert "never alter mandatory points, generation, ranking, or GPX" in html

    assert 'fetch("/v1/pois/status"' in api
    assert 'fetch("/v1/pois/search"' in api
    assert "currentViewportBounds" in app
    assert "window.setTimeout(() => fetchViewportPois" in app
    assert "250" in app
    assert "state.poiAbortController?.abort()" in app
    assert "if (!filters.categories.length) return null" in app
    assert "state.poiRequest.id !== id" in app
    assert "response.truncated" in app
    assert "zoom in to narrow the viewport" in app

    assert "selectedPoiId: null" in state_code
    assert "selectedPointIndex: null" in state_code
    select_poi = app[
        app.index("function selectPoi") : app.index("async function fetchViewportPois")
    ]
    assert "state.points" not in select_poi
    assert "currentRequest" not in select_poi
    assert "Add to route" not in html + app + map_code

    assert "cluster: true" in map_code
    assert "clusterRadius" in map_code
    assert "map.getSource(POI_SOURCE).setData" in map_code
    assert "poiCollection(features.filter" in map_code
    assert "setDOMContent(poiPopupContent(feature))" in map_code
    assert "document.createTextNode(value)" in map_code
    assert (
        'explanation.textContent = "Mapped in OpenStreetMap as drinking water."'
        in map_code
    )
    assert (
        'explanation.textContent = "Potability is not specified in the mapped data."'
        in map_code
    )
    assert 'explanation.textContent = "Mapped as non-potable."' in map_code
    assert "innerHTML" not in map_code[map_code.index("function poiPopupContent") :]
    assert "new Blob([svgMarkup(body)]" in map_code
    assert "image/svg+xml" in map_code
    assert "icon CDN" not in map_code
    assert "POI_SELECTED_SOURCE" in map_code
    assert "moveRequiredLabelsToTop" in map_code

    assert 'id="nature-preference"' in html
    assert 'id="loop-geometry-preference"' in html
    assert 'id="show-nature"' in html
    assert 'id="show-all"' in html


def test_frontend_auto_tour_is_default_and_preserves_waypoint_mode() -> None:
    html = (STATIC_DIRECTORY / "index.html").read_text(encoding="utf-8")
    app = (STATIC_DIRECTORY / "app.js").read_text(encoding="utf-8")
    api = (STATIC_DIRECTORY / "api.js").read_text(encoding="utf-8")
    state_code = (STATIC_DIRECTORY / "state.js").read_text(encoding="utf-8")
    map_code = (STATIC_DIRECTORY / "map.js").read_text(encoding="utf-8")

    assert 'planningMode: "auto_tour"' in state_code
    assert 'value="auto_tour" checked' in html
    assert 'value="waypoint_route"' in html
    assert 'fetch("/v1/tours/generate"' in api
    assert "currentAutoTourRequest" in app
    assert "preferred_poi_ids" in state_code
    assert "direction_preference" in state_code
    assert "scenic_preference" in state_code
    assert "drinking_water_preference" in state_code
    assert "requested_places" in state_code
    assert 'distancePriority: "flexible"' in state_code
    assert 'id="distance-priority"' in html
    assert 'id="requested-places"' in html
    assert 'if (state.planningMode === "auto_tour")' in app
    assert "state.autoTour.requestedPlaces = requested.map" in app
    assert 'switchPlanningMode("waypoint_route")' not in app
    assert "Prefer in Auto Tour" in map_code
    assert "Require exact visit" not in html + app + map_code
    assert (
        'const VERIFIED_WATER_PIN_URL = "/static/brand/sugarglider-water-pin.png"'
        in map_code
    )
    assert 'map.addImage("poi-water-verified"' in map_code
    assert '"poi-water-unknown"' in map_code
    assert '"poi-water-nonpotable"' in map_code
    assert "selectedPoiId: null" in state_code
    assert "selectedPointIndex: null" in state_code
    assert "function selectPoi" in app
    assert (
        "state.points"
        not in app[
            app.index("function selectPoi") : app.index(
                "function selectedVisitedPoiIds"
            )
        ]
    )


def test_requested_places_have_an_independent_safe_map_lifecycle() -> None:
    html = (STATIC_DIRECTORY / "index.html").read_text(encoding="utf-8")
    app = (STATIC_DIRECTORY / "app.js").read_text(encoding="utf-8")
    map_code = (STATIC_DIRECTORY / "map.js").read_text(encoding="utf-8")
    state_code = (STATIC_DIRECTORY / "state.js").read_text(encoding="utf-8")
    styles = (STATIC_DIRECTORY / "styles.css").read_text(encoding="utf-8")

    assert 'const REQUESTED_SOURCE = "auto-tour-requested-places"' in map_code
    assert (
        'const REQUESTED_RADIUS_SOURCE = "auto-tour-requested-place-radii"' in map_code
    )
    assert "requestedPlaceFeatureCollection" in map_code
    for property_name in (
        "requested_id",
        "original_order",
        "name",
        "longitude",
        "latitude",
        "importance",
        "visit_radius_m",
        "status",
        "measured_distance_m",
        "visit_reason",
    ):
        assert property_name in map_code
    assert 'visit.satisfied ? "satisfied" : "missed"' in map_code
    assert '"pending"' in map_code
    assert "requestedPlaceIdentifier(backendRequestedPlace(visit), index)" in map_code
    assert "requestedPlaceIdentifier(place, index)" in app
    assert "selectedRequestedPlaceId: null" in state_code
    assert "pendingRequestedPlacePopupId: null" in state_code

    requested_layers = map_code[
        map_code.index("function ensureRequestedPlaceLayers") : map_code.index(
            "function requestedPlaceStatusLabel"
        )
    ]
    assert 'type: "circle"' in requested_layers
    assert 'type: "symbol"' in requested_layers
    assert '"text-allow-overlap": false' in requested_layers
    assert '"circle-opacity": .98' in requested_layers
    assert '"satisfied", "#4f8c61"' in requested_layers
    assert '"missed", "#c94f47"' in requested_layers
    assert '"#fff1c7"' in requested_layers
    assert "REQUESTED_PREFERRED_LAYER" in requested_layers
    assert "poi-water-verified" not in requested_layers
    assert "map.getSource(REQUESTED_SOURCE)" in map_code
    assert "map.getLayer(layer.id)" in map_code

    assert "requestedPlaceRadiusCollection" in map_code
    assert "REQUESTED_RADIUS_SEGMENTS = 48" in map_code
    assert "feature.properties.visit_radius_m" in map_code
    assert "showMissed && feature.properties.status" in map_code
    assert 'id="show-missed-requested-radii"' in html
    assert "showMissedRequestedRadii: false" in state_code

    popup = map_code[
        map_code.index("function requestedPlacePopupContent") : map_code.index(
            "function showRequestedPlacePopup"
        )
    ]
    assert "document.createElement" in popup
    assert "textContent" in popup
    assert "innerHTML" not in popup
    assert "setHTML" not in popup
    assert "Closest route passage" in popup
    assert "Required radius" in popup

    assert "candidate?.requested_place_visits ?? []" in app
    assert "renderRequestedPlaceMarkers(" in app
    assert "state.pendingRequestedPlacePopupId = null" in app
    assert "state.selectedRequestedPlaceId = null" in app
    assert "requested-place-row" in app
    assert 'item.setAttribute("role", "button")' in app
    assert "scrollRequestedPlaceIntoView" in app
    assert "fitCoordinates(imported.points.map" in app
    assert 'switchPlanningMode("waypoint_route")' not in app

    for legend_class in (
        "requested-pending",
        "requested-satisfied",
        "requested-missed",
        "mascot-water",
    ):
        assert legend_class in html
        assert legend_class in styles
    assert "Your plan" in html
    assert "Mapped OSM discovery" in html
    assert "max-width: calc(100vw - 24px)" in styles


def test_frontend_uses_local_brand_identity_and_accessible_landmarks() -> None:
    html = (STATIC_DIRECTORY / "index.html").read_text(encoding="utf-8")
    assert '<link rel="icon" type="image/png" href="/static/brand/' in html
    assert 'src="/static/brand/sugarglider-compact-icon.png"' in html
    assert 'src="/static/brand/sugarglider-banner.png"' in html
    assert 'src="/static/brand/sugarglider-flying-map.png"' in html
    assert "Natural trail loops from the paths you choose." in html
    assert 'loading="lazy"' in html
    assert '<meta name="theme-color"' in html
    for landmark in ("<header", "<nav", "<main", "<aside", "<footer"):
        assert landmark in html
    assert 'aria-live="polite"' in html
    assert 'id="generation-state"' in html
    assert 'id="planner-empty"' in html
    assert "prefers-reduced-motion" in (STATIC_DIRECTORY / "styles.css").read_text(
        encoding="utf-8"
    )
    brand_urls = re.findall(r'(?:src|href)="([^"]*sugarglider-[^"]+\.png)"', html)
    assert brand_urls
    assert all(url.startswith("/static/brand/") for url in brand_urls)


def test_required_marker_labels_and_selection_are_coordinated() -> None:
    app = (STATIC_DIRECTORY / "app.js").read_text(encoding="utf-8")
    html = (STATIC_DIRECTORY / "index.html").read_text(encoding="utf-8")
    map_code = (STATIC_DIRECTORY / "map.js").read_text(encoding="utf-8")
    state = (STATIC_DIRECTORY / "state.js").read_text(encoding="utf-8")
    styles = (STATIC_DIRECTORY / "styles.css").read_text(encoding="utf-8")
    assert (
        'const REQUIRED_PIN_URL = "/static/brand/sugarglider-map-pin.png"' in map_code
    )
    assert "data:image" not in map_code
    assert 'anchor: "bottom"' in map_code
    assert "element.className = `required-marker" in map_code
    assert "image.width = 40" in map_code and "image.height = 60" in map_code
    assert "image.draggable = false" in map_code
    assert "element.dataset.accessibleLabel = `Required point" in map_code
    assert (
        'element.setAttribute("aria-label", element.dataset.accessibleLabel)'
        in map_code
    )
    assert "required-point-labels" in map_code
    assert '"text-variable-anchor"' in map_code
    assert '"text-radial-offset"' in map_code
    assert '"text-allow-overlap": false' in map_code
    assert '"text-allow-overlap": true' in map_code
    assert '"symbol-sort-key"' in map_code
    assert '"text-max-width": 14' in map_code
    assert '"text-line-height": 1.15' in map_code
    assert "minzoom: 10.5" in map_code
    assert "source_index" in map_code
    assert "original_request_index" in map_code
    assert "selectedPointIndex" in state
    assert "pendingPointPopupIndex: null" in state
    assert "selectPoint" in app
    assert "updatePoiSelection" in app
    assert "list.scrollTop = rowBottom - list.clientHeight" in app
    assert "handlers.onActivate" in map_code
    assert "if (popupIndex === sourceIndex) marker.togglePopup()" in map_code
    assert "if (selected) marker.togglePopup()" not in map_code
    assert "const popupIndex = state.pendingPointPopupIndex" in app
    assert "state.pendingPointPopupIndex = null" in app
    assert 'role="list"' in html
    assert 'role="listbox"' not in html
    assert 'row.role = "listitem"' in app
    assert 'row.role = "option"' not in app
    assert 'row.setAttribute("aria-current", "true")' in app
    assert "aria-selected" not in html + app
    assert '<details class="legend">' in html
    assert '<details class="legend" open>' not in html
    assert ".required-marker { width: 40px; height: 60px;" in styles
    assert ".required-marker.start { width: 48px; height: 72px;" in styles
    assert ".required-marker { width: 36px; height: 54px;" in styles
    assert ".required-marker.start { width: 44px; height: 66px;" in styles


def test_point_names_remain_text_safe_through_import_edit_map_and_copy() -> None:
    app = (STATIC_DIRECTORY / "app.js").read_text(encoding="utf-8")
    map_code = (STATIC_DIRECTORY / "map.js").read_text(encoding="utf-8")
    state = (STATIC_DIRECTORY / "state.js").read_text(encoding="utf-8")
    assert "suppliedName" in app
    assert "pointDisplayName(point, index)" in app
    assert "name: pointDisplayName(point, index)" in state
    assert "heading.textContent" in map_code
    assert "display_name: displayName" in map_code
    assert "setDOMContent" in map_code
    assert "${point.name}" not in map_code
    assert "currentRequest()" in app


def test_frontend_keeps_browser_native_modules_and_local_icons() -> None:
    html = (STATIC_DIRECTORY / "index.html").read_text(encoding="utf-8")
    app = (STATIC_DIRECTORY / "app.js").read_text(encoding="utf-8")
    icons = (STATIC_DIRECTORY / "icons.js").read_text(encoding="utf-8")
    assert 'type="module"' in html
    assert 'from "./icons.js"' in app
    assert "currentColor" in (STATIC_DIRECTORY / "styles.css").read_text(
        encoding="utf-8"
    )
    assert "createElementNS" in icons
    assert "ICON_PATHS" in icons
    assert not (REPOSITORY_ROOT / "package.json").exists()
    assert not (REPOSITORY_ROOT / "node_modules").exists()
