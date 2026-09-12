"""Static privacy, cache, packaging, and runtime contracts for PR26."""

import hashlib
import json
import re
import struct
from pathlib import Path

from sugarglider.web.routes import STATIC_DIRECTORY

ROOT = Path(__file__).resolve().parents[2]
VENDOR = STATIC_DIRECTORY / "vendor" / "maplibre-gl-6.4.1"
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
    expected = {
        "maplibre-gl.mjs": (
            "97e8b9a39ab8b823d6a0caf9c312237262bc9138a6162d9e29606f5f8d24127d"
        ),
        "maplibre-gl-shared.mjs": (
            "fcf4d81450df235da0aea74897cc23926774b5228d38ae1de6a7d701c5905785"
        ),
        "maplibre-gl-worker.mjs": (
            "ce4957017fe705ac2f9ebef206cca966d08d8621756c39326a78cf09757e7d75"
        ),
        "maplibre-gl.css": (
            "8e2dbbab312dc57656fbb76e9fa5308c75c9d7c7ba5808a7d55bcdb64cc813fa"
        ),
        "LICENSE.txt": (
            "ee5fc05a0677eaf69601d2c7db0d9ecd6cc27c3abc1d0733bc9ed34707cf8ef2"
        ),
    }
    assert {path.name for path in VENDOR.iterdir() if path.is_file()} == {
        *expected,
        "README.md",
    }
    assert {name: _sha256(VENDOR / name) for name in expected} == expected
    assert "maplibre-gl@6.4.1" in (VENDOR / "README.md").read_text()
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


def test_shared_shell_generation_tracks_v41_cached_assets() -> None:
    worker = (STATIC_DIRECTORY / "service-worker.js").read_text()
    generation = re.search(
        r"const SHELL_CACHE = `\$\{SHELL_CACHE_PREFIX\}(v\d+)`;",
        worker,
    )
    assert generation is not None
    assert generation.group(1) == "v41"
    assert {
        name: _sha256(STATIC_DIRECTORY / name)
        for name in (
            "index.html",
            "app.js",
            "state.js",
            "map.js",
            "styles.css",
            "planner_location.js",
            "local_routing.js",
            "local_auto_tour.js",
            "local_planning_context.js",
            "local_planner.js",
            "canonical_numbers.js",
            "local_analysis_templates.js",
            "local_plan_geometry.js",
            "local_candidate_enrichment.js",
            "local_candidate_evaluator.js",
            "local_plan_publisher.js",
            "local_plan_worker.js",
            "local_plan_client.js",
            "local_waypoint_route.js",
            "regional_manifest.js",
            "local_region_client.js",
            "local_region_data.js",
            "local_region_store.js",
            "local_region_worker.js",
            "local_region_panel.js",
            "native_bridge_transport.js",
            "api.js",
            "local_gpx_export.js",
            "local_gpx_client.js",
            "local_gpx_worker.js",
            "native_gpx_save.js",
            "public_profile_metadata.js",
        )
    } == {
        "local_planner.js": (
            "a2ea147a2cf3d987d38ac1f3b3980112984db3c3577ab8e171b6a9f53caaa20f"
        ),
        "canonical_numbers.js": (
            "0c45121c5e89d9dcbd23c126740a7f3760e8c31f9683d8206b70c6d253e65a26"
        ),
        "local_analysis_templates.js": (
            "6036c6d7fcf55a97514d29a57caba72e43f522ef9e811d60548886fe8f126e01"
        ),
        "local_plan_geometry.js": (
            "f48a33644581705ac0ba22a4c49625d4623850281dcca76d873f5c190dbe3f3a"
        ),
        "local_candidate_enrichment.js": (
            "2d71476066aa440bdebb28c26b1d0eac2b62c37dd1275b0ef8448aee3e7c2ef5"
        ),
        "local_candidate_evaluator.js": (
            "2b56af7f998db9a2d174670847608ed394de24b40fbed2c84e2242f1037b2788"
        ),
        "local_plan_publisher.js": (
            "4a7162832605f171f32158370b9bc80e606075fbeca78dd2a6b0019118911f30"
        ),
        "local_plan_worker.js": (
            "3ca9645f88dbe2ff9f57e63190d04d2a5bcbdec017e072850bed0fa0ac1f7eb8"
        ),
        "local_plan_client.js": (
            "f47b62e8a6d7aa00deb7e1312e5eda57ca91fc59e082c465b4c161a791f7f0d0"
        ),
        "index.html": (
            "47c31ee3e3673bbcefae8c0f2faf83dee81aa648e48c9703e60315ab3daa7a7f"
        ),
        "app.js": ("5fc0a7f5c09941702b98fc42673240a8a64d1a653c01eb87febdba247653051b"),
        "state.js": (
            "de724c096dd193347bdbdb9a424e873902ead40b30d48a339925da4d9aa58abd"
        ),
        "map.js": ("e7f38b7fa68c47d4b5a429d7561ca2a52dafd59a274bf6774061ec3c6ae944c8"),
        "styles.css": (
            "11026a66bc90cc66deb477e8d3602b9ebd65f72ed59990bd570b8a7eb9d37e4d"
        ),
        "planner_location.js": (
            "ce28891c92263c084e33dd5ae9ad906a31e527253aeb321539599711e4500b9c"
        ),
        "local_routing.js": (
            "364b36d2750d24fd4b9e56b4cc8004fb98623eb26e3b0239749dbe6504a54a3b"
        ),
        "local_planning_context.js": (
            "4daf16dd06654c1d4b857fd2b4497b87821c64aac9de0c73675b0b3a59add519"
        ),
        "local_auto_tour.js": (
            "2b4c13d1ca70538c28e766937756bc2bece5a852ec8880a06330e2b8cf71fc54"
        ),
        "local_waypoint_route.js": (
            "45f94090ef1cf08fb405243cc610f366bc370c8dcc1ed12f7e929d6b0e271a8b"
        ),
        "regional_manifest.js": (
            "f062cff8451b1a8039de394856654e07c0533f55ccfb82e25aa0e3f814e94787"
        ),
        "local_region_client.js": (
            "f034f2e2d05335d2f3b8384144f095708f1544fef93322819645265a6e7076ac"
        ),
        "local_region_data.js": (
            "81d76b750de4aba6ea5e701ae2a5319ae4fd9221073b06fc472f86148828f6bb"
        ),
        "local_region_store.js": (
            "1d031f544b27c0c38ef37efd68b2d9d107843af4bbb8e12fe7c87428bab78eb5"
        ),
        "local_region_worker.js": (
            "a463b22af5ef1f68b9199d9b1177df84ae7feb64fd4c41224e88bc14c63dfd11"
        ),
        "local_region_panel.js": (
            "43c5119cb1cf5ed4249dc00ae8a7d30741dd78b307a9305f31ee6a3988c456f6"
        ),
        "native_bridge_transport.js": (
            "485c4690f4b6c35a15c9800f1c7a7bb771814fe47d59fb419df5efe372e3b754"
        ),
        "api.js": ("2844e8cc44afc78de06e3ce24ff7e6040ce16c189fd84122b790404cdf76c297"),
        "local_gpx_export.js": (
            "edc7678c70a860e014aab54af907d6ebd953894e7f4eba0dff83372903eecfd1"
        ),
        "public_profile_metadata.js": (
            "2077a93dd9291b556d2cf5ebe29c317aeda3f96b356722a3fd069ff8963f41fa"
        ),
        "local_gpx_client.js": (
            "607a89cea494125a4fea99e717751f7f69a4c7d76a5325d6fceeef3f50b8d511"
        ),
        "native_gpx_save.js": (
            "63364ea3184de7c77903393b699d689b69f2996204b5f114b27173404e899d24"
        ),
        "local_gpx_worker.js": (
            "ad4769fc03bb5e205d4bcd4e9833256f96fe7931fa0cc53e9bc4cb5ca90bc0b2"
        ),
    }


