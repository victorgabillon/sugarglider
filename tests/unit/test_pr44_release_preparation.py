"""Release privacy boundaries that must survive future manifest changes."""

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "android" / "app" / "src" / "main"
ANDROID = "{http://schemas.android.com/apk/res/android}"


@pytest.mark.parametrize("mode", ["cloud-backup", "device-transfer"])
def test_no_android_backup_mode_exports_any_application_storage(mode: str) -> None:
    manifest = ET.parse(APP / "AndroidManifest.xml").getroot()
    application = manifest.find("application")
    assert application is not None
    assert application.attrib[f"{ANDROID}allowBackup"] == "false"
    assert application.attrib[f"{ANDROID}fullBackupContent"] == "false"
    assert (
        application.attrib[f"{ANDROID}dataExtractionRules"]
        == "@xml/data_extraction_rules"
    )
    rules = ET.parse(APP / "res" / "xml" / "data_extraction_rules.xml").getroot()
    selected = rules.find(mode)
    assert selected is not None
    assert not selected.findall("include")
    assert {
        (node.attrib["domain"], node.attrib["path"])
        for node in selected.findall("exclude")
    } == {
        (domain, ".")
        for domain in (
            "root",
            "file",
            "database",
            "sharedpref",
            "external",
            "device_root",
            "device_file",
            "device_database",
            "device_sharedpref",
        )
    }


def test_dead_renderer_recovery_preserves_authority_and_export_boundaries() -> None:
    source = (
        APP / "java/io/github/victorgabillon/sugarglider/MainActivity.kt"
    ).read_text()
    recovery = source.split("override fun onRenderProcessGone", 1)[1].split(
        "override fun onPageStarted", 1
    )[0]
    assert recovery.index("webGeolocationPermissions.discard()") < recovery.index(
        "invalidateBridgePage()"
    )
    assert "wasCurrent && gpxDocumentSaver.hasPendingWork()" in recovery
    assert "if (wasCurrent)" in recovery
    assert (
        "showRendererRecovery(origin, bridgeNavigationEpoch, pendingDocument)"
        in recovery
    )
    assert "WebView.setWebContentsDebuggingEnabled(BuildConfig.DEBUG)" in source
    assert "page_recovery_gpx" in source
    assert "briefly retains recent updates so viewers can reconnect" in source
    assert "Only the latest current position is retained" not in source
