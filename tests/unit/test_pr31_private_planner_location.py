"""Focused architecture contracts for PR31 private planner geolocation."""

import hashlib
import struct
from pathlib import Path

from sugarglider.web.routes import STATIC_DIRECTORY

ROOT = Path(__file__).resolve().parents[2]
CANONICAL_BRAND = ROOT / "assets" / "brand"
RUNTIME_BRAND = STATIC_DIRECTORY / "brand"
GPS_ASSETS = (
    "gps-recenter-default.png",
    "gps-recenter-active.png",
)
GPS_ASSET_HASHES = {
    "gps-recenter-default.png": (
        "9ed7206a9cf4881ccc021e4a6616f0520bad157ae1029d5f5a68258d7bf70c35"
    ),
    "gps-recenter-active.png": (
        "31e561518c0a17df07c4bd74bfd7ab69bcea5c2bf90f6c3822c0d14ea5170941"
    ),
}


def test_gps_assets_are_optimized_rgba_exact_canonical_runtime_copies() -> None:
    for filename in GPS_ASSETS:
        canonical = (CANONICAL_BRAND / filename).read_bytes()
        runtime = (RUNTIME_BRAND / filename).read_bytes()
        assert canonical == runtime
        assert runtime.startswith(b"\x89PNG\r\n\x1a\n")
        assert runtime[12:16] == b"IHDR"
        width, height, bit_depth, color_type = struct.unpack(">IIBB", runtime[16:26])
        assert (width, height, bit_depth, color_type) == (256, 256, 8, 6)
        assert len(runtime) < 150_000
        assert hashlib.sha256(runtime).hexdigest() == GPS_ASSET_HASHES[filename]


def test_private_location_lifecycle_is_latest_only_local_and_permission_gated() -> None:
    source = (STATIC_DIRECTORY / "planner_location.js").read_text()
    assert 'permissions.query({ name: "geolocation" })' in source
    assert "PLANNER_PERMISSION_QUERY_TIMEOUT_MS = 250" in source
    assert "await Promise.race([" in source
    assert 'permissionState === "granted"' in source
    assert "startWatch();" in source
    assert 'control?.addEventListener("click", activate)' in source
    assert "geolocation.watchPosition(" in source
    assert "geolocation.clearWatch(watch.id)" in source
    assert "PLANNER_LOCATION_WATCH_OPTIONS" in source
    assert "normalizeGeolocationPosition(position)" in source
    assert "let currentFix = null" in source
    assert "currentFix = Object.freeze({" in source
    assert 'windowTarget?.addEventListener("pagehide", suspend)' in source
    assert 'windowTarget?.addEventListener("pageshow", resume)' in source
    assert "manualMapInteraction" in source
    assert "followMode = false" in source
    for forbidden in (
        "fetch(",
        "XMLHttpRequest",
        "EventSource",
        "indexedDB",
        "localStorage",
        "sessionStorage",
        "position_outbox",
        "participant_token",
        "publish",
        "history",
        "/v2/",
    ):
        assert forbidden not in source


def test_root_planner_wires_private_location_without_public_page_autostart() -> None:
    application = (STATIC_DIRECTORY / "app.js").read_text()
    creation = application.index("plannerLocation = createPlannerLocationController")
    root_guard = application.rfind("if (!sharedSlug)", 0, creation)
    map_creation = application.index("const mapInitialized = initializeMap", creation)
    assert root_guard >= 0
    assert creation < map_creation
    assert "if (currentOutingSlug)" in application
    assert application.index("if (currentOutingSlug)") < creation
    assert "plannerLocation?.mapReady()" in application
    assert "plannerLocation?.manualMapInteraction()" in application
    assert "void plannerLocation?.initialize()" in application
    assert "renderPlannerCurrentLocation" in application
    assert "centerPlannerCurrentLocation" in application
    assert "clearPlannerCurrentLocation" in application


