"""Focused presentation and responsive-harness contracts for PR29."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / "src" / "sugarglider" / "web" / "static"
ANDROID = (
    ROOT
    / "android"
    / "app"
    / "src"
    / "main"
    / "java"
    / "io"
    / "github"
    / "victorgabillon"
    / "sugarglider"
)


def test_pr29_framework_free_harness_covers_polished_states_and_widths() -> None:
    harness = (ROOT / "tests/browser/pr29_ux_polish_harness.js").read_text()
    html = (ROOT / "tests/browser/pr29_ux_polish_harness.html").read_text()
    assert "[360, 390, 412, 600, 768, 1280, 1440]" in harness
    for scenario in (
        "shellScenario(frame, width)",
        "candidateScenario(frame, width)",
        "savedRouteScenario(frame, width)",
        "outingReceiptScenario(frame, width)",
        "liveOutingScenario(frame, width)",
    ):
        assert scenario in harness
    assert "document.documentElement.scrollWidth" in harness
    assert "runPr29UxPolishHarness" in html
    assert 'addEventListener("unhandledrejection"' in html


def test_pr29_shell_keeps_primary_actions_outside_secondary_disclosures() -> None:
    html = (STATIC / "index.html").read_text()
    nav = html[html.index('<nav aria-label="File') : html.index("</nav>")]
    tools = nav[nav.index('<details class="header-tools') :]
    assert nav.index('id="generate-top"') < nav.index('<details class="header-tools')
    assert nav.index('for="gpx-file"') < nav.index('<details class="header-tools')
    assert nav.index('id="save-route"') < nav.index('<details class="header-tools')
    assert 'id="request-file"' in tools
    assert 'id="export-plan"' in tools
    assert "<summary>Advanced route preferences</summary>" in html
    assert '<details class="map-tools"' in html
    assert "<summary>Layers</summary>" in html
    assert '<details class="metrics-disclosure">' in html
    assert "<summary>Technical route metrics</summary>" in html
    application = (STATIC / "app.js").read_text()
    assert 'byId("save-route").classList.toggle("hidden"' in application
    assert 'selector.addEventListener("click", () => selectCandidate' in application
    outing_view = (STATIC / "outing_view.js").read_text()
    for label in (
        "Not currently sharing",
        "Sharing your location",
        "Start background sharing",
        "will send only the latest position",
    ):
        assert label in outing_view


def test_pr29_android_server_chrome_is_compact_and_keeps_change_guard() -> None:
    activity = (ANDROID / "MainActivity.kt").read_text()
    open_server = activity[activity.index("private fun openServer") :]
    open_server = open_server[: open_server.index("private fun loadConfiguredPage")]
    assert "showServerMenu(origin)" in open_server
    assert "text = origin" not in open_server
    assert "setMessage(origin)" in open_server
    assert "requestServerChange()" in open_server
    assert (
        "ServerChangePolicy.allowed(application.statusRepository.current())"
        in open_server
    )
    assert "remove(PREFERENCE_SERVER_ORIGIN)" in open_server
    assert "ViewCompat.setOnApplyWindowInsetsListener(serverChrome)" in open_server
    assert "WindowInsetsCompat.Type.systemBars()" in open_server
    assert "WindowInsetsCompat.Type.displayCutout()" in open_server
    assert "val chromeTopPadding = dp(8)" in open_server
    assert "val chromeEndPadding = dp(12)" in open_server
    assert "systemBars.top + chromeTopPadding" in open_server
    assert "systemBars.right + chromeEndPadding" in open_server
    assert "ViewCompat.requestApplyInsets(serverChrome)" in open_server
