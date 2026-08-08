"""Static Android/native bridge trust and privacy contracts for PR27."""

import re
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ANDROID = ROOT / "android"
APP = ANDROID / "app" / "src" / "main"
KOTLIN = APP / "java" / "io" / "github" / "victorgabillon" / "sugarglider"
STATIC = ROOT / "src" / "sugarglider" / "web" / "static"
ANDROID_NAME = "{http://schemas.android.com/apk/res/android}name"
TOOLS_NODE = "{http://schemas.android.com/tools}node"


def test_android_project_is_pinned_and_targets_api_36() -> None:
    build = (ANDROID / "app" / "build.gradle.kts").read_text()
    root_build = (ANDROID / "build.gradle.kts").read_text()
    assert 'applicationId = "io.github.victorgabillon.sugarglider"' in build
    assert "compileSdk = 36" in build
    assert "targetSdk = 36" in build
    assert "minSdk = 26" in build
    assert "JavaVersion.VERSION_17" in build
    for forbidden in ('+"', "latest.release", "SNAPSHOT", "-alpha", "-beta", "-rc"):
        assert forbidden not in build + root_build


def test_manifest_has_only_expected_permissions_and_nonexported_location_service() -> (
    None
):
    root = ET.parse(APP / "AndroidManifest.xml").getroot()
    permissions = {
        node.attrib[ANDROID_NAME]
        for node in root.findall("uses-permission")
        if node.attrib.get(TOOLS_NODE) != "remove"
    }
    assert permissions == {
        "android.permission.INTERNET",
        "android.permission.ACCESS_COARSE_LOCATION",
        "android.permission.ACCESS_FINE_LOCATION",
        "android.permission.FOREGROUND_SERVICE",
        "android.permission.FOREGROUND_SERVICE_LOCATION",
        "android.permission.POST_NOTIFICATIONS",
    }
    application = root.find("application")
    assert application is not None
    service = application.find("service")
    assert service is not None
    android = "{http://schemas.android.com/apk/res/android}"
    assert service.attrib[f"{android}exported"] == "false"
    assert service.attrib[f"{android}foregroundServiceType"] == "location"
    text = (APP / "AndroidManifest.xml").read_text()
    assert "ACCESS_BACKGROUND_LOCATION" not in text
    assert "BOOT_COMPLETED" not in text
    assert 'android:usesCleartextTraffic="false"' in text


def test_debug_cleartext_policy_is_isolated_from_main_and_release() -> None:
    debug_manifest = ANDROID / "app" / "src" / "debug" / "AndroidManifest.xml"
    debug_policy = (
        ANDROID
        / "app"
        / "src"
        / "debug"
        / "res"
        / "xml"
        / "network_security_config.xml"
    )
    assert 'android:usesCleartextTraffic="true"' in debug_manifest.read_text()
    assert 'cleartextTrafficPermitted="true"' in debug_policy.read_text()
    assert not (
        ANDROID / "app" / "src" / "main" / "res" / "xml" / "network_security_config.xml"
    ).exists()


def test_bridge_uses_origin_checked_webkit_listener_without_javascript_interface() -> (
    None
):
    activity = (KOTLIN / "MainActivity.kt").read_text()
    protocol = (KOTLIN / "BridgeProtocol.kt").read_text()
    combined = "\n".join(path.read_text() for path in KOTLIN.glob("*.kt"))
    assert "WebViewCompat.addWebMessageListener" in activity
    assert "WebViewCompat.removeWebMessageListener" in activity
    assert "isMainFrame" in activity
    assert "System.identityHashCode(sourceView)" in activity
    assert "sourceOrigin.toString()" in activity
    assert "addJavascriptInterface" not in combined
    assert "startFields" in protocol and '"owner_token"' not in protocol
    replies = protocol[
        protocol.index("fun reply(") : protocol.index("private fun parseStart")
    ]
    assert '"participant_token"' not in replies


def test_native_http_contract_is_redirect_and_cookie_safe() -> None:
    api = (KOTLIN / "NativeOutingApi.kt").read_text()
    runtime = (KOTLIN / "NativeRuntime.kt").read_text()
    assert "connection.instanceFollowRedirects = false" in api
    assert '"X-Sugarglider-Participant-Token"' in api
    for path in ("/v2/outings/", "/participants/", "/position", "/live"):
        assert path in api
    assert "CookieHandler.setDefault(null)" in runtime
    assert "connectTimeout" in api and "readTimeout" in api
    assert "disconnect()" in api


def test_service_is_not_sticky_and_has_no_background_job_or_history() -> None:
    service = (KOTLIN / "LocationSharingService.kt").read_text()
    engine = (KOTLIN / "NativeTrackingEngine.kt").read_text()
    combined = "\n".join(path.read_text() for path in KOTLIN.glob("*.kt"))
    assert "START_NOT_STICKY" in service
    assert "ServiceCompat.startForeground" in service
    assert "FOREGROUND_SERVICE_TYPE_LOCATION" in service
    assert "NativeTrackingEngine(" in service
    assert "stopSelfResult(capturedStartId)" in service
    assert "ServiceStartIdGuard" in service
    assert 'status.copy(state = "stopping")' in service
    assert "publicationIntervalMs: Long = 5_000L" in engine
    assert "ScheduledThreadPoolExecutor(1)" in engine
    assert "LatestOnlyPending" in engine
    for forbidden in (
        "WorkManager",
        "AlarmManager",
        "WakeLock",
        "ACCESS_BACKGROUND_LOCATION",
        "BOOT_COMPLETED",
        "coordinateHistory",
        "breadcrumb",
    ):
        assert forbidden not in combined


