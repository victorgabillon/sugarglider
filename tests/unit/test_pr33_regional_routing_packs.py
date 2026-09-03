"""Static architecture contracts for the PR33 regional routing-pack foundation."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ANDROID = ROOT / "android/app"
KOTLIN = ANDROID / "src/main/java/io/github/victorgabillon/sugarglider"
DEBUG_KOTLIN = ANDROID / "src/debug/java/io/github/victorgabillon/sugarglider"
RELEASE_KOTLIN = ANDROID / "src/release/java/io/github/victorgabillon/sugarglider"
STATIC = ROOT / "src/sugarglider/web/static"


def test_manifest_registry_is_strict_confined_and_deterministic() -> None:
    registry = (KOTLIN / "RoutingPackRegistry.kt").read_text()
    for field in (
        '"schema_version"',
        '"pack_id"',
        '"engine"',
        '"engine_version"',
        '"bounds"',
        '"west"',
        '"south"',
        '"east"',
        '"north"',
    ):
        assert field in registry
    assert "ROUTING_PACK_MANIFEST_SCHEMA_VERSION_V1 = 1" in registry
    assert "ROUTING_PACK_MANIFEST_SCHEMA_VERSION = 2" in registry
    assert '"access_modes"' in registry
    assert 'ROUTING_PACK_ENGINE = "valhalla"' in registry
    assert 'ROUTING_PACK_ENGINE_VERSION = "3.6.3"' in registry
    assert 'ROUTING_PACK_MANIFEST_NAME = "manifest.json"' in registry
    assert 'ROUTING_PACK_TILE_ARCHIVE_NAME = "valhalla_tiles.tar"' in registry
    assert "packId == directoryPackId" in registry
    assert "it.parentFile == directory" in registry
    assert "directory.parentFile != canonicalRoot" in registry
    assert "length < TAR_BLOCK_BYTES" in registry
    assert 'VALHALLA_INDEX_ENTRY = "index.bin"' in registry
    assert 'TAR_MAGIC = "ustar"' in registry
    assert "coordinate.longitude in west..east" in registry
    assert "coordinate.latitude in south..north" in registry
    assert "points.all(manifest.bounds::contains)" in registry
    assert ".filter { it.covers(points) }" in registry
    assert "it.manifest.bounds.area()" in registry
    assert ".thenBy(RoutingPack::packId)" in registry
    assert (
        "absolutePath"
        not in registry[
            registry.index("RoutingPackManifest") : registry.index("RoutingPack(")
        ]
    )


def test_debug_engine_selects_one_pack_and_keeps_one_current_actor() -> None:
    engine = (DEBUG_KOTLIN / "NativeRouteEngineFactory.kt").read_text()
    registry = (KOTLIN / "RoutingPackRegistry.kt").read_text()
    assert "registry.select(request.points, request.profile.accessMode)" in engine
    assert "NativeRouteFailureCode.NO_COVERING_ROUTING_PACK" in engine
    assert "NativeRouteFailureCode.NO_COMPATIBLE_ROUTING_PACK" in engine
    assert "SingleCurrentRoutingPackActor" in engine
    assert "private var current: CurrentActor<T>? = null" in registry
    assert "current = CurrentActor(key, created)" in registry
    assert "MutableMap" not in registry
    assert ".withTileExtract(pack.tileArchive.absolutePath)" in engine
    assert "ValhallaProfilePolicies.forProfile(request.profile)" in engine
    assert "Executors" not in engine


def test_public_bridge_reports_pack_ids_without_paths_and_release_stays_disabled() -> (
    None
):
    boundary = (KOTLIN / "NativeRouteEngine.kt").read_text()
    protocol = (KOTLIN / "BridgeProtocol.kt").read_text()
    release = (RELEASE_KOTLIN / "NativeRouteEngineFactory.kt").read_text()
    assert 'NO_COVERING_ROUTING_PACK("no_covering_routing_pack")' in boundary
    assert "val installedPackIds: List<String>" in boundary
    assert "val packId: String" in boundary
    assert '"installed_pack_count"' in protocol
    assert '"installed_pack_ids"' in protocol
    assert '"supported_profile_ids"' in protocol
    assert '"pack_capabilities"' in protocol
    assert '"pack_id", result.packId' in protocol
    assert "absolutePath" not in protocol
    assert "enabled = false" in release
    assert "packs = emptyList()" in release
    assert "supportedProfiles = emptyList()" in release
    assert "NativeRouteFailureCode.ROUTING_PACK_UNAVAILABLE" in release
    assert "com.valhalla" not in release


def test_debug_browser_has_fixed_regional_actions_and_strict_replies() -> None:
    source = (STATIC / "local_routing.js").read_text()
    index = (STATIC / "index.html").read_text()
    app = (STATIC / "app.js").read_text()
    for marker in (
        "PARIS_OFFLINE_SMOKE_TEST",
        "CROSS_PACK_FAILURE_TEST",
        '"installed_pack_count"',
        '"installed_pack_ids"',
        '"no_covering_routing_pack"',
        "validPackIds",
        "safePackId",
        "pack ${reply.pack_id}",
    ):
        assert marker in source
    assert 'id="local-routing-paris-smoke-button"' in index
    assert 'id="local-routing-cross-pack-button"' in index
    assert "local-routing-paris-smoke-button" in app
    assert "local-routing-cross-pack-button" in app
    assert "globalThis.fetch" not in source
    assert "generatePlan" not in source


def test_tooling_builds_two_ignored_manifest_backed_packs() -> None:
    generic = (ROOT / "scripts/build_pr33_valhalla_pack.sh").read_text()
    both = (ROOT / "scripts/build_pr33_development_packs.sh").read_text()
    writer = (ROOT / "scripts/write_pr33_routing_pack_manifest.py").read_text()
    extractor = (ROOT / "scripts/extract_pr33_regional_pbf.py").read_text()
    ignore = (ROOT / ".gitignore").read_text()
    assert "data/valhalla/" in ignore
    assert "ghcr.io/valhalla/valhalla:3.6.3" in generic
    assert "PACK_DIRECTORY=$REPOSITORY_ROOT/data/valhalla/$PACK_ID" in generic
    assert 'if [ -L "$PACK_DIRECTORY" ]' in generic
    assert 'rm -f -- "$PACK_DIRECTORY/valhalla.json"' in generic
    assert 'rm -rf -- "$PACK_DIRECTORY/tiles"' in generic
    assert 'rm -f -- "$PACK_DIRECTORY/marly.osm.pbf"' in generic
    assert '"$PACK_DIRECTORY/manifest.json"' in generic
    assert "write_pr33_routing_pack_manifest.py" in generic
    assert "marly-dev-v1 2.00 48.80 2.16 48.94" in both
    assert "paris-dev-v1 2.25 48.80 2.42 48.92" in both
    assert '"schema_version": 2' in writer
    assert '"access_modes": ["foot", "bicycle"]' in writer
    assert "mjolnir-include-bicycle true" in generic
    assert '"engine": "valhalla"' in writer
    assert '"engine_version": "3.6.3"' in writer
    assert "class RegionalExtractHandler" in extractor
    assert "http" not in generic.lower()


def test_browser_harness_and_docs_cover_physical_acceptance() -> None:
    harness = (ROOT / "tests/browser/pr33_regional_routing_harness.js").read_text()
    html = (ROOT / "tests/browser/pr33_regional_routing_harness.html").read_text()
    docs = (ROOT / "docs/pr33-regional-routing-packs.md").read_text()
    for scenario in (
        "strict_regional_reply_parser",
        "regional_pack_switch_sequence",
        "cross_region_failure_without_fetch",
    ):
        assert f'scenarios.push("{scenario}")' in harness
    assert "A→A→B→B→A pack lifecycle is visible" in harness
    assert "regional failure makes no backend request" in harness
    assert "runPr33RegionalRoutingHarness" in html
    assert 'addEventListener("unhandledrejection"' in html
    assert "inclusive west, south, east, and north edges" in docs
    assert "smallest rectangular bounds area" in docs
    assert "PR33 physical acceptance passed on a physical Fairphone 6" in docs
    assert "Installed regional packs (2): marly-dev-v1, paris-dev-v1." in docs
    assert "No graph stitching, backend, network, or straight-line fallback" in docs
    assert "no_covering_routing_pack" in docs


def test_shared_transport_and_no_fallback_boundaries_remain_intact() -> None:
    transport = (STATIC / "native_bridge_transport.js").read_text()
    outing = (STATIC / "outing_native_bridge.js").read_text()
    local = (STATIC / "local_routing.js").read_text()
    runtime = transport + outing + local
    assert runtime.count("globalThis.sugargliderNative ?? null") == 1
    assert runtime.count("function cryptographicPageNonce(") == 1
    assert runtime.count("port.onmessage = receive") == 1
    combined_native = "\n".join(
        path.read_text()
        for source_set in (KOTLIN, DEBUG_KOTLIN, RELEASE_KOTLIN)
        for path in source_set.glob("*.kt")
    )
    assert "addJavascriptInterface" not in combined_native
    assert "fetch(" not in combined_native
    assert "straight-line" not in combined_native.lower()
