"""Focused local-profile, avatar-artwork, and live-map contracts for PR30."""

import hashlib
from pathlib import Path

from sugarglider.web.routes import STATIC_DIRECTORY

ROOT = Path(__file__).resolve().parents[2]
CANONICAL_BADGES = ROOT / "assets" / "brand" / "profile-badges"
RUNTIME_BADGES = STATIC_DIRECTORY / "brand" / "profile-badges"
BADGE_HASHES = {
    "blue.png": "04fb4e73a98ed60fb3903cc92b13fa322131dff06231cc13e7ba5a857bcd1e76",
    "forest.png": "ed23f6346d4182f479cc4f3d567be3686b8ec9e1c556e41756a7753b5dc5054c",
    "orange.png": "7341ee2b77171515e5308d924a82a1a78769d32134d8ea757457daffa7755df9",
    "tomato.png": "483bfee9e59dc914f0e634714c6990b972cea35eab66675ba43df72d4e29b129",
    "mask.png": "0cf50dc763279290f655daeeda6e4044fcbd319b799a6457109ac547204c7a24",
}
AVATAR_LABELS = {
    "blue": "Lake",
    "forest": "Forest",
    "orange": "Vico",
    "tomato": "Jime",
    "mask": "Lezca",
}
AVATAR_DEFAULT_NAMES = {
    "blue": None,
    "forest": None,
    "orange": "Vico",
    "tomato": "Jime",
    "mask": "Lezca",
}


def test_profile_badges_are_exact_canonical_runtime_copies() -> None:
    assert {path.name for path in CANONICAL_BADGES.glob("*.png")} == set(BADGE_HASHES)
    assert {path.name for path in RUNTIME_BADGES.glob("*.png")} == set(BADGE_HASHES)
    for name, expected_hash in BADGE_HASHES.items():
        canonical = (CANONICAL_BADGES / name).read_bytes()
        runtime = (RUNTIME_BADGES / name).read_bytes()
        assert canonical == runtime
        assert hashlib.sha256(runtime).hexdigest() == expected_hash
        assert runtime.startswith(b"\x89PNG\r\n\x1a\n")


def test_profile_shell_is_local_versioned_and_never_starts_tracking() -> None:
    html = (STATIC_DIRECTORY / "index.html").read_text()
    profile = (STATIC_DIRECTORY / "trail_profile.js").read_text()
    application = (STATIC_DIRECTORY / "app.js").read_text()
    assert 'id="trail-profile-dialog"' in html
    assert 'id="edit-trail-profile"' in html
    assert 'id="setup-join-profile"' in html
    assert "Welcome to Sugarglider" in html
    assert "visible to anyone with the public link" in html
    assert html.count('name="trail-profile-avatar"') == 5
    for key, label in AVATAR_LABELS.items():
        assert f'value="{key}"' in html
        assert f"/static/brand/profile-badges/{key}.png" in html
        assert f'aria-label="{label} trail badge"' in html
        assert f'alt="{label} Sugarglider trail badge"' in html
        assert f'<span aria-hidden="true">{label}</span>' in html
    assert "TRAIL_PROFILE_SCHEMA_VERSION = 1" in profile
    assert "display_name: value.display_name.trim()" in profile
    assert "avatar_key: value.avatar_key" in profile
    assert "avatarDefaultName(input.value)" in profile
    assert "participant_token" not in profile
    assert "owner_token" not in profile
    assert "join_token" not in profile
    assert "geolocation" not in profile
    assert "watchPosition" not in profile
    assert "publishOutingPosition" not in profile
    assert "requireSetup: !currentOutingSlug && !currentSharedRouteSlug" in application


def test_profile_persistence_uses_the_existing_focused_store_boundary() -> None:
    store = (STATIC_DIRECTORY / "pwa_store.js").read_text()
    profile = (STATIC_DIRECTORY / "trail_profile.js").read_text()
    assert 'trailProfile: "trail_profile"' in store
    assert "const DATABASE_VERSION = 2" in store
    assert "indexedDB" not in profile
    assert "localStorage" not in profile
    assert "sessionStorage" not in profile
    assert "PWA_STORES.trailProfile" in profile
    assert "store.durable" in profile
    assert "currentProfile = profile" in profile


