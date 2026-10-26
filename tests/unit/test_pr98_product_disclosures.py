"""Release wording is checked alongside behavioral planner/bridge regressions."""

import json
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "android/app/src/main"
CONTRACT = (
    "After downloading a supported region, Sugarglider calculates routes, displays "
    "regional maps, analyzes elevation and exports GPX on the device without "
    "requiring an internet connection."
)


def normalized(text: str) -> str:
    return " ".join(text.split())


def test_approved_contract_is_consistent_in_product_and_android_privacy_ui() -> None:
    strings = {
        node.attrib["name"]: node.text or ""
        for node in ET.parse(APP / "res/values/strings.xml").getroot()
    }
    for relative in ("README.md", "docs/pr98-offline-capable-product.md"):
        assert CONTRACT in normalized((ROOT / relative).read_text())
    privacy = strings["privacy_description"]
    assert CONTRACT in privacy
    for topic in (
        "installed and verified",
        "no uncovered-area routing fallback",
        "terrain estimates, not surveyed measurements",
        "Downloading, updating and checking",
        "IGN Géoplateforme",
        "content-autofill.googleapis.com",
        "source remains unknown",
        "cannot confirm or exclude personal information",
        "document picker",
        "no enabled social",
        "previous permission grant",
        "earlier release",
    ):
        assert topic in privacy
    assert strings["privacy_online"] == "Published privacy policy"


def test_v2_policy_proposal_covers_actual_flows_without_blanket_privacy_claims() -> (
    None
):
    draft = (ROOT / "docs/pr98-privacy-policy-draft.md").read_text()
    assert "DRAFT FOR REVIEW" in draft
    assert "Not approved, not effective and not published" in draft
    for heading in (
        "Offline route planning and elevation",
        "Private foreground device location",
        "Local storage and deletion",
        "Explicit downloads and optional online actions",
        "Android WebView and platform communications",
        "GPX export and disabled social publication",
        "Advertising, analytics and review contact",
    ):
        assert f"## {heading}" in draft
    assert "data.geopf.fr" in draft and "content-autofill.googleapis.com" in draft
    assert "cannot claim they contain none" in draft
    for forbidden in (
        "no data ever leaves the device",
        "no third-party services are used",
        "requests contain no personal information",
    ):
        assert forbidden not in draft.lower()
    matrix = (ROOT / "docs/pr98-data-safety-review.md").read_text()
    assert "DRAFT, NOT SUBMITTED" in matrix
    assert "answer/10787469" in matrix and "answer/10144311" in matrix
    assert "REVIEW REQUIRED" in matrix
    assert "Optional IGN address search" in matrix


def test_new_contract_preserves_packaged_capabilities_and_strict_uid_assertion() -> (
    None
):
    android = "{http://schemas.android.com/apk/res/android}"
    manifest = ET.parse(APP / "AndroidManifest.xml").getroot()
    assert {
        node.attrib[android + "name"]
        for node in manifest.findall("uses-permission")
        if node.attrib.get(android + "name", "").startswith("android.permission.")
    } == {
        "android.permission.INTERNET",
        "android.permission.ACCESS_COARSE_LOCATION",
        "android.permission.ACCESS_FINE_LOCATION",
        "android.permission.RECORD_AUDIO",
    }
    assert not manifest.findall(".//service")
    config = json.loads(
        (ROOT / "src/sugarglider/web/static/android_ui_config.json").read_text()
    )
    assert all(
        config[name] is False
        for name in (
            "saved_routes_available",
            "outings_available",
            "outing_live_positions_available",
        )
    )
    assert config["geocoding"]["available"] is True
    assert config["geocoding"]["endpoint"] == "https://data.geopf.fr/geocodage/search"
    instrumentation = (
        ROOT
        / "android/app/src/androidTest/java/io/github/victorgabillon/sugarglider"
        / "V2RegionInstrumentation.kt"
    ).read_text()
    assert "txDelta == 0L && rxDelta == 0L" in instrumentation
    assert "planner network counters: tx=$txDelta rx=$rxDelta" in instrumentation


def test_deployment_template_is_still_unapproved_and_separate_from_v2_draft() -> None:
    template = (ROOT / "deploy/regions/github-pages/privacy/index.html").read_text()
    assert 'data-policy-status="draft"' in template
    assert "{{PUBLIC_PUBLISHER_IDENTITY}}" in template
    assert "{{POLICY_EFFECTIVE_DATE}}" in template
    assert not (ROOT / "deploy/regions/github-pages/privacy/pr98.html").exists()
