"""Static contracts for the narrow PR32 on-device routing spike."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ANDROID = ROOT / "android/app"
KOTLIN = ANDROID / "src/main/java/io/github/victorgabillon/sugarglider"
STATIC = ROOT / "src/sugarglider/web/static"


def test_debug_packaging_installs_beside_unchanged_release_app() -> None:
    build = (ANDROID / "build.gradle.kts").read_text()
    release_strings = (ANDROID / "src/main/res/values/strings.xml").read_text()
    debug_strings = (ANDROID / "src/debug/res/values/strings.xml").read_text()
    docs = (ROOT / "docs/pr32-on-device-routing-spike.md").read_text()
    release_id = "io.github.victorgabillon.sugarglider"
    debug_id = f"{release_id}.debug"
    assert f'applicationId = "{release_id}"' in build
    assert f'namespace = "{release_id}"' in build
    assert 'applicationIdSuffix = ".debug"' in build
    assert 'versionNameSuffix = "-debug"' in build
    assert '<string name="app_name">Sugarglider</string>' in release_strings
    assert '<string name="app_name">Sugarglider Debug</string>' in debug_strings
    assert f"run-as {debug_id}" in docs
    assert f"am force-stop {debug_id}" in docs
    assert f"run-as {release_id} " not in docs
    assert f"am force-stop {release_id}\n" not in docs


def test_valhalla_is_pinned_debug_arm64_only_and_release_is_disabled() -> None:
    build = (ANDROID / "build.gradle.kts").read_text()
    debug = (
        ANDROID
        / "src/debug/java/io/github/victorgabillon/sugarglider"
        / "NativeRouteEngineFactory.kt"
    ).read_text()
    release = (
        ANDROID
        / "src/release/java/io/github/victorgabillon/sugarglider"
        / "NativeRouteEngineFactory.kt"
    ).read_text()
    registry = (KOTLIN / "RoutingPackRegistry.kt").read_text()
    assert 'debugImplementation("io.github.rallista:valhalla-mobile:0.5.1")' in build
    assert 'ndk.abiFilters += "arm64-v8a"' in build
    assert 'buildConfigField("boolean", "LOCAL_ROUTING_EXPERIMENT", "true")' in build
    assert 'buildConfigField("boolean", "LOCAL_ROUTING_EXPERIMENT", "false")' in build
    policy = (
        ANDROID
        / "src/debug/java/io/github/victorgabillon/sugarglider"
        / "ValhallaProfilePolicy.kt"
    ).read_text()
    assert "CostingModel.pedestrian" in policy
    assert 'ENGINE_VERSION = "0.5.1/valhalla-3.6.3"' in debug
    assert '"routing-packs"' in debug
    assert ".withTileExtract(pack.tileArchive.absolutePath)" in debug
    assert 'ROUTING_PACK_ENGINE_VERSION = "3.6.3"' in registry
    assert "enabled = false" in release
    assert "com.valhalla" not in release


def test_native_boundary_is_bounded_explicit_and_has_no_fallback() -> None:
    boundary = (KOTLIN / "NativeRouteEngine.kt").read_text()
    protocol = (KOTLIN / "BridgeProtocol.kt").read_text()
    activity = (KOTLIN / "MainActivity.kt").read_text()
    assert "interface NativeRouteEngine" in boundary
    assert 'HIKE("hike", LocalRouteAccessMode.FOOT)' in boundary
    assert "MAX_LOCAL_ROUTE_VERTICES = 20_000" in boundary
    assert "MAX_LOCAL_ROUTE_REPLY_BYTES = 512 * 1_024" in boundary
    for code in (
        "invalid_request",
        "unsupported_profile",
        "routing_pack_unavailable",
        "no_covering_routing_pack",
        "no_compatible_routing_pack",
        "no_route",
        "route_too_large",
        "routing_busy",
        "routing_failure",
    ):
        assert code in boundary
    assert '"local_route" -> parseLocalRoute' in protocol
    assert '"get_local_route_capabilities"' in protocol
    assert "Executors.newSingleThreadExecutor()" in activity
    assert "pendingLocalRoute !== operation" in activity
    assert "postToBridge(channel, reply)" in activity
    assert "val canonicalSourceOrigin = ServerOrigin.parse(" in activity
    assert "sourceOrigin.toString()," in activity
    assert "BuildConfig.ALLOW_HTTP," in activity
    combined = boundary + protocol + activity
    assert "addJavascriptInterface" not in combined
    assert "fetch(" not in combined
    assert "straight" not in combined.lower()


def test_experiment_is_isolated_private_and_never_replaces_generate() -> None:
    module = (STATIC / "local_routing.js").read_text()
    transport = (STATIC / "native_bridge_transport.js").read_text()
    app = (STATIC / "app.js").read_text()
    index = (STATIC / "index.html").read_text()
    map_source = (STATIC / "map.js").read_text()
    assert 'id="local-routing-experiment"' in index
    assert 'id="local-routing-smoke-button"' in index
    assert "Run Marly offline smoke test" in index
    assert "Local routing experiment" in index
    assert "Debug Android only" in index
    assert "createLocalRoutingExperiment" in app
    assert "state.points.map" in app
    assert "renderLocalExperimentalRoute" in map_source
    assert "globalThis.sugargliderNative ?? null" in transport
    assert "transport = nativeBridgeTransport" in module
    assert "MAX_ROUTE_VERTICES = 20_000" in module
    assert "globalThis.fetch" not in module
    assert "MARLY_OFFLINE_SMOKE_TEST" in module
    assert "Object.freeze({ lat: 48.8715, lon: 2.0965 })" in module
    assert "Object.freeze({ lat: 48.8983, lon: 2.0969 })" in module
    assert "route_version: LOCAL_ROUTE_VERSION" in module
    assert "points: points.map" in module
    assert "requestSmokeTest" in module
    assert "Native routing handshake unavailable." in module
    assert "if (bridge.nativeAvailable)" in module
    assert "Local Valhalla experiment failed (${explicitCode})" in module
    assert "generatePlan" not in module
    assert "participant_token" not in module
    assert "navigator.geolocation" not in module
    assert "LocationSharingService" not in module


def test_page_has_one_shared_native_transport_for_both_clients() -> None:
    transport = (STATIC / "native_bridge_transport.js").read_text()
    outing = (STATIC / "outing_native_bridge.js").read_text()
    local = (STATIC / "local_routing.js").read_text()
    client_sources = outing + local
    runtime_sources = transport + client_sources
    assert runtime_sources.count("globalThis.sugargliderNative ?? null") == 1
    assert runtime_sources.count("function cryptographicPageNonce(") == 1
    assert runtime_sources.count("port.onmessage = receive") == 1
    assert "nativeBridgeTransport = createNativeBridgeTransport()" in transport
    assert "`web-${pageNonce}-${requestCounter}`" in transport
    assert 'postRequest("hello", {}, {' in transport
    assert "const pending = new Map()" in transport
    assert "cancelOwner" in transport
    assert "subscribeUnsolicited" in transport
    assert "isUnsolicitedRequestId" in transport
    assert "parseReply," in outing
    assert "parseReply: parseLocalRoutingReply" in local
    assert client_sources.count('from "./native_bridge_transport.js"') == 2
    assert "port.onmessage" not in client_sources
    assert "pageNonce" not in client_sources


def test_pack_is_reproducible_ignored_and_not_embedded() -> None:
    ignore = (ROOT / ".gitignore").read_text()
    builder = (ROOT / "scripts/build_pr32_marly_valhalla_pack.sh").read_text()
    regional_builder = (ROOT / "scripts/build_pr33_valhalla_pack.sh").read_text()
    extractor = (ROOT / "scripts/extract_pr33_regional_pbf.py").read_text()
    normalizer = (ROOT / "scripts/normalize_pr32_valhalla_tar.py").read_text()
    docs = (ROOT / "docs/pr32-on-device-routing-spike.md").read_text()
    assert "data/valhalla/" in ignore
    assert "build_pr33_valhalla_pack.sh" in builder
    assert "marly-dev-v1 2.00 48.80 2.16 48.94" in builder
    assert "ghcr.io/valhalla/valhalla:3.6.3" in regional_builder
    assert "valhalla_build_tiles" in regional_builder
    assert "valhalla_build_extract" in regional_builder
    assert "normalize_pr32_valhalla_tar.py" in regional_builder
    assert "write_pr33_routing_pack_manifest.py" in regional_builder
    assert 'header[148:156] = b"        "' in normalizer
    assert "sha256sum" in regional_builder and "stat -c" in regional_builder
    assert "class Bounds" in extractor
    assert "bounds.west <= node.location.lon <= bounds.east" in extractor
    assert "No routing pack is embedded in the APK" in docs
    assert not list(ANDROID.rglob("valhalla_tiles.tar"))


def test_pr32_browser_harness_covers_required_failure_and_ownership_cases() -> None:
    harness = (ROOT / "tests/browser/pr32_local_routing_harness.js").read_text()
    html = (ROOT / "tests/browser/pr32_local_routing_harness.html").read_text()
    assert harness.count('scenarios.push("') == 11
    for scenario in (
        "native_local_routing_unavailable",
        "native_handshake_unavailable_is_diagnostic",
        "shared_transport_outing_first",
        "shared_transport_local_first",
        "unsolicited_tracking_while_local_routing",
        "valid_local_route_zero_backend_fetches",
        "marly_smoke_test_fixed_offline_cold_warm",
        "no_route_is_explicit",
        "malformed_native_reply_rejected",
        "stale_page_reply_ignored",
        "geometry_rendered_only_for_current_request",
    ):
        assert scenario in harness
    assert "globalThis.fetch = async" in harness
    assert "smoke test ignores normal planner state" in harness
    assert "same smoke action can run twice" in harness
    assert "local reply cannot resolve outing request" in harness
    assert "outing reply cannot resolve local request" in harness
    assert "unknown web request is ignored" in harness
    assert "status and terminal failure both reach outing subscriber" in harness
    assert "runPr32LocalRoutingHarness" in html
    assert 'addEventListener("unhandledrejection"' in html


def test_pr32_shell_generation_precaches_local_bridge() -> None:
    worker = (STATIC / "service-worker.js").read_text()
    assert "`${SHELL_CACHE_PREFIX}v18`" in worker
    assert '"/static/native_bridge_transport.js"' in worker
    assert '"/static/local_routing.js"' in worker
