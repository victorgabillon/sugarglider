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


def test_shared_shell_generation_tracks_v60_cached_assets() -> None:
    worker = (STATIC_DIRECTORY / "service-worker.js").read_text()
    generation = re.search(
        r"const SHELL_CACHE = `\$\{SHELL_CACHE_PREFIX\}(v\d+)`;",
        worker,
    )
    assert generation is not None
    assert generation.group(1) == "v60"
    assert {
        name: _sha256(STATIC_DIRECTORY / name)
        for name in (
            "index.html",
            "app.js",
            "app_shell.js",
            "automatic_intent.js",
            "route_edit_history.js",
            "route_dock.js",
            "route_point_drag.js",
            "route_point_acquisition.js",
            "location_search.js",
            "location_search_dialog.js",
            "map_viewport.js",
            "route_results.js",
            "waypoint_editor.js",
            "trail_profile.js",
            "pwa_view.js",
            "region_screen.js",
            "state.js",
            "itinerary_draft.js",
            "itinerary_dialog.js",
            "map.js",
            "place_presentation.js",
            "poi_route_location.js",
            "local_places.js",
            "styles.css",
            "planner_location.js",
            "planner_profile.js",
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
            "native_itinerary_handoff.js",
            "api.js",
            "local_gpx_export.js",
            "local_gpx_client.js",
            "local_gpx_worker.js",
            "native_gpx_save.js",
            "public_profile_metadata.js",
        )
    } == {
        "itinerary_draft.js": (
            "d637856e680a5f29511e568daaec73043690f6ffb3e2d721c7f5399e3d42f366"
        ),
        "itinerary_dialog.js": (
            "5307b28b6bf2c00672938196eca9595201b7470e195bf5cc323107b500dde4cd"
        ),
        "route_dock.js": (
            "edca98e12782a796b3b7f7d2726ad6aee68be66636760aa39a66bea89c08a00d"
        ),
        "route_point_drag.js": (
            "a61aa834611a65ca108fbedf9645ae6f5a6188c15ba48795b0417e6489808862"
        ),
        "route_point_acquisition.js": (
            "5e05bb3a299e4db829cff750e412143407246022066347189351d4fc121d110a"
        ),
        "route_edit_history.js": (
            "7fb0be59fb37419d41bab341162c222d38f066e0c69c4037db3dcf4b3bfed58b"
        ),
        "automatic_intent.js": (
            "5e7ca9b810851ab81baf2a365e43f2a6aab7a89015e59a7dfe29fea3f4581c83"
        ),
        "poi_route_location.js": (
            "53321cda828128f43c93aee5b6f513885e77c1435777b7a9eac06c6f15a87e49"
        ),
        "place_presentation.js": (
            "c46bbb65e445bb793250ed9e508eff9272d6d76d0af89fef97b91daf9108a225"
        ),
        "local_places.js": (
            "57a69909891fc671ce6d93f615ed4c7789f75afb73d8a3027087d3a62e14876c"
        ),
        "local_planner.js": (
            "849b02b8f594400956eefdd61b99cc02eead3c92e9818e064a46bf4836c3e29b"
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
            "27ebdd61eb6a0ee6c98820f674413e880a82c9f928e475ec047eaf00b586a394"
        ),
        "location_search.js": (
            "635f5aaf5603cadbc3b77f035055251e54358b16a831d927e51fe6c44c031c36"
        ),
        "location_search_dialog.js": (
            "60924fa83037b8de5daa90cdfbcde5ab498a2134ff9a97b2b679e11b55c55b40"
        ),
        "app.js": ("e05d28adfe72c731d05daa8098509773a40725cac02e8d1a758b0c63438aaed6"),
        "region_screen.js": (
            "0cf6d527a0ea957e0222a31a8ffa2ee1d1a24b2118628c6fd70e4dbd9d5371c5"
        ),
        "pwa_view.js": (
            "b5f8919ea0c0b40b27559f3b506b2839731baea871554cfe3db7f5dc8c20b479"
        ),
        "trail_profile.js": (
            "cb2671c7d5c5905f5905942d7620c4bf2b98a57771165134275668faea965a25"
        ),
        "waypoint_editor.js": (
            "10fda3729bf2c8edd5ccd4d301bf37935692c612300b7501a75a7694636bd6e6"
        ),
        "route_results.js": (
            "2c77c0f3ef38b605a2858341e992a93fbc9c4c49cf77d3ba2ec6aab7f1076480"
        ),
        "map_viewport.js": (
            "afad92cd8b766c284fda15bd29cc73b1d9b66b43516450447646093d6005e86c"
        ),
        "app_shell.js": (
            "aa3c203a3042fb812c1088adc60fa3f07585ef014aec9a8584895e660862a7eb"
        ),
        "state.js": (
            "31925d46e487ee78406e316e57e58f74c7ac62d76fd71d24bcb356a1fa748b0b"
        ),
        "map.js": ("4332b8ab111da7e336235bbdc86a58c7d5ee756e812f1bf05021aa61412b7328"),
        "styles.css": (
            "f769eb208639e12ded9d041861974fc2860d77bb822994a31bdf4fec4e83c72c"
        ),
        "planner_profile.js": (
            "4183a1318f3aa49df52ca0a46329caaa4f6eee1bec1b49612c446562b1b0030a"
        ),
        "planner_location.js": (
            "ce28891c92263c084e33dd5ae9ad906a31e527253aeb321539599711e4500b9c"
        ),
        "local_routing.js": (
            "364b36d2750d24fd4b9e56b4cc8004fb98623eb26e3b0239749dbe6504a54a3b"
        ),
        "local_planning_context.js": (
            "aa6a94b9eee2821d68881b29d84346e8cbb7039a0200db2b0abcb0fd8373c2cd"
        ),
        "local_auto_tour.js": (
            "2b4c13d1ca70538c28e766937756bc2bece5a852ec8880a06330e2b8cf71fc54"
        ),
        "local_waypoint_route.js": (
            "45f94090ef1cf08fb405243cc610f366bc370c8dcc1ed12f7e929d6b0e271a8b"
        ),
        "regional_manifest.js": (
            "50dcb3ec6a87cd3382dfc25d6b70b525191d6c8b310132901eb34cbd7f686efc"
        ),
        "local_region_client.js": (
            "712f2b6dc1602c9b20fcd0033cb11602efad24f922dedaa60fb1a311bd560a31"
        ),
        "local_region_data.js": (
            "0bb2e9ff0e97a9375b802c2b9471f27620a2025e4398d5f58de8baf48b7910b6"
        ),
        "local_region_store.js": (
            "1d031f544b27c0c38ef37efd68b2d9d107843af4bbb8e12fe7c87428bab78eb5"
        ),
        "local_region_worker.js": (
            "b27c99b264c23a105893a1d923f9a3a4a76283dad7abb2a1e11427c71384c54a"
        ),
        "local_region_panel.js": (
            "43c5119cb1cf5ed4249dc00ae8a7d30741dd78b307a9305f31ee6a3988c456f6"
        ),
        "native_itinerary_handoff.js": (
            "835107e847c459772a794d9bacf4372b705cc6540db168c944b48d148fdb082d"
        ),
        "native_bridge_transport.js": (
            "367825db860c5ebc11d9fe629978c1bcc796d2854d396cbebb8db8e19fbd2dfd"
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
