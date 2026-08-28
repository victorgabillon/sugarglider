"""Static privacy, cache, packaging, and runtime contracts for PR26."""

import hashlib
import json
import re
import struct
from pathlib import Path

from sugarglider.web.routes import STATIC_DIRECTORY

ROOT = Path(__file__).resolve().parents[2]
VENDOR = STATIC_DIRECTORY / "vendor" / "maplibre-gl-4.7.1"
PWA_MODULES = (
    "offline_snapshots.js",
    "outing_durable_session.js",
    "pwa_controller.js",
    "pwa_network.js",
    "pwa_runtime.js",
    "pwa_store.js",
    "pwa_view.js",
    "service_worker_policy.js",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _png_dimensions(path: Path) -> tuple[int, int]:
    payload = path.read_bytes()
    assert payload.startswith(b"\x89PNG\r\n\x1a\n")
    assert payload[12:16] == b"IHDR"
    return struct.unpack(">II", payload[16:24])


def _core_assets(worker: str) -> set[str]:
    block = worker[
        worker.index("const CORE_ASSETS") : worker.index("function navigationResponse")
    ]
    return set(re.findall(r'"(/[^"]+)"', block))


def test_exact_maplibre_distribution_and_deterministic_icons() -> None:
    assert {path.name for path in VENDOR.iterdir() if path.is_file()} == {
        "LICENSE.txt",
        "README.md",
        "maplibre-gl.css",
        "maplibre-gl.js",
    }
    assert _sha256(VENDOR / "maplibre-gl.js") == (
        "be9633c4d870e26fb37f1cfe5c5a77181667114003ea16207ac7850d8da8add1"
    )
    assert _sha256(VENDOR / "maplibre-gl.css") == (
        "576b085fdd9487a65a19215328c1e086c07ce5bf6da09b666b3806d3d008dae9"
    )
    assert _sha256(VENDOR / "LICENSE.txt") == (
        "ee5fc05a0677eaf69601d2c7db0d9ecd6cc27c3abc1d0733bc9ed34707cf8ef2"
    )
    assert "maplibre-gl@4.7.1" in (VENDOR / "README.md").read_text()
    icons = STATIC_DIRECTORY / "pwa"
    assert _png_dimensions(icons / "icon-192.png") == (192, 192)
    assert _png_dimensions(icons / "icon-512.png") == (512, 512)
    assert _sha256(icons / "icon-192.png") == (
        "6d1778c5727bd4300ea47fbc99235a0565a9a68dc75f279c28e338b55ffcaa47"
    )
    assert _sha256(icons / "icon-512.png") == (
        "92f9a8b44925b336e9841f2606111c0aa15008075d1caebe422cec065eaa9922"
    )


def test_manifest_is_capability_free_and_root_scoped() -> None:
    manifest = json.loads(
        (STATIC_DIRECTORY / "manifest.webmanifest").read_text(encoding="utf-8")
    )
    assert manifest["id"] == manifest["start_url"] == manifest["scope"] == "/"
    assert manifest["display"] == "standalone"
    assert manifest["background_color"] == "#f2eee3"
    assert manifest["theme_color"] == "#214b3b"
    assert {icon["sizes"] for icon in manifest["icons"]} >= {"192x192", "512x512"}
    assert all(
        marker not in manifest[field]
        for field in ("id", "start_url")
        for marker in ("?", "#")
    )
    serialized = json.dumps(manifest).lower()
    for forbidden in (
        "token",
        "capability",
        "participant",
        "outing_slug",
        "share_target",
        "protocol_handler",
        "file_handler",
    ):
        assert forbidden not in serialized


def test_worker_policy_is_root_shell_only_and_has_no_background_authority() -> None:
    worker = (STATIC_DIRECTORY / "service-worker.js").read_text()
    policy = (STATIC_DIRECTORY / "service_worker_policy.js").read_text()
    for event_name in ("install", "activate", "fetch", "message"):
        marker = f'self.addEventListener("{event_name}"'
        assert marker in worker
        assert all(
            marker not in (STATIC_DIRECTORY / name).read_text() for name in PWA_MODULES
        )
    for forbidden in (
        "indexedDB",
        "participant_token",
        "owner_token",
        "join_token",
        "X-Sugarglider-Participant-Token",
        "X-Sugarglider-Outing-Owner-Token",
        "X-Sugarglider-Outing-Join-Token",
        "X-Saved-Route-Owner-Token",
        "EventSource",
        "geolocation",
        "watchPosition",
        "sync",
        "periodicSync",
        "push",
        "notification",
        "WebSocket",
        "sendBeacon",
    ):
        assert forbidden not in worker
    assert 'request.method !== "GET"' in policy
    assert "url.origin !== origin" in policy
    assert 'pathname.startsWith("/v1/")' in policy
    assert 'pathname.startsWith("/v2/")' in policy
    assert 'request.mode === "navigate"' in policy
    assert "fetchRequest(request).catch(" in policy
    assert "response.ok" in policy and 'response.type !== "basic"' in policy
    assert (
        "skipWaiting"
        not in worker[worker.index('"install"') : worker.index('"activate"')]
    )
    assert "name.startsWith(SHELL_CACHE_PREFIX)" in worker
    assert "self.clients.claim()" in worker
    assert "caches.match(" not in worker
    assert "createCurrentCacheAccess(caches, SHELL_CACHE)" in worker
    for header in (
        "authorization",
        "cookie",
        "x-sugarglider-participant-token",
        "x-sugarglider-outing-owner-token",
        "x-sugarglider-outing-join-token",
        "x-saved-route-owner-token",
    ):
        assert f'"{header}"' in policy


def test_shared_shell_generation_tracks_pr31_cached_assets() -> None:
    worker = (STATIC_DIRECTORY / "service-worker.js").read_text()
    generation = re.search(
        r"const SHELL_CACHE = `\$\{SHELL_CACHE_PREFIX\}(v\d+)`;",
        worker,
    )
    assert generation is not None
    assert generation.group(1) == "v12"
    assert {
        name: _sha256(STATIC_DIRECTORY / name)
        for name in ("index.html", "styles.css", "planner_location.js")
    } == {
        "index.html": (
            "f892b599151f690bd6572b7341300ebea695b193895d9176fd41e00cdaf00e7f"
        ),
        "styles.css": (
            "8fb571cba5249148b4ae1aef7b20a42ddced4e1fd1d10184bbdb2570e27ace72"
        ),
        "planner_location.js": (
            "ce28891c92263c084e33dd5ae9ad906a31e527253aeb321539599711e4500b9c"
        ),
    }


def test_precache_covers_index_and_static_module_graph() -> None:
    worker = (STATIC_DIRECTORY / "service-worker.js").read_text()
    core = _core_assets(worker)
    index = (STATIC_DIRECTORY / "index.html").read_text()
    assert "unpkg.com" not in index
    assert "/static/vendor/maplibre-gl-4.7.1/maplibre-gl.js" in index
    assert "/static/vendor/maplibre-gl-4.7.1/maplibre-gl.css" in index
    nonessential = {
        "/static/brand/sugarglider-banner.png",
        "/static/brand/sugarglider-flying-map.png",
    }
    index_assets = set(re.findall(r'(?:src|href)="(/static/[^"]+)"', index))
    assert index_assets - nonessential <= core

    pending = ["app.js"]
    visited: set[str] = set()
    while pending:
        name = pending.pop()
        if name in visited:
            continue
        visited.add(name)
        source = (STATIC_DIRECTORY / name).read_text()
        pending.extend(
            match
            for match in re.findall(r'from "\./([^"]+\.js)"', source)
            if match not in visited
        )
    assert {f"/static/{name}" for name in visited} <= core
    assert (
        "ROOT_SHELL"
        in worker[
            worker.index("const CORE_ASSETS") : worker.index(
                "function navigationResponse"
            )
        ]
    )
    assert {
        "/static/vendor/maplibre-gl-4.7.1/maplibre-gl.js",
        "/static/vendor/maplibre-gl-4.7.1/maplibre-gl.css",
        "/static/pwa/icon-192.png",
        "/static/pwa/icon-512.png",
    } <= core
    assert not any(path.startswith(("/v1/", "/v2/", "/o/", "/r/")) for path in core)
    assert not any("tile" in path or path.endswith(".pbf") for path in core)


def test_browser_persistence_ownership_is_narrow() -> None:
    sources = {
        path.name: path.read_text()
        for path in STATIC_DIRECTORY.glob("*.js")
        if path.name != "service-worker.js"
    }
    assert {name for name, source in sources.items() if "indexedDB" in source} == {
        "pwa_store.js"
    }
    assert {
        name for name, source in sources.items() if "navigator.serviceWorker" in source
    } == {"pwa_controller.js"}
    assert {
        name for name, source in sources.items() if "storageManager?.persist" in source
    } == {"pwa_controller.js"}
    combined = "\n".join(sources.values())
    for forbidden in ("localStorage", "sessionStorage", "document.cookie"):
        assert forbidden not in combined
    store = sources["pwa_store.js"]
    for object_store in (
        "public_runtime",
        "offline_snapshots",
        "participant_sessions",
        "position_outbox",
        "trail_profile",
    ):
        assert object_store in store
    durable = sources["outing_durable_session.js"]
    outbox_fields = durable[
        durable.index("const OUTBOX_FIELDS") : durable.index(
            "export function createParticipantSessionRepository"
        )
    ]
    assert '"participant_token"' not in outbox_fields
    assert '"sequence"' not in outbox_fields
    assert "removeIf(" in durable
    assert "record?.sample_id === sampleId" in durable
    assert "putLatestOutboxIfSessionMatches(" in store
    assert "removeSessionAndRelatedOutbox(" in store
    assert "touch" not in durable
    assert "replaceAndRemovePrevious(" in store
    assert "putBounded(" in store
    assert "captured_at) > Date.parse(value.queued_at)" in durable
    assert "age < 0 || age > resumeWindowMs" in durable


def test_reconnect_restore_and_worker_update_boundaries_are_explicit() -> None:
    application = (STATIC_DIRECTORY / "app.js").read_text()
    outing = (STATIC_DIRECTORY / "outing_controller.js").read_text()
    runtime = (STATIC_DIRECTORY / "pwa_runtime.js").read_text()
    controller = (STATIC_DIRECTORY / "pwa_controller.js").read_text()
    assert "render: renderPwaApplication" in application
    assert "ownsOutboxPresence: outingOutboxPresenceIsCurrent" in application
    assert (
        'if (!slug || state.offlineSnapshotKind !== "saved_route")' not in application
    )
    assert 'if (!slug || state.offlineSnapshotKind !== "outing")' not in outing
    restore = runtime[
        runtime.index(
            "export async function restoreRememberedParticipant"
        ) : runtime.index("export async function rememberParticipant")
    ]
    for forbidden in ("state.", "renderPwaState"):
        assert forbidden not in restore
    assert "isCurrent()" in restore
    assert 'updateViaCache: "none"' in controller
    assert "activationRequested = false" in controller
    assert "createPwaStorageRuntime" in runtime
    assert "createMemoryPwaStore" in runtime
    assert "storageUnavailable" in runtime
    assert "installAuthoritativeOutingSnapshot(" in outing
    assert "clearUnavailableSavedRouteState(state, slug)" in application
    assert "readOptionalStorage(" in application


def test_final_review_async_privacy_boundaries_are_explicit() -> None:
    application = (STATIC_DIRECTORY / "app.js").read_text()
    outing = (STATIC_DIRECTORY / "outing_controller.js").read_text()
    tracking = (STATIC_DIRECTORY / "outing_tracking.js").read_text()
    durable = (STATIC_DIRECTORY / "outing_durable_session.js").read_text()
    policy = (STATIC_DIRECTORY / "service_worker_policy.js").read_text()
    assert ".then(() => storeResponse(request, response.clone()))" in policy
    assert ".catch(() => {})" in policy
    assert "putLatestOutboxIfSessionMatches" in durable
    assert "removeSessionAndRelatedOutbox" in durable
    assert "const removedReceipt = installAuthoritativeOutingSnapshot" in outing
    assert "clearUnavailableSavedRouteState(state, slug);" in application
    assert "clearRoutes();" in application
    assert "void forgetRememberedParticipant(" not in outing
    assert "void removeOfflineSnapshot(" not in outing
    permanent = tracking[
        tracking.index(
            "async function handlePermanentParticipantFailure"
        ) : tracking.index("function retainLatestSample")
    ]
    assert permanent.index("await discardDurableSample(") < permanent.index(
        "onPermanentFailure?.({"
    )
    assert "if (!ownsPublish(operation)) return" not in permanent
    publish_catch = tracking[
        tracking.index(
            "} catch (error) {", tracking.index("async function performPublish")
        ) : tracking.index(
            "} finally {", tracking.index("async function performPublish")
        )
    ]
    assert publish_catch.index('error?.code === "outing_not_found"') < (
        publish_catch.index("if (!ownsPublish(operation)) return outcome;")
    )
    recovery = tracking[
        tracking.index("async function recoverSequence") : tracking.index(
            "async function handlePermanentParticipantFailure"
        )
    ]
    recovery_catch = recovery[recovery.index("} catch (error) {") :]
    assert recovery_catch.index('error?.code === "outing_not_found"') < (
        recovery_catch.index("if (!ownsPublish(operation)) return;")
    )


def test_public_snapshot_and_participant_privacy_boundaries_are_explicit() -> None:
    snapshots = (STATIC_DIRECTORY / "offline_snapshots.js").read_text()
    durable = (STATIC_DIRECTORY / "outing_durable_session.js").read_text()
    assert "rejectForbiddenPublicData(normalized)" in snapshots
    assert "canonicalSecurityKey" in snapshots
    for forbidden_key in (
        "token",
        "capability",
        "liveposition",
        "liveevent",
        "eventcursor",
        "replaycursor",
    ):
        assert f'"{forbidden_key}"' in snapshots
    assert "MAXIMUM_SNAPSHOTS = 8" in snapshots
    assert "MAXIMUM_SNAPSHOT_BYTES" in snapshots
    assert "participantIds.has" in snapshots
    assert "validGeometry" in snapshots
    session_fields = durable[
        durable.index("const SESSION_FIELDS") : durable.index("const OUTBOX_FIELDS")
    ]
    assert session_fields.count('"participant_token"') == 1
    for forbidden_key in ("owner_token", "join_token", "invite_path"):
        assert forbidden_key not in durable


def test_pr26_modules_and_runtime_harness_are_focused() -> None:
    assert {
        name: len((STATIC_DIRECTORY / name).read_text().splitlines())
        for name in PWA_MODULES
        if len((STATIC_DIRECTORY / name).read_text().splitlines()) >= 800
    } == {}
    harness = (ROOT / "tests/browser/pr26_pwa_runtime_harness.js").read_text()
    html = (ROOT / "tests/browser/pr26_pwa_runtime_harness.html").read_text()
    assert harness.count('scenarios.push("') == 63
    assert "runPr26PwaRuntimeHarness" in harness
    assert 'addEventListener("unhandledrejection"' in html
    assert 'addEventListener("error"' in html
    assert "window.setTimeout(resolve, 0)" in html
    assert html.index('addEventListener("unhandledrejection"') < html.index(
        '<script type="module">'
    )
    for scenario in (
        "stale_remembered_restore_cannot_mutate_new_outing",
        "future_outbox_timestamp_rejected",
        "concurrent_outbox_old_write_cannot_replace_new",
        "nine_concurrent_snapshot_saves_leave_eight",
        "publish_not_found_forgets_remembered_session",
        "sequence_recovery_not_found_forgets_session",
        "pwa_prune_failure_falls_back_to_memory",
        "static_network_success_survives_cache_write_failure",
        "cross_tab_forget_prevents_stale_outbox_write",
        "reconnect_removed_participant_stops_tracker",
        "saved_route_reconnect_not_found_clears_display",
        "stop_during_publish_not_found_still_forgets_identity",
        "stop_before_publish_not_found_still_forgets_identity",
        "stop_before_sequence_recovery_not_found_still_forgets_identity",
        "membership_removal_storage_rejection_is_handled",
    ):
        assert f'scenarios.push("{scenario}")' in harness


def test_pr26_documentation_and_repository_rules_exist() -> None:
    documentation = ROOT / "docs" / "pr26-pwa-offline-resilience.md"
    assert documentation.exists()
    text = documentation.read_text().lower()
    for phrase in (
        "latest-only",
        "foreground",
        "background sync",
        "offline",
        "maplibre",
        "forget",
        "pr27",
    ):
        assert phrase in text
    rules = (ROOT / "AGENTS.md").read_text()
    for phrase in (
        "explicit offline",
        "remembered participant",
        "latest-only",
        "service worker",
        "background geolocation",
    ):
        assert phrase in rules