def test_outing_payloads_cards_and_offline_legacy_default_are_avatar_aware() -> None:
    requests = (STATIC_DIRECTORY / "outings.js").read_text()
    cards = (STATIC_DIRECTORY / "outing_view.js").read_text()
    offline = (STATIC_DIRECTORY / "offline_snapshots.js").read_text()
    assert "participant_avatar_key: avatarKey" in requests
    assert "avatar_key: avatarKey" in requests
    assert 'avatar.className = "outing-participant-avatar"' in cards
    assert "avatarImageUrl(participant.avatar_key)" in cards
    assert "participant?.avatar_key === undefined" in offline
    assert "participant.avatar_key = DEFAULT_AVATAR_KEY" in offline
    assert "!isAvatarKey(participant.avatar_key)" in offline


def test_live_map_uses_five_avatar_symbols_with_a_visible_blue_fallback() -> None:
    avatar = (STATIC_DIRECTORY / "avatar.js").read_text()
    map_source = (STATIC_DIRECTORY / "map.js").read_text()
    for key in ("blue", "forest", "orange", "tomato", "mask"):
        assert f'"{key}"' in avatar
        assert "outing-avatar-${normalizeAvatarKey(value)}" in avatar
    for key, label in AVATAR_LABELS.items():
        assert f'{key}: "{label}"' in avatar
    for key, default_name in AVATAR_DEFAULT_NAMES.items():
        expected = "null" if default_name is None else f'"{default_name}"'
        assert f"{key}: {expected}" in avatar
    assert "AVATAR_LABELS[normalizeAvatarKey(value)]" in avatar
    assert "AVATAR_DEFAULT_NAMES[normalizeAvatarKey(value)]" in avatar
    assert "for (const avatarKey of AVATAR_KEYS)" in map_source
    assert "if (map.hasImage(imageId)) continue" in map_source
    assert "pixelRatio: 8" in map_source
    assert "const avatarKey = normalizeAvatarKey(value)" in map_source
    assert "...outingLiveAvatarProperties(participant.avatar_key)" in map_source
    marker = map_source[
        map_source.index("id: OUTING_LIVE_POSITION_MARKER_LAYER") : map_source.index(
            "id: OUTING_LIVE_POSITION_SELECTED_LAYER"
        )
    ]
    assert 'type: "symbol"' in marker
    assert '"icon-image": ["get", "avatar_image"]' in marker
    assert '"icon-opacity": ["get", "opacity"]' in marker
    assert "export function outingLiveAvatarProperties" in map_source
    assert "export function outingAvatarRegistrationIds" in map_source
    assert "DEFAULT_AVATAR_KEY" in map_source
    assert '"circle-color": ["get", "color"]' in map_source
    live_renderer = map_source[
        map_source.index(
            "export function renderOutingLivePositions"
        ) : map_source.index("export function clearOutingLivePositions")
    ]
    assert (
        "coordinates: [position.coordinate.lon, position.coordinate.lat]"
        in live_renderer
    )
    assert "geometry: accuracyPolygon(" in live_renderer
    assert "const freshness = liveFreshness" in live_renderer
    assert "position.participant_id === selectedParticipantId" in live_renderer
    assert "participant.avatar_key" in live_renderer
    assert "trailProfileAvatarKey" not in live_renderer
    assert "history" not in live_renderer.lower()


def test_pr30_shell_cache_and_framework_free_harness_cover_new_assets() -> None:
    worker = (STATIC_DIRECTORY / "service-worker.js").read_text()
    harness = (ROOT / "tests/browser/pr30_trail_profiles_harness.js").read_text()
    html = (ROOT / "tests/browser/pr30_trail_profiles_harness.html").read_text()
    assert "`${SHELL_CACHE_PREFIX}v9`" in worker
    for name in BADGE_HASHES:
        assert f'"/static/brand/profile-badges/{name}"' in worker
    assert '"/static/avatar.js"' in worker
    assert '"/static/trail_profile.js"' in worker
    for scenario in (
        "profileValidationScenario()",
        "profileUiScenario()",
        "localProfileStorageScenario()",
        "outingPayloadScenario()",
        "profileMarkupScenario()",
        "avatarFallbackScenario()",
    ):
        assert scenario in harness
    assert "runPr30TrailProfilesHarness" in html
    assert 'addEventListener("unhandledrejection"' in html
