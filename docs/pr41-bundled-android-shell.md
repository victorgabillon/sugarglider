# PR41 — bundled Android first launch

This preparation builds on `af37a1f` on the dependent branch
`feat/pr41-bundled-android-shell`. The normal planner now ships inside the APK and
opens at `https://appassets.androidplatform.net/` on ordinary first launch.
It does not need a configured server, localhost, a prior web visit or a service
worker. This closes the shell setup dependency; production native routing and
consumer regional installation remain separate open PR41/42 gates.

## Packaged shared assets

`android/shell-assets.txt` is a generated explicit allowlist of the shared web
shell's runtime files, its public Android configuration and four license notices.
Gradle copies those exact files into generated build assets; it does not commit
another artwork/code tree or package routing graphs, maps, POI/nature indexes,
server code, secrets or GPX. The three font PBF files are existing licensed glyph
chunks, not OSM map data. Regenerate the manifest and environment-independent
public configuration with:

```sh
uv run python -m sugarglider.web.build_android_shell
```

Python freshness checks connect configuration to the canonical public UI builder
and the asset list to the shared shell declarations. Builds reject missing or
symlinked assets. The application source remains the same web orchestration used
by the browser, including its workers, routing context, canonical publisher,
map rendering, local GPX serializer and bounded regional readers.

A thin `WebViewAssetLoader` adapter maps declared paths to packaged bytes. The
reserved origin answers only known GET resources. Unsupported methods, queries,
undeclared paths, APIs, saved/outing navigation paths and service-worker scripts
receive local 404 responses; missing packaged files cannot fall back to a server.
The local `/v1/ui/config` response is a packaged public JSON file, not a running
API. Ordinary web sharing still uses its own configured origin and endpoints.

The bundled page does not register a service worker: app updates supply its current
HTML, JavaScript and worker bytes, with no-store responses. OPFS and optional
IndexedDB remain shared-web implementations scoped to the local origin. Existing
server-origin offline maps, places, nature, profiles, snapshots and participant
storage are not copied or deleted. Native routing archives stay in their existing
independent application storage. Missing regional components remain explicit.

The packaged planner uses local maps only and keeps attribution visible even
when only the routed line is present. The former debug routing controls stay
hidden on the bundled page. Release routing is still disabled in this preparation;
there is no server fallback when that factory or a compatible region is unavailable.

## Sharing and lifecycle separation

The native Sharing control opens an explicitly configured sharing server in a
new WebView; Back to planner opens the packaged origin. Existing sharing-server
preferences remain intact. Outing deep links retain the configured server path.
Activity recreation remembers only a boolean UI mode, not a URL, participant
identity or capability. Opening either view never starts geolocation or sharing.
The existing explicit native tracking disclosure, permissions and Stop behavior
remain in place.

The local bridge allows only handshake, routing capabilities, route requests and
GPX saving. Its handshake has neutral stopped status; tracking commands receive
`sharing_unavailable` without participant identity. Native tracking broadcasts
and terminal events are not delivered to the local page. The existing exact-origin,
main-frame/current-WebView and page-nonce gates remain authoritative. An active
native service is not automatically stopped by a page switch.

