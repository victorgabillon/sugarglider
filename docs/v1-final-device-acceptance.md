# Prepared final Yvelines Fairphone acceptance

**PREPARED; NOT RUN.** Work supplies the catalog HTTPS URL, public privacy HTTPS
URL and, optionally, the final signed AAB path. No device scenario in this document
has been executed against the integrated production region. Codex performs the
later device session; Work owns publication/Play Console. No new signing key,
public deployment or Play upload is authorized for this preparation.

## Exact entry commands after Work returns

Run from `/home/pompote/oldata/victor/sugarglider-v1-code2`:

```sh
uv run --offline python -m sugarglider.offline_regions.acceptance \
  --catalog-url 'https://victorgabillon.github.io/sugarglider-regions/catalog.json' \
  --privacy-url 'https://victorgabillon.github.io/sugarglider-regions/privacy/'
```

When Work provides a signed bundle, append `--signed-aab /absolute/path/to/final.aab`.
These are the only external inputs. The public paths above are expected, **not
currently asserted to exist**. The command uses the committed publication
inventory, pinned local bundletool and existing JDK; it reads no keystore/password.
It follows no redirects, sends no credentials/cookies, uses normal TLS trust and
requires the browser's CORS grant for browser-downloaded files. It streams all
runtime data files against the exact known sizes/hashes and checks the completed
HTML privacy page. The deployment-only `.nojekyll` flag need not be a public URL.

Output is a new `/tmp/sugarglider-v1-final-acceptance-*/` directory containing
`preflight.json`, `verified-catalog.json`, `requests.json`, six individual Import
JSON requests under `requests/`, and this `CHECKLIST.md`. A failure stays explicit.
Success means **public bytes verified, device not run**. Optional bundle signature
validation records only public certificate fingerprints, never private subject/key
data; compare with the expected upload certificate before trusting its identity.

The preflight never edits source, builds/installs an app, changes phone settings,
starts location sharing, removes regional data or claims a physical PASS. The
following supervised steps are part of the prepared driver/checklist.

## Bind the returned configuration and identify the test build

1. Check `preflight.json` and Work's observations. The region must be
   `yvelines-ouest-parisien`, build
   `1bbf598d64f5d5cc987a60f9a4cb22318392d596ff88f3eb6b40cb70dceb4691`.
   If Work changed bytes, URL layout, redirects or encoding, investigate; do not
   accept a substituted manifest or rebuild data to conceal a mismatch.
2. In a reviewed follow-up to this integration branch, Codex embeds the verified
   catalog as `src/sugarglider/web/static/offline_region_catalog.json`, sets
   `SUGARGLIDER_ANDROID_PRIVACY_POLICY_URL` to Work's verified public URL for the
   build, and advances the shared service-worker cache version and corresponding
   assertions. Until then the integrated catalog remains honestly unavailable.
3. Repeat `make check`, the browser harnesses, both Android unit/lint variants,
   release assembly/bundle and exact shell-asset checks after that configuration
   change. Record source commit, package, version code/name, APK/AAB sizes/hashes,
   certificate, device API/WebView versions and regional build ID.
4. Use the separate `.debug` package for instrumented tests without touching the
   Play-installed app. `adb install -r` may upgrade that matching existing debug
   identity only after confirming the app is not sharing or saving a document.
   ADB/CDP are observers; regional installation uses the actual Download UI.
5. A signed upload-key AAB does **not** automatically produce an APK compatible
   with the installed Play app: Play App Signing may use a different certificate.
   Never replace/uninstall/reset the Play app. Work supplies a later compatible
   internal-track update when authorized. Final release-specific evidence remains
   separate from debug observations; WebView debugging stays off in release.

## Record measurements and enforce the phone boundary

Use only this Fairphone (`014728cc`), awake/unlocked and visibly available. Start
only when its current app can safely be used for the acceptance session. Record
whether any region, route, GPX operation or sharing session already exists. Do not
clear unrelated app data. No `pm clear`, uninstall, permission revocation, hotspot,
Wi-Fi, cellular, airplane-mode, background-location or wake-lock change is allowed.
No real position is needed for these fixed public test proposals.

Baseline and each stage's end/peak measurements include:

```sh
adb -s 014728cc shell df -k /data
adb -s 014728cc shell run-as io.github.victorgabillon.sugarglider.debug du -sk files app_webview no_backup
```

Record only aggregate sizes, not file contents or capabilities. Missing directories
and release `run-as` denial are explicit measurement limitations. Add browser
`navigator.storage.estimate()` and app storage totals where available. Log UTC
start/end, monotonic elapsed milliseconds, total/free bytes and observed peak
storage at checking/map/routing/places+nature/verification/activation boundaries.
System free-space changes include other apps; they are not exact attribution.

For the debug observer, attach CDP only to that package's current WebView PID.
Enable `Network` before each operation and retain only sanitized public host/path,
method/status and request counts. Never retain headers, capabilities, coordinates
from device sensors, raw general logcat or unrelated page state. Capture only the
fixed test request, its canonical result and diagnostics. On each restart reacquire
the PID/session; stale observers do not own the new page.

## Scenarios and required evidence

Every row starts **NOT RUN**. Record actual observations, times and failure codes;
never convert a prepared request or unit/browser PASS into a device PASS.

