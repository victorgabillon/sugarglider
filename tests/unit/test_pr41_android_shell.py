"""The packaged shell contains public, current assets with canonical defaults."""

import json
import re
from pathlib import Path

import pytest

from sugarglider.web.build_android_shell import (
    ANDROID_APP_ORIGIN,
    STATIC,
    render_android_shell_assets,
    render_android_ui_config,
)
from sugarglider.web.models import UiConfig

ROOT = Path(__file__).resolve().parents[2]


def test_android_shell_allowlist_matches_current_shared_runtime() -> None:
    source = (ROOT / "android" / "shell-assets.txt").read_text()
    assert source == render_android_shell_assets()
    paths = [path for path in source.splitlines() if not path.startswith("#")]
    assert len(paths) == len(set(paths))
    assert "android_app.js" in paths and "local_plan_worker.js" in paths
    assert "service-worker.js" not in paths
    assert len([path for path in paths if "LICENSE" in path]) == 5
    for path in paths:
        assert (STATIC / path).is_file()
        assert not (STATIC / path).is_symlink()
        assert not path.endswith((".gpx", ".pmtiles", ".sqlite", ".tar", ".gz"))
        if path.endswith(".pbf"):
            assert path.startswith("fonts/Open Sans Semibold/")


def test_bundled_html_images_are_available_without_network_fallback() -> None:
    html = (STATIC / "index.html").read_text()
    image_paths = {
        path.removeprefix("/static/")
        for path in re.findall(r'<img\b[^>]*\bsrc="(/static/[^"\n]+)"', html)
    }
    assert image_paths
    assert image_paths <= set(render_android_shell_assets().splitlines())


def test_bundled_config_is_canonical_public_and_ignores_host_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = render_android_ui_config()
    monkeypatch.setenv("SUGARGLIDER_MAP_TILE_URL", "https://irrelevant.invalid/tiles")
    monkeypatch.setenv("SUGARGLIDER_SAVED_ROUTES_ENABLED", "true")
    assert render_android_ui_config() == expected
    assert (STATIC / "android_ui_config.json").read_text() == expected
    config = UiConfig.model_validate(json.loads(expected))
    assert config.tile_url_template.startswith(ANDROID_APP_ORIGIN + "/")
    assert not config.saved_routes_available
    assert not config.outings_available
    assert not config.outing_live_positions_available
    assert not config.poi_index_available and not config.nature_index_available


def test_bundled_origin_and_bridge_scope_are_explicit() -> None:
    kotlin = ROOT / "android/app/src/main/java/io/github/victorgabillon/sugarglider"
    activity = (kotlin / "MainActivity.kt").read_text()
    policy = (kotlin / "BundledShellPolicy.kt").read_text()
    web = (STATIC / "android_app.js").read_text()
    assert ANDROID_APP_ORIGIN in web
    assert 'const val HOST = "appassets.androidplatform.net"' in policy
    assert "savedInstanceState?.getBoolean(STATE_SHARING_SCREEN) == true" in activity
    assert "!BundledShellPolicy.acceptsOrigin(request, origin)" in activity
    assert (
        "if (origin == BundledShellPolicy.ORIGIN) NativeTrackingStatus.stopped()"
        in activity
    )
    for method in (
        "private fun broadcastStatus",
        "private fun broadcastTerminalFailure(\n",
    ):
        assert (
            "configuredOrigin == BundledShellPolicy.ORIGIN) return"
            in activity.split(method, 1)[1].split("\n    }", 1)[0]
        )