API basis checked 2026-09-12: Android's
[in-app content guidance](https://developer.android.com/develop/ui/views/layout/webapps/load-local-content)
and [WebViewAssetLoader reference](https://developer.android.com/reference/androidx/webkit/WebViewAssetLoader).
The explicit local 404 policy closes the default loader's possible network fallback.

## Validation

On 2026-09-12 the following final checks pass:

- `make check`: **1,031 passed / 16 existing integration tests deselected**;
  Ruff and strict mypy pass (246 files).
- **286 scenarios across fifteen real browser harnesses** pass. New tests cover
  bundled-origin recognition, absence of an independent service-worker cache,
  and unchanged browser registration. The normal shared-page host test also
  passes both modes, hiking/cycling, exact map lines and GPX after server shutdown.
- Android `testDebugUnitTest lintDebug testReleaseUnitTest lintRelease assembleDebug
  bundleRelease`: **149 debug / 144 release tests**, zero failures/errors/skips,
  and no lint errors/fatal findings. The two debug warnings are existing
  development cleartext and ChromeOS ABI support; release has only the latter.
  Five new native cases cover allowed resources, private/unknown paths, methods,
  origin boundaries, bridge authority and truthful token-free rejection.
- **84 declared assets** in both APK and AAB match their shared source bytes,
  together with the generated asset list. This includes unchanged canonical brand
  artwork and the existing licensed glyph files. No service-worker script is
  packaged. The final native build took 3 min 32 s.

The Fairphone 6 / API 36 / WebView 151 was upgraded with `adb install -r`, retaining
its data. No setup server or USB reverse connection existed. The local HTTPS page
opened directly, including its first-run profile dialog, and retained that profile
after a cold process restart. It has no service-worker registration or controller.
Packaged fonts and module workers return local 200 responses; unknown files,
`/v2/plans` and `/service-worker.js` return local 404 responses. Handshake status is
neutral and a tracking-status request returns `sharing_unavailable` with no
participant identity. The native Sharing button opens the separately stored
development server origin; Back to planner restores the local origin with its own
profile/storage and neutral bridge. No server preference or old origin data was
changed. No sharing/location watch was started.

| Bundled normal Generate | Time | Native calls | Candidates | Recommended distance |
| --- | ---: | ---: | ---: | ---: |
| Waypoint / hike | 2,429 ms including cold engine start | 1 | 1 | 4,226 m |
| Waypoint / city bike | 311 ms | 1 | 1 | 4,249 m |
| Auto Tour / hike | 943 ms | 6 | 2 | 14,378 m |
| Auto Tour / city bike | 1,096 ms | 8 | 2 | 14,397 m |

All six returned candidates pass Python's unchanged canonical/submitted-candidate
validation. Map lines match the native candidate geometry exactly; direction
arrows and OSM attribution remain visible. The new origin correctly reports no
installed map pack and unknown nature/POI evidence: old server-origin OPFS data was
not copied. The native `marly-dev-v1` routing archive remains available from its
independent native storage. No planning API requests occur. Worker request events
use the local packaged origin; these are not network routing calls. A separate
outside-coverage case returns one native failure without retry or API fallback.

Normal GPX Save and Cancel pass again from this bundled origin. The cycling tour
exports 22,717 bytes / 518 trackpoints, one track and segment, no route/extensions,
with exact Python XML equality and zero new routing calls. The selected candidate
is unchanged. SHA-256 is
`2e8b12321ced15e0b04bac0c2b8011fdace6c8de5da59f10200fe5bf1b7db1c6`.

Current artifacts, outside Git:

- Debug APK: `android/app/build/outputs/apk/debug/app-debug.apk`, **151,612,119 bytes**,
  SHA-256 `fdc6a6a86408b02cce6699e1fd224d6049309890adae1d8d2e9ff6de505be8fe`.
- Unsigned release AAB: `android/app/build/outputs/bundle/release/app-release.aab`,
  **10,908,285 bytes**, SHA-256
  `1b1fc099a4c540d726040dc5611de51fd9035b42c1d66145bf9cc99886e8bd43`.
  It contains the shared shell but no enabled production router; **it is not the
  V1 release artifact**.

Logs, public fixture reports and small device drivers are under
`/tmp/sugarglider-pr41-bundle-*`, including the artifact hashes, first-launch and
restart probes, native planning results and GPX verification. Initial validation
caught a Gradle import-name collision and one long Python line. Device review
caught generic rejection wording and missing attribution on the empty basemap;
these were corrected and relevant checks rerun. No hard route constraint was
weakened. Temporary diagnostic breakpoints and owned ADB forwarding were removed;
reverse forwarding remains empty and stay-awake remains its original value `0`.
Radios and hotspot were unchanged, no app data was cleared, and no generated GPX
or screenshot is committed.

This remains a debug preparation, not release-equivalent PR41 acceptance. The
new origin has no installed map/POI/nature components yet; the consumer installer
and useful production region acceptance belong to PR42. No V1 readiness or Play
submission approval is claimed.
