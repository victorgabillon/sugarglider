"""Architecture and packaging contracts for PR36 offline map packs."""

from __future__ import annotations

import hashlib
import json
import re
import struct
import subprocess
import sys
from pathlib import Path

from sugarglider.web.routes import STATIC_DIRECTORY

ROOT = Path(__file__).resolve().parents[2]
PMTILES_VENDOR = STATIC_DIRECTORY / "vendor" / "pmtiles-4.5.0"
BASEMAPS_VENDOR = STATIC_DIRECTORY / "vendor" / "protomaps-basemaps-5.7.2"
MANIFEST_FIELDS = {
    "archive_filename",
    "attribution",
    "bounds",
    "build_id",
    "byte_size",
    "data_source",
    "display_name",
    "format",
    "max_zoom",
    "min_zoom",
    "pack_id",
    "schema_version",
    "tile_type",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _core_assets(worker: str) -> set[str]:
    block = worker[
        worker.index("const CORE_ASSETS") : worker.index("function navigationResponse")
    ]
    return set(re.findall(r'"(/[^"]+)"', block))


def test_exact_pmtiles_and_protomaps_distributions_are_vendored() -> None:
    assert {path.name for path in PMTILES_VENDOR.iterdir()} == {
        "LICENSE.txt",
        "README.md",
        "pmtiles.js",
    }
    assert _sha256(PMTILES_VENDOR / "pmtiles.js") == (
        "08d687b3605d61ee91128086d826676708ff51e5f2e1c7acc02b5834984bbbc7"
    )
    assert _sha256(PMTILES_VENDOR / "LICENSE.txt") == (
        "c5430dc019512cc4f4fe8c89e9f57bc5cd3096916847fba4bb7e632d55f86579"
    )
    assert {path.name for path in BASEMAPS_VENDOR.iterdir()} == {
        "LICENSE.md",
        "README.md",
        "basemaps.js",
    }
    assert _sha256(BASEMAPS_VENDOR / "basemaps.js") == (
        "a41d87faaf6004ffa264d81d6afd8d819ad55f88753ad3706ba046c855a17a2b"
    )
    assert _sha256(BASEMAPS_VENDOR / "LICENSE.md") == (
        "74f975cfedd168098c43b5cfd6e587e40604684c4ffcec3e90d24b3b09c061b0"
    )
    assert "pmtiles@4.5.0" in (PMTILES_VENDOR / "README.md").read_text()
    assert "@protomaps/basemaps@5.7.2" in (BASEMAPS_VENDOR / "README.md").read_text()


def test_manifest_templates_are_strict_and_map_packs_are_ignored() -> None:
    templates = sorted((ROOT / "map-packs").glob("*.template.json"))
    assert [path.name for path in templates] == [
        "marly-map-dev-v1.template.json",
        "paris-map-dev-v1.template.json",
    ]
    for path in templates:
        value = json.loads(path.read_text(encoding="utf-8"))
        assert set(value) == MANIFEST_FIELDS
        assert value["schema_version"] == 1
        assert value["format"] == "pmtiles-v3"
        assert value["tile_type"] == "mvt"
        assert value["archive_filename"] == "basemap.pmtiles"
        assert "OpenStreetMap contributors" in value["attribution"]
    assert "data/map-packs/" in (ROOT / ".gitignore").read_text()


def test_manifest_writer_reads_pmtiles_header_and_records_input_identity(
    tmp_path: Path,
) -> None:
    template = ROOT / "map-packs/marly-map-dev-v1.template.json"
    template_value = json.loads(template.read_text(encoding="utf-8"))
    archive = tmp_path / "basemap.pmtiles"
    payload = bytearray(127)
    payload[:7] = b"PMTiles"
    payload[7] = 3
    payload[99] = 1
    payload[100] = template_value["min_zoom"]
    payload[101] = template_value["max_zoom"]
    for offset, coordinate in zip(
        (102, 106, 110, 114), template_value["bounds"], strict=True
    ):
        struct.pack_into("<i", payload, offset, round(coordinate * 10_000_000))
    archive.write_bytes(payload)
    source_pbf = tmp_path / "source.osm.pbf"
    source_pbf.write_bytes(b"deterministic fixture")
    output = tmp_path / "manifest.json"
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/write_pr36_map_pack_manifest.py"),
            "--template",
            str(template),
            "--archive",
            str(archive),
            "--source-pbf",
            str(source_pbf),
            "--output",
            str(output),
        ],
        check=True,
    )
    manifest = json.loads(output.read_text(encoding="utf-8"))
    assert set(manifest) == MANIFEST_FIELDS
    assert manifest["byte_size"] == len(payload)
    assert manifest["build_id"].startswith("protomaps-3ea8293a2813-pbf-")
    assert f"-pbf-{_sha256(source_pbf)[:16]}-" in manifest["build_id"]
    assert manifest["build_id"].endswith(f"-pmtiles-{_sha256(archive)[:16]}")


