"""Independent Python contracts for the shared local regional-data browser tests."""

import gzip
import hashlib
import json
from pathlib import Path
from typing import Any, cast

import pytest

from sugarglider.analysis.route import project_geometry_edges
from sugarglider.domain.models import GeoJsonPosition
from sugarglider.nature.analysis import NatureRouteAnalyzer
from sugarglider.nature.index import NatureIndex
from sugarglider.nature.models import NatureIndexDocument
from sugarglider.offline_regions.models import RegionalManifest, canonical_json
from sugarglider.pois.models import PoiIndexDocument

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/fixtures/pr40_regional_data.json"
STATIC = ROOT / "src/sugarglider/web/static"


@pytest.fixture
def fixture() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(FIXTURE.read_text()))


def test_regional_browser_fixture_uses_unmodified_pr39_formats(
    fixture: dict[str, Any],
) -> None:
    manifest = RegionalManifest.model_validate_json(json.dumps(fixture["manifest"]))
    pois = PoiIndexDocument.model_validate(fixture["pois"])
    nature = NatureIndexDocument.model_validate(fixture["nature"])
    assert pois.metadata.bounding_box == nature.metadata.bounding_box == manifest.bounds
    for kind, document, component in (
        ("pois", pois, manifest.components.pois),
        ("nature", nature, manifest.components.nature),
    ):
        assert document.metadata.source_basename == manifest.source.basename
        content = gzip.compress(canonical_json(fixture[kind]), mtime=0)
        descriptor = component.files[0]
        assert len(content) == descriptor.byte_size
        assert hashlib.sha256(content).hexdigest() == descriptor.sha256


@pytest.mark.parametrize(
    "metric",
    (
        "woodland",
        "open_natural",
        "agriculture",
        "water_crossing",
        "urban",
        "unknown_landcover",
        "park_or_protected",
        "near_water",
        "nature_score",
    ),
)
def test_local_nature_golden_matches_independent_python_analysis(
    fixture: dict[str, Any], metric: str
) -> None:
    nature = NatureIndex(NatureIndexDocument.model_validate(fixture["nature"]))
    geometry: tuple[GeoJsonPosition, ...] = tuple(
        (float(point[0]), float(point[1])) for point in fixture["route"]["geometry"]
    )
    distance = float(fixture["route"]["distance_m"])
    edges = project_geometry_edges(
        geometry=geometry, route_distance_m=distance, path_details={}
    ).edges
    actual = NatureRouteAnalyzer(nature).analyze_route(edges, distance)
    expected = fixture["expected"][metric]
    value = actual.model_dump(mode="json")[metric]
    if metric == "nature_score":
        assert value == pytest.approx(expected, abs=1e-6)
    else:
        assert value["distance_m"] == pytest.approx(expected["distance_m"], abs=1e-5)
        assert value["share"] == pytest.approx(expected["share"], abs=1e-9)


def test_worker_module_graph_is_available_offline_without_data_precaching() -> None:
    worker = (STATIC / "service-worker.js").read_text()
    for name in (
        "regional_manifest",
        "local_region_client",
        "local_region_worker",
        "local_region_store",
        "local_region_data",
        "local_region_panel",
    ):
        assert f'"/static/{name}.js"' in worker
    assert "index.json.gz" not in worker
    assert "valhalla_tiles.tar" not in worker
    assert "indexedDB" not in (STATIC / "local_region_store.js").read_text()
