# Development

Start with [architecture](architecture.md), then the guide for the subsystem you will
change. Canonical documentation describes current contracts; numbered reports preserve
milestone history and detailed measurements. Do not infer current enablement from an
old release/acceptance report.

## Fast checks without services

Use Python 3.13 and `uv`; dependencies are locked in `uv.lock`.

```sh
uv sync --frozen
make check
git diff --check
```

`make check` runs `ruff format --check`, Ruff lint, strict mypy over `src tests`, and
`pytest -m "not integration"`. Unit tests must use small deterministic fixtures and
injected adapters, never Docker, live network, map data or external services. Installation
may download dependencies; test execution does not require services.

Run a focused Python test with `uv run pytest tests/unit/<file>.py`. Use `make format`
after Python edits; it applies formatting and lint fixes, so review the resulting diff.

## Reference browser and GraphHopper

The repository-root `docker-compose.yml` is the reference stack, not the Android runtime
or social production stack. Copy `.env.example` to a private `.env`, review its settings,
then explicitly obtain the configured OSM PBF and start services:

```sh
cp .env.example .env
make download-osm
make up
```

The download script preserves an existing nonempty PBF unless `FORCE=1` is explicitly
set. First graph import can take substantial time/disk. The API/browser is at
`http://localhost:8000`; the external GraphHopper port is 8989. `make logs` shows service
startup. `scripts/run_gui.sh` starts/waits for this stack and opens the selected browser.

For local Python development with an already running GraphHopper:

```sh
uv run uvicorn sugarglider.api.main:app --host 127.0.0.1 --port 8000 --reload
```

`Settings` reads the reference environment configuration; `GRAPHHOPPER_URL` defaults to
localhost:8989. The social service has independent configuration. Live routing tests
are deliberately separate:

```sh
uv run pytest -m integration
```

They require a running compatible graph/PBF; do not treat them as offline unit tests.
Profile/model/version changes require `make rebuild-graph`, whose fingerprint prevents
reuse of incompatible graphs and whose existing implementation preserves backups.

## Local indexes and regional builds

For the reference application, `make nature-index` and `make poi-index` derive ignored
indexes from the configured PBF. Startup loads each once; missing/invalid data remains
explicitly unavailable and does not prevent basic routing/health.

For a regional build, supply an existing source with verified configured coverage:

```sh
make offline-region REGION=yvelines-ouest-parisien PBF_INPUT=/absolute/path/source.osm.pbf
make offline-region-verify REGION=yvelines-ouest-parisien
```

The pipeline validates/stages a new output and refuses replacement. Map/routing builder
scripts invoke their pinned container/toolchains. Regional builds are not unit-test
prerequisites. `offline_regions/distribution.py` prepares reviewed static downloads;
publication is separate. Never commit PBFs, generated indexes, regional outputs or graph
caches. See [regions and Places](regions-and-places.md).

Other scripts fall into four groups: reference Marly generation/report/smoke, PBF/pack
builders, analysis/optimizer benchmarks, and offline migration/export/startup tooling.
Historical names remain stable for reproducibility. `sugarglider-migrate-plan` converts
legacy JSON offline and refuses ambiguous/lossy interpretations; runtime import accepts
canonical schema 1 only.

## Android checks

Install JDK 17 and Android SDK 36/build-tools 36.0.0; point `ANDROID_HOME` or a local
`android/local.properties` at the SDK. Use the checked-in wrapper:

```sh
make android-check
make android-apk
```

Equivalent combined invocation:

```sh
cd android
./gradlew --no-daemon testDebugUnitTest lintDebug assembleDebug
```

JVM tests inject boundaries; they do not need a device. Lint/debug build verifies the
bundled shell and native project, not physical acceptance or release signing. Install a
debug APK only on an explicitly selected test device. Shared shell files are copied
from the source allowlist; check packaged bytes when UI assets change. `make brand-assets`
synchronizes canonical artwork. Do not recolor/stretch/crop divergent runtime copies.

## Browser harnesses

`tests/browser/*_harness.html` are real browser suites with small deterministic adapters.
They are separate from `make check` and Android CI. Serve the repository from loopback
so `/tests`, `/src` and the application `/static` alias resolve. From the repository root:

```sh
uv run python - <<'PY'
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

class HarnessFiles(SimpleHTTPRequestHandler):
    def translate_path(self, path: str) -> str:
        if path.startswith("/static/"):
            path = "/src/sugarglider/web/static/" + path.removeprefix("/static/")
        return super().translate_path(path)

ThreadingHTTPServer(("127.0.0.1", 8765), HarnessFiles).serve_forever()
PY
```