| Scenario | Procedure and required evidence |
| --- | --- |
| Fresh download | Confirm no committed Yvelines version, use real Download, record all four component phases, bytes/hash verification and activation time. Partial files must not enable Generate. No sideloaded component or mock bridge. |
| Map | Select Yvelines, verify four component checks, Show region on map, pan/zoom inside bounds with visible attribution. Actual PMTiles map must render from local storage; no raster/network/native map fallback. |
| Waypoint / pedestrian | Import `requests/waypoint_hike.json`, Generate, record canonical request/result, explicit `hike`, snapped exact anchors, native geometry, route/cache/budget facts, latency and candidate distance. |
| Waypoint / bicycle | Repeat with `waypoint_city_bike.json`; preserve its distinct proven test coordinates and explicit profile. No automatic change to hike or relaxed snap radius. |
| Auto Tour | Import `auto_tour_hike_off.json` and `auto_tour_city_bike_off.json`, Generate, retain/expose the no-POI control, record candidates, native geometry and bounded calls. |
| Places and nature | Run the matching `*_prefer.json` cases. Record actual local index identity, nature partition/unknown coverage and each considered POI outcome. Accept truthful rejection/unavailability, not a promise of a reached scenic/water POI. Reward must not bypass missing repetition/backtracking evidence or hard gates. |
| Deterministic repeat | Repeat identical requests with identical graph/seed/settings. Compare candidate IDs/order, every candidate geometry/distance, POI outcomes and structural diagnostics. Exclude only documented elapsed measurement fields. Do not compare just the recommended distance. |
| Six profiles | Verify all six public identities in selector/capabilities and diagnostics. Record reached routes or explicit graph/snap failures when extending these fixtures; no alias/backend-profile/fallback behavior. |
| GPX | On a selected result use real system Cancel, then Save. Cancellation retains selection; Save adds zero routing calls. Compare exported XML with the captured canonical candidate using `write_plan_gpx`: one track, one segment, no route/analysis extensions, truthful reached/approximated waypoint order. Keep GPX/evidence outside Git. |
| Backend-unavailable restart | No routing/reference backend, static fixture server or USB reverse is supplied. Restart only the owned idle test app, reacquire observer, block `/v1/*` and `/v2/*` requests in that debug WebView before Generate, then rerun map, both modes and GPX using installed data. Count attempted requests as well as successful ones. CDP blocking is scoped to one session and must be reapplied after restart. Native gateway/pack identity and packaged router configuration corroborate local routing; `navigator.onLine` is not connectivity evidence. |
| Distribution unavailable | After installation, additionally block the public regional host in the debug page; verify stored map/indexes and normal planning remain available. Restore only those observer rules afterwards. No radio changes or reliance on a public-host outage. |
| Cancel fresh install | Use the product's explicit removal of the owned test region if appropriate, begin Download, cancel during transfer, wait for drain and inspect incomplete/inactive state. Generate stays unavailable; resume or remove explicitly. Measure retained partial/free space. |
| Interrupted download | With only an owned incomplete test download and no route/GPX/sharing active, terminate the debug app process; restart and verify explicit incomplete recovery and no partial activation. Use Resume/Download or scoped removal. Never use `pm clear`. |
| Remove / reinstall | Use real Remove confirmation for Yvelines only. Map/Generate must reflect missing coverage and storage release. Reinstall the same verified public offering, measure time/storage and repeat a route/map check. |
| Update preservation / peak storage | When a genuinely different prepared version is advertised, record old/new build IDs, baseline/peak/final storage, staged transfer, cancellation with old version usable, then atomic switch. With this first single-version catalog, record **PENDING SECOND PREPARED VERSION**; Verify download/reinstall is not an update and no invented build ID or regenerated pack is allowed. Automated staged-update evidence remains separate. |
| Outside coverage / corrupt data | A fixed outside-region request must fail without mutation/API retry. Inspect explicit checksum/recovery failures if an actual installation fails; do not alter valid production files to invent a passing corruption test. Unit/browser corruption evidence remains identified separately. |
| Privacy / lifecycle | Open the final public privacy link. Test rotation, background/resume and empty renderer recovery; active GPX/sharing cases require their own owned synthetic session and consent. Permission-denial, location-disabled and screen-off sharing remain separate explicit tests, never triggered by loading/joining/reconnect. |

## Finish and preserve evidence

Use the existing Python `PLAN_REQUEST_ADAPTER`, `PlanResult` and neutral
`validate_submitted_candidate` for captured canonical results; compare GPX using
the existing `sugarglider.gpx.writer.write_plan_gpx`, not a new XML interpretation.
Record requested coordinates as deliberate public fixtures, never as user GPS.
Do not silently rewrite a failing fixture or change graph/seed/arrival tolerance.
Stop on a correctness/privacy/geometry failure, retain its original result and
fix/retest through normal review.

Restore keyboard/rotation/observer rules and remove only forwards created by this
session. Keep user's hotspot, existing Play app and unrelated data untouched.
Store reports/GPX/screenshots outside Git. No publication or merge-to-main follows
automatically from this checklist. Only observed complete rows can close their
original PR/V1 gates; signing, policy and Play approval are separate.
