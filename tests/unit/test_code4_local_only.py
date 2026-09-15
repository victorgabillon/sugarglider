"""Wiring contracts for the local-only Android product, alongside behavioral tests."""

import json
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "android/app/src/main"
KOTLIN = APP / "java/io/github/victorgabillon/sugarglider"
ANDROID = "{http://schemas.android.com/apk/res/android}"


def test_no_sharing_component_or_deep_link_in_any_packaged_manifest() -> None:
    for path in (ROOT / "android/app/src").glob("*/AndroidManifest.xml"):
        manifest = ET.parse(path).getroot()
        assert not manifest.findall(".//service")
        assert not manifest.findall(".//receiver")
        assert not manifest.findall(".//data")
        for permission in manifest.findall("uses-permission"):
            assert permission.get(ANDROID + "name") not in {
                "android.permission.FOREGROUND_SERVICE",
                "android.permission.FOREGROUND_SERVICE_LOCATION",
                "android.permission.ACCESS_BACKGROUND_LOCATION",
                "android.permission.POST_NOTIFICATIONS",
            }


def test_ui_restore_configuration_and_bridge_use_the_fixed_product_boundary() -> None:
    source = (KOTLIN / "MainActivity.kt").read_text()
    for signature in ("showServerConfiguration()", "openSharingServer()"):
        body = source.split(f"private fun {signature} {{", 1)[1]
        assert body.lstrip().startswith(
            "if (!V1ReleasePolicy.sharingEnabled) { openPlanner(); return }"
        )
    assert "if (V1ReleasePolicy.sharingEnabled) serverChrome.addView" in source
    assert "if (V1ReleasePolicy.sharingEnabled &&" in source
    assert source.split("private fun deepLinkSlug", 1)[1].splitlines()[1].strip() == (
        "if (!V1ReleasePolicy.sharingEnabled) return null"
    )
    assert (
        source.split("private fun openServer(origin: String) {", 1)[1]
        .lstrip()
        .startswith("if (!V1ReleasePolicy.allowsOrigin(origin))")
    )
    assert source.index("if (!V1ReleasePolicy.acceptsBridge(request, origin))") < (
        source.index("when (request)")
    )


def test_service_and_durable_state_are_inert_before_initialization() -> None:
    service = (KOTLIN / "LocationSharingService.kt").read_text()
    assert service.index("if (!V1ReleasePolicy.sharingEnabled)") < service.index(
        "publisher = NativeOutingApi()"
    )
    start = service.split("override fun onStartCommand", 1)[1]
    assert start.index("if (!V1ReleasePolicy.sharingEnabled)") < start.index(
        "when (intent?.action)"
    )
    runtime = (KOTLIN / "NativeRuntime.kt").read_text()
    assert runtime.index("if (V1ReleasePolicy.sharingEnabled)") < runtime.index(
        "secureStore = AndroidSecureStateStore(this)"
    )
    config = json.loads(
        (ROOT / "src/sugarglider/web/static/android_ui_config.json").read_text()
    )
    assert config["outings_available"] is False
    assert config["saved_routes_available"] is False