Open `http://127.0.0.1:8765/tests/browser/automatic_intent_harness.html` or another harness.
Completion is `#result[data-status="passed"]`; a failed status or uncaught page error is
a failure. Preserve a fresh browser context per suite so OPFS/IndexedDB fixtures do not
leak. Browser fixtures are not proof of native activation or physical-device behavior.

To run all harnesses automatically, provision Playwright/Chromium separately from the
repository Python environment. With a resolvable `playwright` module (or set
`PLAYWRIGHT_MODULE` to its external module path), run in another terminal:

```sh
node <<'JS'
const fs = require("fs");
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || "playwright");
(async () => {
  const launchOptions = { args: ["--enable-unsafe-swiftshader"] };
  if (process.env.CHROME_BIN) launchOptions.executablePath = process.env.CHROME_BIN;
  const browser = await chromium.launch(launchOptions);
  try {
    for (const file of fs.readdirSync("tests/browser").filter(f => f.endsWith("_harness.html")).sort()) {
      const context = await browser.newContext({ viewport: { width: 1500, height: 950 } });
      try {
        const page = await context.newPage();
        const errors = [];
        page.on("pageerror", error => errors.push(error.message));
        await page.goto("http://127.0.0.1:8765/tests/browser/" + file);
        await page.waitForFunction(() => ["passed", "failed"].includes(
          document.querySelector("#result")?.dataset.status), null, { timeout: 120000 });
        const status = await page.locator("#result").getAttribute("data-status");
        if (status !== "passed" || errors.length) throw Error(file + ": " + errors.join("; ")
          + " " + await page.locator("#result").textContent());
        console.log(file, status);
      } finally { await context.close(); }
    }
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
JS
```

The `*_acceptance.cjs` scripts additionally drive the actual application and, where
specified, existing Yvelines data/routing. Read their environment/input requirements
before running; they write GPX/screenshots outside Git. `scripts/check_planner_startup.py`
uses an isolated bundled page with pointer input and platform/storage fixtures. Its
startup wording and later control hit-area assumptions predate automatic intent and
currently fail on main; repair those assertions before using it as an acceptance gate.
The browser harnesses and `automatic_intent_acceptance.cjs` cover current intent. None
of these fixtures establishes a live deployment.

## Test map and CI

| Contract | Useful starting tests |
| --- | --- |
| Python search/context/cache | `test_planning_core.py`, `test_waypoint_native.py`, `test_auto_tour_service.py` |
| Geometry/profile/unknown metrics | `test_route_analysis.py`, `test_backtracking.py`, `test_routing_profiles.py`, `test_nature_analysis.py` |
| Local planner and GPX | Browser `pr41_normal_planner`, `pr41_local_planning`, `pr41_local_gpx` harnesses |
| Automatic intent and editing | Browser `automatic_intent`, `ui2_waypoints`, `ui2_planning` harnesses |
| Regions/Places | `test_pr39_offline_regional_pipeline.py`, `test_places_ice_cream.py`; browser `pr42_*` / `places` harnesses |
| Snapshot/social/live safety | `test_saved_routes.py`, `test_outing_live.py`, `test_social_server.py`; browser `pr25_live_runtime`, `pr26_pwa_runtime` |
| Native routing/leases/GPX/lifecycle | Android JVM classes in `android/app/src/test/` |

Python CI runs frozen dependencies, Ruff, strict mypy and non-integration tests. Android
CI runs JVM tests/lint/debug build. Social CI validates/builds/smokes its factory/proxy;
it does not deploy. Browser/manual/device acceptance remains a separate reported gate.

## Safe changes and documentation

Read `AGENTS.md`. Keep required-point identity/order, profile-aware budgets, unknown
coverage, immutable snapshots, capability privacy and async operation ownership intact.
No map/route fallback, spontaneous location sharing or silent weakened retry is allowed.
Doc-only changes should leave Python executable ASTs and JS/Kotlin tokens unchanged
apart from docstrings/comments. A functional extraction needs focused equivalence tests.

Keep generated GPX, screenshots, indexes, PBFs, caches, credentials and release artifacts
outside Git. Do not use destructive clean/reset/stash operations to obtain a clean tree.
Use an isolated worktree when protected local work or an independent release is present.

The canonical guides form the current architecture map. Detailed social deployment,
static distribution, signing and dated device reports remain useful runbooks/evidence;
old claims about readiness, permission inventories or publication belong to their named
milestones, not today's feature matrix.