def test_secure_store_is_aes_gcm_keystore_atomic_and_latest_only() -> None:
    store = (KOTLIN / "SecureTrackingStore.kt").read_text()
    assert 'Cipher.getInstance("AES/GCM/NoPadding")' in store
    assert 'KeyStore.getInstance("AndroidKeyStore")' in store
    assert "AtomicFile" in store
    assert "SecureRandom" in store
    assert "clearMatchingSample" in store
    assert "clearMatchingSession" in store
    fields = store[
        store.index("private val sessionFields") : store.index(
            "private val sampleFields"
        )
    ]
    for forbidden in ("owner_token", "join_token", "invitation", "history"):
        assert forbidden not in fields


def test_browser_native_module_preserves_default_browser_boundary() -> None:
    bridge = (STATIC / "outing_native_bridge.js").read_text()
    tracker = (STATIC / "outing_tracking.js").read_text()
    controller = (STATIC / "outing_controller.js").read_text()
    assert "globalThis.sugargliderNative ?? null" in bridge
    assert "if (!await initialize()) return null" in bridge
    assert "navigator.geolocation" not in bridge
    assert "EventSource" not in bridge
    assert "participant_token" in bridge
    assert "participant_token" not in bridge[bridge.index("function parseReply") :]
    assert "navigator.geolocation" in tracker
    assert "tracker.start(receipt" in controller
    assert "nativeTrackingBridge.start" in controller
    assert "nativeStatusBusy(state.nativeServiceStatus)" in controller


def test_native_stopping_state_blocks_start_and_server_change() -> None:
    activity = (KOTLIN / "MainActivity.kt").read_text()
    primitives = (KOTLIN / "TrackingPrimitives.kt").read_text()
    models = (KOTLIN / "TrackingModels.kt").read_text()
    view = (STATIC / "outing_view.js").read_text()
    assert "current.isNativeBusy()" in activity
    assert 'current.state == "stopping"' in activity
    assert '"stop_in_progress"' in activity
    assert "currentStatus = current" in activity
    assert "ServerChangePolicy.allowed" in activity
    assert "fun allowed(currentStatus: NativeTrackingStatus)" in primitives
    assert '"stopping"' in models[models.index("NATIVE_BUSY_STATES") :]
    assert "|| state.outingTrackingTransitionPending" in view


def test_bridge_requests_are_page_scoped_and_terminal_cleanup_is_exact() -> None:
    bridge = (STATIC / "outing_native_bridge.js").read_text()
    protocol = (KOTLIN / "BridgeProtocol.kt").read_text()
    activity = (KOTLIN / "MainActivity.kt").read_text()
    controller = (STATIC / "outing_controller.js").read_text()
    assert "cryptoObject.getRandomValues(bytes)" in bridge
    assert "`web-${pageNonce}-${requestCounter}`" in bridge
    assert "data class Key(val pageNonce: String, val requestId: String)" in protocol
    assert "override fun onPageStarted" in activity
    assert "invalidateBridgePage()" in activity
    assert "acknowledgeTerminalFailure" in bridge
    assert "createRetainedTerminalFailureProcessor" in controller
    assert "runBestEffortStorage([" in controller
    assert "onStorageFailure: reportOptionalStorageFailure" in controller
    assert "processing = new Set()" in bridge
    assert "completed = new Set()" in bridge
    assert "applicationState.outingParticipantReceipt = null" in bridge
    assert "applyNativeTerminalFailureToCurrentPage(state, failure)" in controller
    assert (
        "state.outingOwnerReceipt"
        not in controller[
            controller.index(
                "async function applyNativePermanentFailure"
            ) : controller.index("function applyNativeStartRejection")
        ]
    )


def test_pr27_browser_harness_covers_native_selection_and_stale_ownership() -> None:
    harness = (ROOT / "tests" / "browser" / "pr27_native_bridge_harness.js").read_text()
    html = (ROOT / "tests" / "browser" / "pr27_native_bridge_harness.html").read_text()
    assert harness.count('scenarios.push("') == 17
    for scenario in (
        "ordinary_browser_uses_no_native_bridge",
        "explicit_start_uses_native_message",
        "reload_get_status_does_not_restart",
        "page_scoped_ledger_across_reload",
        "stale_start_reply_ignored_after_stop",
        "status_cannot_mutate_another_outing",
        "production_projection_isolates_another_outing",
        "terminal_failure_survives_page_and_acknowledges",
        "terminal_cleanup_preserves_newer_and_owner_authority",
        "terminal_storage_failure_is_retryable",
        "terminal_acknowledgement_failure_is_retryable",
        "terminal_success_ignores_duplicate",
        "stale_terminal_cannot_mutate_newer_authority",
        "stopping_status_is_globally_busy",
        "native_status_creates_no_event_source",
    ):
        assert f'scenarios.push("{scenario}")' in harness
    assert 'addEventListener("unhandledrejection"' in html


def test_no_secret_fixture_looks_like_real_authority() -> None:
    tests = "\n".join(
        path.read_text() for path in (ANDROID / "app" / "src" / "test").rglob("*.kt")
    )
    assert "synthetic" in tests
    assert re.search(r"participant_token_[A-Za-z0-9_-]+", tests)
