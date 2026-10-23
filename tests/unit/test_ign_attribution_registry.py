"""Code-pinned offline notices must stay tied to the reviewed source ledger."""

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / "src/sugarglider/web/static"


def test_ign_notice_editions_match_the_exact_pinned_source_ledger() -> None:
    source = (STATIC / "terrain_attribution.js").read_text()
    match = re.search(r"const IGN = Object.freeze\((\{.*?\})\);", source, re.DOTALL)
    assert match is not None
    registry = json.loads(match.group(1))
    ledger_bytes = (
        ROOT / "offline-regions/sources/ign-rge-alti-5m-four-tiles.json"
    ).read_bytes()
    ledger = json.loads(ledger_bytes)
    assert hashlib.sha256(ledger_bytes).hexdigest() == registry["ledger_sha256"]
    assert registry["editions"] == [file["filename"] for file in ledger["files"]]
    assert len(registry["editions"]) == len(set(registry["editions"])) == 17
    assert ledger["surface"] == "DTM" and ledger["vertical_crs"] == "EPSG:5720"
    fixture = json.loads(
        (ROOT / "tests/fixtures/ign_terrain_attribution.json").read_bytes()
    )
    components = fixture["manifest"]["components"]
    assert registry["tiles"] == components["elevation"]["files"][1:]
    assert registry["routing_archive"] == components["routing"]["files"][1]
    # A public preview changes only elevation metadata here, not pinned terrain.
    assert (
        fixture["proposed_public_elevation_descriptor"]
        != components["elevation"]["files"][0]
    )


def test_map_attribution_surface_remains_separate() -> None:
    offline_map = (STATIC / "offline_map.js").read_text()
    assert "attribution: escapeAttribution(manifest.attribution)" in offline_map
    map_manifest = ROOT / "map-packs/yvelines-ouest-parisien-map-v1.template.json"
    # Other source rights remain with the map pipeline, not the IGN licence.
    assert (
        "Terrain licensing does not cover other map data."
        in (STATIC / "terrain_attribution.js").read_text()
    )
    credits = json.loads(map_manifest.read_bytes())["attribution"]
    for name in ("OpenStreetMap", "ESA WorldCover", "Natural Earth", "Protomaps"):
        assert name in credits