def test_opfs_store_is_shared_strict_streamed_and_network_safe() -> None:
    manifest = (STATIC_DIRECTORY / "map_pack_manifest.js").read_text()
    store = (STATIC_DIRECTORY / "map_pack_store.js").read_text()
    source = (STATIC_DIRECTORY / "opfs_pmtiles_source.js").read_text()
    assert "Object.keys(value).sort()" in manifest
    assert 'value.format !== "pmtiles-v3"' in manifest
    assert 'value.tile_type !== "mvt"' in manifest
    assert "boundsArea(left.bounds)" in manifest
    assert "compareAscii(left.pack_id, right.pack_id)" in manifest
    assert 'MAP_PACK_DIRECTORY = "sugarglider-map-packs"' in store
    assert 'getFileHandle("manifest.json"' in store
    assert store.index("await this.archiveValidator") < store.index(
        'getFileHandle("manifest.json", { create: true })'
    )
    assert "response.body?.getReader?.()" in store
    assert 'credentials: "omit"' in store
    assert 'redirect: "error"' in store
    assert 'cache: "no-store"' in store
    for forbidden in ("file://", "content://", "javascript:", "addJavascriptInterface"):
        assert forbidden not in store
    assert "file.slice(offset, end).arrayBuffer()" in source
    assert "MAXIMUM_PM_TILES_RANGE_BYTES" in source
    assert "archive.getHeader()" in source
    assert "archive.getMetadata()" in source


def test_local_basemap_uses_shared_map_and_preserves_truthful_fallbacks() -> None:
    application = (STATIC_DIRECTORY / "app.js").read_text()
    map_source = (STATIC_DIRECTORY / "map.js").read_text()
    offline_map = (STATIC_DIRECTORY / "offline_map.js").read_text()
    index = (STATIC_DIRECTORY / "index.html").read_text()
    assert index.count('id="offline-map-pack-status"') == 1
    assert index.count('id="offline-map-status"') == 1
    assert 'id="offline-map-install-form"' in index
    assert index.index("pmtiles-4.5.0/pmtiles.js") < index.index("app.js")
    assert application.index("await initializeOfflineMaps") < application.index(
        "if (currentOutingSlug)"
    )
    assert "offlineMapBootstrapForConfig(config)" in map_source
    assert (
        "const startWithOnlineRaster = !offline && !bootstrap.covering_local_pack"
        in (map_source)
    )
    assert "style: initialMapStyle(config)" in map_source
    assert "function bootstrapForConfig(config)" in offline_map
    assert "selectMapPackForCoordinate(scan.packs" in offline_map
    assert "await attachOfflineBasemap(loadedMap, config)" in map_source
    assert 'id: "offline-background"' in map_source
    assert "url: `pmtiles://${opened.source.getKey()}`" in offline_map
    assert "active_source_diagnostics" in offline_map
    assert "offlineMapSnapshot" in offline_map
    assert 'original.type === "symbol" || original.type === "background"' in offline_map
    assert "removeLocalBasemap(currentMap)" in offline_map
    for state in (
        "local_pack_active",
        "no_covering_map_pack",
        "map_pack_storage_unavailable",
        "map_pack_invalid",
        "map_pack_install_failed",
    ):
        assert state in offline_map
    for forbidden in ("navigator.userAgent", "Android", "file://", "content://"):
        assert forbidden not in offline_map


def test_service_worker_precaches_runtime_but_never_map_archives() -> None:
    worker = (STATIC_DIRECTORY / "service-worker.js").read_text()
    policy = (STATIC_DIRECTORY / "service_worker_policy.js").read_text()
    core = _core_assets(worker)
    assert "`${SHELL_CACHE_PREFIX}v31`" in worker
    assert {
        "/static/vendor/pmtiles-4.5.0/pmtiles.js",
        "/static/vendor/protomaps-basemaps-5.7.2/basemaps.js",
        "/static/map_pack_manifest.js",
        "/static/map_pack_store.js",
        "/static/opfs_pmtiles_source.js",
        "/static/offline_map.js",
    } <= core
    assert not any(path.endswith(".pmtiles") for path in core)
    assert 'pathname.endsWith(".pmtiles")' in policy
    assert 'request.cache === "no-store"' in policy


def test_build_pipeline_and_browser_harness_are_bounded() -> None:
    build = (ROOT / "scripts/build_pr36_map_pack.sh").read_text()
    harness = (ROOT / "tests/browser/pr36_offline_maps_harness.js").read_text()
    html = (ROOT / "tests/browser/pr36_offline_maps_harness.html").read_text()
    assert "7b8e71f18627754af756923f6613a9008b5f1ff82377fff4e617157d053fc807" in build
    assert "maven:3.9.13-eclipse-temurin-21-alpine@sha256:" in build
    assert '--bounds="$BOUNDS"' in build
    assert "--maxzoom=15" in build
    assert "write_pr36_map_pack_manifest.py" in build
    assert "Output already exists; remove it explicitly" in build
    assert harness.count('scenarios.push("') == 17
    assert "real_opfs_create_write_slice_read_delete" in harness
    assert "interrupted_install_never_becomes_active" in harness
    assert "region_switch_removes_stale_source_and_keeps_overlays" in harness
    assert "covering_bootstrap_omits_online_raster_source" in harness
    assert "bootstrap_preserves_online_and_neutral_fallbacks" in harness
    assert "failed_local_open_adds_only_truthful_fallback" in harness
    assert "runPr36OfflineMapsHarness" in html
    assert 'addEventListener("unhandledrejection"' in html
    assert 'addEventListener("error"' in html