def test_precache_covers_index_and_static_module_graph() -> None:
    worker = (STATIC_DIRECTORY / "service-worker.js").read_text()
    core = _core_assets(worker)
    index = (STATIC_DIRECTORY / "index.html").read_text()
    assert "unpkg.com" not in index
    assert '<script defer src="/static/vendor/maplibre-gl' not in index
    assert (
        'from "./vendor/maplibre-gl-6.4.1/maplibre-gl.mjs"'
        in (STATIC_DIRECTORY / "map.js").read_text()
    )
    assert "/static/vendor/maplibre-gl-6.4.1/maplibre-gl.css" in index
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
        for relative in re.findall(r'from\s*["\']\./([^"\']+\.m?js)["\']', source):
            dependency = (Path(name).parent / relative).as_posix()
            if dependency not in visited:
                pending.append(dependency)
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
        "/static/vendor/maplibre-gl-6.4.1/maplibre-gl.mjs",
        "/static/vendor/maplibre-gl-6.4.1/maplibre-gl-shared.mjs",
        "/static/vendor/maplibre-gl-6.4.1/maplibre-gl-worker.mjs",
        "/static/vendor/maplibre-gl-6.4.1/maplibre-gl.css",
        "/static/pwa/icon-192.png",
        "/static/pwa/icon-512.png",
    } <= core
    assert not any(path.startswith(("/v1/", "/v2/", "/o/", "/r/")) for path in core)
    packaged_glyphs = {
        "/static/fonts/Open%20Sans%20Semibold/0-255.pbf",
        "/static/fonts/Open%20Sans%20Semibold/256-511.pbf",
        "/static/fonts/Open%20Sans%20Semibold/8192-8447.pbf",
    }
    assert {path for path in core if path.endswith(".pbf")} == packaged_glyphs
    assert not any(path.endswith(".pmtiles") for path in core)
    assert "CORE_ASSETS.includes(new URL(request.url).pathname)" in worker


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
    } == {"map_pack_store.js", "pwa_controller.js"}
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
