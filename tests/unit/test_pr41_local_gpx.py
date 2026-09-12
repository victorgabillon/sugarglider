"""Python truth for shared offline GPX fixtures and profile metadata."""

import json
from pathlib import Path
from typing import Any, cast
from xml.etree import ElementTree

from sugarglider.gpx.writer import GPX_NAMESPACE, gpx_filename, write_plan_gpx
from sugarglider.planning.result import PlanCandidate
from sugarglider.web.build_profile_metadata import render_profile_metadata
from sugarglider.web.routes import STATIC_DIRECTORY

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "pr41_local_gpx.json"


def test_packaged_profile_metadata_matches_sole_registry() -> None:
    assert (STATIC_DIRECTORY / "public_profile_metadata.js").read_text() == (
        render_profile_metadata()
    )


def test_browser_gpx_fixture_matches_canonical_python_writer() -> None:
    fixture = cast(dict[str, Any], json.loads(FIXTURE.read_text()))
    candidate = PlanCandidate.model_validate(fixture["candidate"])
    before = candidate.model_dump_json()
    root = ElementTree.fromstring(write_plan_gpx(candidate))
    namespace = {"g": GPX_NAMESPACE}
    actual = {
        "name": root.findtext("g:metadata/g:name", namespaces=namespace),
        "description": root.findtext("g:metadata/g:desc", namespaces=namespace),
        "type": root.findtext("g:trk/g:type", namespaces=namespace),
        "points": [
            point.attrib for point in root.findall("g:trk/g:trkseg/g:trkpt", namespace)
        ],
        "waypoints": [
            {
                "coordinate": point.attrib,
                "name": point.findtext("g:name", namespaces=namespace),
                "description": point.findtext("g:desc", namespaces=namespace),
                "type": point.findtext("g:type", namespaces=namespace),
            }
            for point in root.findall("g:wpt", namespace)
        ],
    }
    assert actual == fixture["expected"]
    # The earlier approximation must precede the later reached stop. The two
    # arrays must never be concatenated as if they already formed visit order.
    waypoint_names = [
        point.findtext("g:name", namespaces=namespace)
        for point in root.findall("g:wpt", namespace)
    ]
    assert waypoint_names == ["1. Forêt <ouverte> — approximate", "2. Étape & source"]
    assert len(root.findall("g:trk", namespace)) == 1
    assert len(root.findall("g:trk/g:trkseg", namespace)) == 1
    assert root.findall("g:rte", namespace) == []
    assert root.findall(".//g:extensions", namespace) == []
    assert candidate.model_dump_json() == before


def test_browser_coordinate_and_filename_cases_match_python() -> None:
    fixture = cast(dict[str, Any], json.loads(FIXTURE.read_text()))
    for case in fixture["coordinates"]:
        assert format(case["value"], ".8f") == case["formatted"]
    for case in fixture["filenames"]:
        assert gpx_filename(case["name"]) == case["filename"]


def test_normal_export_is_local_and_available_with_an_offline_candidate() -> None:
    app = (STATIC_DIRECTORY / "app.js").read_text()
    handler = app[app.index("async function downloadSelected()") :]
    handler = handler[: handler.index("function renderSavedRoutePanel()")]
    assert "await localGpxExporter.exportCandidate(candidate)" in handler
    assert "serverFeaturesUnavailable" not in handler
    assert "downloadSavedRouteGpx" not in handler
    assert 'byId("download-gpx").disabled = !candidate || busy' in app
    worker = (STATIC_DIRECTORY / "service-worker.js").read_text()
    for name in (
        "local_gpx_export",
        "local_gpx_client",
        "local_gpx_worker",
        "public_profile_metadata",
    ):
        assert f'"/static/{name}.js"' in worker
