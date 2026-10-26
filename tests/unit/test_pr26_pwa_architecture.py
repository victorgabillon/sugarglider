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


def test_shared_shell_generation_tracks_v119_cached_assets() -> None:
    worker = (STATIC_DIRECTORY / "service-worker.js").read_text()
    generation = re.search(
        r"const SHELL_CACHE = `\$\{SHELL_CACHE_PREFIX\}(v\d+)`;",
        worker,
    )
    assert generation is not None
    assert generation.group(1) == "v119"
    assert {
        name: _sha256(STATIC_DIRECTORY / name)
        for name in (
            "brand/profile-badges/olivier.png",
            "i18n.js",
            "translations.js",
            "index.html",
            "app.js",
            "adventure_model.js",
            "adventure_proposal.js",
            "adventure_grounding.js",
            "adventure_assessment.js",
            "adventure_controller.js",
            "adventure_intent.js",
            "adventure_elevation.js",
            "adventure_speech.js",
            "adventure_dialog.js",
            "adventure_results.js",
            "adventure_snapshot.js",
            "adventure_snapshot_validation.js",
            "adventure_snapshot_worker.js",
            "local_adventure_search.js",
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
            "terrain_attribution.js",
            "data_notices.js",
            "data_notice_registry.js",
            "state.js",
            "itinerary_draft.js",
            "itinerary_dialog.js",
            "map.js",
            "place_presentation.js",
            "place_capabilities.js",
            "poi_route_location.js",
            "local_places.js",
            "styles.css",
            "planner_location.js",
            "planner_profile.js",
            "local_routing.js",
            "local_auto_tour.js",
            "local_planning_context.js",
            "local_planner.js",
            "endpoint_snapping.js",
            "endpoint_adjustment_view.js",
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
            "elevation_profile.js",
            "elevation_view.js",
            "elevation_map_marker.js",
            "elevation_sampling.js",
            "elevation_sampling_worker.js",
            "route_elevation.js",
            "native_gpx_save.js",
            "public_profile_metadata.js",
        )
    } == {
        "brand/profile-badges/olivier.png": (
            "bc967b92f946ff80794202f982dc2089ee41111554f2f7a51e5874fda775a5dc"
        ),
        "elevation_profile.js": (
            "319176cc644c0c80ba464133c969de558e65e75d084e1ed699646301e3ee7b1b"
        ),
        "elevation_view.js": (
            "367b28f0056e8b0924b66ebf433c284db322e00219738d981a7a6a327b8c99bc"
        ),
        "elevation_map_marker.js": (
            "3e064a2be298eda3d3d64e335e478e35a9a0c3a23ff417d905ebe73314c641ba"
        ),
        "elevation_sampling.js": (
            "0b1d871c06793a74520622131405a85d8e533dffece1e89548e1f72651ae8959"
        ),
        "elevation_sampling_worker.js": (
            "a2c0a6fa37dec239e634a59816dc3ca3ea12819557cecc0341e68f1d1ab59511"
        ),
        "route_elevation.js": (
            "949bbfc150e01a062fd0e6c2bc82732328692d4538e86f8bc8a782b0821b0c22"
        ),
        "itinerary_draft.js": (
            "810768879886ea0a74df9ea102a273390f5e8efeefda9573e82541a9afbff8a1"
        ),
        "itinerary_dialog.js": (
            "f3551e7904a08cde405faaa9250a41ce8624daa3b084b506d525c4219afbf39c"
        ),
        "route_dock.js": (
            "194587c573ef4095b28bec859e6af43e5a6d7b77463b5020d46702019fff5673"
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
            "7299f2bcb62363a4d2a7e7d23bef48b12c035425aaeea84bf7fbbdbfb6e411aa"
        ),
        "poi_route_location.js": (
            "53321cda828128f43c93aee5b6f513885e77c1435777b7a9eac06c6f15a87e49"
        ),
        "place_capabilities.js": (
            "27c77b03322a8f63391b10f1e7f830a92292c3e755575f42d44d60e2cf708e5a"
        ),
        "place_presentation.js": (
            "1a4af6f227b3d8e07cece06d25819d464af55047fb50d66a1f5cf14055cc3b21"
        ),
        "local_places.js": (
            "57a69909891fc671ce6d93f615ed4c7789f75afb73d8a3027087d3a62e14876c"
        ),
        "local_planner.js": (
            "03bac667ff454b3efc8543b017d87aeec6fa63973c5f11409ac08eea0a999e35"
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
            "d1793cac80f1cba86ec77679fb90a69bb42c8c59b71ebd2b981b24a06917f87e"
        ),
        "local_candidate_evaluator.js": (
            "52128534fbf13f88178c86be1820005a7b48b6d91fa5f87ce1f5996e19dba5c2"
        ),
        "local_plan_publisher.js": (
            "d9521b42f10b933932835a3fa869102a50ea4135dee4dd524bbf2cd15c946e76"
        ),
        "local_plan_worker.js": (
            "3ca9645f88dbe2ff9f57e63190d04d2a5bcbdec017e072850bed0fa0ac1f7eb8"
        ),
        "local_plan_client.js": (
            "f47b62e8a6d7aa00deb7e1312e5eda57ca91fc59e082c465b4c161a791f7f0d0"
        ),
        "i18n.js": ("708543feff434012bfa950a16ac6156619f5475cc54d97f2f693db73e810e7b2"),
        "translations.js": (
            "6829df6ee1f2d63482c941a190e9dc14a3e388c757f337b0069cccf46b123578"
        ),
        "index.html": (
            "a003b4210c02901fac13408a9ce00bf970c23e07745dea07ae8e37aee1b0fef4"
        ),
        "location_search.js": (
            "635f5aaf5603cadbc3b77f035055251e54358b16a831d927e51fe6c44c031c36"
        ),
        "location_search_dialog.js": (
            "1511d1d554d7d22ffc327e413faf25eb4e43a342ff1236c31442900d5e1947ea"
        ),
        "endpoint_snapping.js": (
            "801dfb85e8531421b96417020e5356614a5d1ef4bcd91c0dc4ad53743a7d83f7"
        ),
        "endpoint_adjustment_view.js": (
            "8bd472674af25c55ed1ae8819ec128a61f14299f67bfdb3a8ee0a54d01e4a85b"
        ),
        "adventure_model.js": (
            "e327d50459f1d19704af3ec0cf2a9c06a0f35f2378b8dd7db50d9f5edf10df23"
        ),
        "adventure_proposal.js": (
            "718c55d35e5cfb43dd44461825cb95cbc972959cebaeaea96bade331a1dcd77d"
        ),
        "adventure_grounding.js": (
            "64560d708dbe0a46c91c8bb111351fcad22f7aaf1978abc3c32a089e22b639ca"
        ),
        "adventure_assessment.js": (
            "4d4d7abae5431c4a78e034377e389ef68ad218f6ef98e331c5cb42a5eef20415"
        ),
        "adventure_controller.js": (
            "7f4947690feea30f7a638d154fffe969b50f406a811a74f877319cfca370e7f5"
        ),
        "adventure_intent.js": (
            "f858a28b903d8a255744a45b1a9bb2719c7158f02916414ce1e0ad10eb09c390"
        ),
        "adventure_elevation.js": (
            "ccc2a3c0bf48a6cbd01cbe9fc09a3d8688e31378cc99e9af3f990a85c1b01739"
        ),
        "adventure_speech.js": (
            "886d1a7348fee81b78d8b8ee16cb2cc90655d8f49d720c1f6b8f5a89a8f516a2"
        ),
        "adventure_dialog.js": (
            "7120697a03a4a552a8dafa26ae9745dfd86c30cdf0c2181e1c233e356bc2096a"
        ),
        "adventure_results.js": (
            "04bb4626caf9556384590a948fc547e764b19788adcc75cd7fa47d6f16be7651"
        ),
        "adventure_snapshot.js": (
            "fd1610e5d2b3655fe7187561921bb2f69a153c3522749257efb788a40898597c"
        ),
        "adventure_snapshot_validation.js": (
            "df01e8d8c152bb3343ceb714fcb245ad1d4a076e8297940990fefbceb13c4bb7"
        ),
        "adventure_snapshot_worker.js": (
            "212e4c0a9cd53aec3b19384119d2921a27293eb054cb9e0ce399c10edd933d3b"
        ),
        "local_adventure_search.js": (
            "faae64c661a211505d82bad9b78f1c7d8533904182db967b6ff0b603ef08086b"
        ),
        "app.js": ("c19f5cd663459b6cc8704b97b3bbecd30674b483d4930dccb8be0b19414022ab"),
        "region_screen.js": (
            "ac0aad40280167eca27482eb4256512b48453a2883a6a588ab5b2e3a98fa1301"
        ),
        "data_notices.js": (
            "5ccbfa08a5d4cbf952968f38bf9bdc8ba66156f333befc8219447fe76040528d"
        ),
        "data_notice_registry.js": (
            "6f19be0ab5ad54e21e7327eacfca0956f7cfae0828fb16ae593c376b0f050278"
        ),
        "terrain_attribution.js": (
            "1de488084d35553193788917299b329b204bc4008c0b86a9ca31215e41ba0be2"
        ),
        "pwa_view.js": (
            "c03e2520c4266b1a77909b5fa72e6b86477b775bf5e17c740413efc115087d51"
        ),
        "trail_profile.js": (
            "ff93e74a11cd81023625cd4d5054f9258fb19f327b1e775eb557002f42ce628b"
        ),
        "waypoint_editor.js": (
            "5c2b4d2a92114944f933e84622458c320729b31633be636cbab4dffb4c6cac0a"
        ),
        "route_results.js": (
            "b7612e9b9c15ba8050019110480bcde2d0f11f058910f5b5c5a1552ae10f4b01"
        ),
        "map_viewport.js": (
            "b106a498748884750ec77f283ca8bae0892a66bc6e08d12f6d8efca34b74b874"
        ),
        "app_shell.js": (
            "0f366f76e092051913c114987361b2d7dc171945d6d029bd4a4d0f897b5c4ca7"
        ),
        "state.js": (
            "ae7c5e7acc9d5e91957c275b227957a95855aee7853f15178858a0c52c0cc1c3"
        ),
        "map.js": ("1f3c8bb2894224d109f39f3c84d2a89fcd75a0090ae238c16f1e25eef083e430"),
        "styles.css": (
            "319bd69cfb6ff205eba4ca5385891bb7eb631521d90456691a2b6f675dcd1ed2"
        ),
        "planner_profile.js": (
            "4183a1318f3aa49df52ca0a46329caaa4f6eee1bec1b49612c446562b1b0030a"
        ),
        "planner_location.js": (
            "aa5d61cc14c996caff67ea9597b7b6b3c4623d7e64637b655fb99d05c86cd95a"
        ),
        "local_routing.js": (
            "364b36d2750d24fd4b9e56b4cc8004fb98623eb26e3b0239749dbe6504a54a3b"
        ),
        "local_planning_context.js": (
            "aa6a94b9eee2821d68881b29d84346e8cbb7039a0200db2b0abcb0fd8373c2cd"
        ),
        "local_auto_tour.js": (
            "3f427eacfb2ce4b6a2017aabd50151c12caa06f092e397fc52c951a052dbdbfe"
        ),
        "local_waypoint_route.js": (
            "c08b6e2616f505ad0bdac906881b9fc6e5322e6c0548162c85beb34de2e53fb5"
        ),
        "regional_manifest.js": (
            "253de7af724800456d99f4189331aed4f49169cbc5736327c257f22d2e0cdbde"
        ),
        "local_region_client.js": (
            "f9058ebcd70619d84af0a381f298770197e0f387ff6fbd39f1f2d857336f24f5"
        ),
        "local_region_data.js": (
            "15c1cee2e20651a3015f4ac64d00941f24e8d7938d273eff6d2786dc0ead4982"
        ),
        "local_region_store.js": (
            "ca9f071e5ca170d0bb60f2bae7d81f91d5e8caa721ea4ed41a2a10860204e9d7"
        ),
        "local_region_worker.js": (
            "a281330d20e49e9ca7f177a752ed1711801cae0d724c61af28fb8ab41ddc198a"
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