def test_map_uses_separate_exact_coordinate_avatar_and_accuracy_layers() -> None:
    source = (STATIC_DIRECTORY / "map.js").read_text()
    renderer = source[
        source.index("export function renderPlannerCurrentLocation") : source.index(
            "export function clearPlannerCurrentLocation"
        )
    ]
    assert "planner-current-location-current" in source
    assert "planner-current-location-accuracy-current" in source
    assert "PLANNER_LOCATION_AVATAR_LAYER" in source
    assert "outingLiveAvatarProperties(avatarKey)" in renderer
    assert "coordinates: [fix.coordinate.lon, fix.coordinate.lat]" in renderer
    assert "accuracyPolygon(" in renderer
    assert "fix.accuracy_m" in renderer
    assert "snap" not in renderer.lower()
    assert "project" not in renderer.lower()
    assert "fetch(" not in source
    center = source[
        source.index("export function centerPlannerCurrentLocation") : source.index(
            "export function plannerCurrentLocationDiagnostics"
        )
    ]
    assert "map.easeTo({" in center
    assert "Math.min(Math.max(currentZoom, 15), 18)" in center
    assert "event?.originalEvent" in source
    assert "handlers.onUserMapInteraction?.()" in source


def test_control_accessibility_pwa_and_browser_harness_are_explicit() -> None:
    index = (STATIC_DIRECTORY / "index.html").read_text()
    styles = (STATIC_DIRECTORY / "styles.css").read_text()
    worker = (STATIC_DIRECTORY / "service-worker.js").read_text()
    harness = (
        ROOT / "tests/browser/pr31_private_planner_location_harness.js"
    ).read_text()
    harness_html = (
        ROOT / "tests/browser/pr31_private_planner_location_harness.html"
    ).read_text()
    assert 'id="planner-location-control"' in index
    assert 'aria-pressed="false"' in index
    assert 'aria-busy="false"' in index
    assert 'id="planner-location-status"' in index
    assert "width: 48px; height: 48px" in styles
    assert "width: 40px; height: 40px" in styles
    assert 'data-state="acquiring"' in styles
    assert "prefers-reduced-motion: reduce" in styles
    assert "`${SHELL_CACHE_PREFIX}v16`" in worker
    assert '"/static/planner_location.js"' in worker
    for filename in GPS_ASSETS:
        assert f'"/static/brand/{filename}"' in worker
    for scenario in (
        "grantedPermissionScenario()",
        "promptPermissionScenario()",
        "deniedPermissionScenario()",
        "pendingPermissionsQueryScenario()",
        "lifecycleScenario()",
        "fallbackScenario()",
        "noPublicationScenario()",
        "responsiveControlScenario()",
    ):
        assert scenario in harness
    assert "[360, 800]" in harness
    assert "[1440, 900]" in harness
    assert "runPr31PrivatePlannerLocationHarness" in harness_html
    assert 'addEventListener("unhandledrejection"' in harness_html


def test_android_webview_geolocation_is_exact_origin_foreground_only() -> None:
    kotlin = ROOT / "android/app/src/main/java/io/github/victorgabillon/sugarglider"
    activity = (kotlin / "MainActivity.kt").read_text()
    coordinator = (kotlin / "WebGeolocationPermissionCoordinator.kt").read_text()
    combined = activity + coordinator
    assert "setGeolocationEnabled(true)" in activity
    assert "onGeolocationPermissionsShowPrompt" in activity
    assert "ServerOrigin.parse(" in activity
    assert "requestedOrigin = normalizedRequestedOrigin" in activity
    assert "val canonicalSourceOrigin = ServerOrigin.parse(" in activity
    assert "sourceOrigin.toString()," in activity
    assert "canonicalSourceOrigin," in activity
    assert "callback.invoke(requestedOrigin, allow, allow)" in activity
    assert "configuredOrigin = configuredOrigin" in activity
    assert "Manifest.permission.ACCESS_COARSE_LOCATION" in activity
    assert "Manifest.permission.ACCESS_FINE_LOCATION" in activity
    assert "REQUEST_WEB_GEOLOCATION_PERMISSION" in activity
    assert "GeolocationPermissions.getInstance().clearAll()" in activity
    assert "requestedOrigin != configuredOrigin" in coordinator
    assert "navigationEpoch" in coordinator
    assert "webViewIdentity" in coordinator
    assert "pending != null" in coordinator
    assert "pending?.resolve(false)" in coordinator
    foreground = activity[
        activity.index("private fun foregroundGeolocationClient") : activity.index(
            "private fun openExternal"
        )
    ]
    for forbidden in (
        "ACCESS_BACKGROUND_LOCATION",
        "POST_NOTIFICATIONS",
        "LocationSharingService",
        "NativeTrackingEngine",
        "NativeOutingApi",
    ):
        assert forbidden not in foreground
    assert "addJavascriptInterface" not in combined
