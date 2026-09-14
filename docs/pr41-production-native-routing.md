# PR41 — shared production native routing

This dependent preparation starts at bundled-shell commit `5f43bce`. Debug and
release now compile one native routing factory and the same six profile policies.
The disabled release factory and debug experiment build flag are removed. The
pinned Valhalla 0.5.1 / native 3.6.3 dependencies and ARM64 ABI apply to both
variants. The normal shared planner remains responsible for bounded search,
canonical publication, map display and selected-candidate GPX.

Production packaging is enabled; **the complete PR41 release-equivalent and PR42
consumer-region acceptance gates remain open**. This is not the final V1 artifact.

## Runtime boundary and variant audit

Each route still selects exactly one compatible installed archive through the
existing registry, with explicit public profile identity, bounded ordered points,
continuous native leg geometry and snapped endpoints. No routing/profile policy,
graph version, budget, snap threshold or candidate ranking changed. The previous
debug geometry and profile unit tests now run in both variants.

The real serialized configuration contains only the selected archive. Its tile
directory and auxiliary elevation, admin, timezone, landmark and transit paths
are empty; remote tile URL, traffic archive, HTTP-server and statsd configuration
are absent. This prevents an unavailable archive from selecting an unrelated SDK
default directory. The serialization test uses real Moshi and a synthetic path;
it needs no native library, map, service or network.

The pinned wrapper's [build configuration](https://github.com/Rallista/valhalla-mobile/blob/0.5.1/src/CMakeLists.txt)
disables HTTP and services. The [3.6.3 graph reader](https://github.com/valhalla/valhalla/blob/3.6.3/src/baldr/graphreader.cc)
uses the configured archive and cannot load directory tiles from an empty path.
The [Kotlin wrapper](https://github.com/Rallista/valhalla-mobile/blob/0.5.1/android/valhalla/src/main/java/com/valhalla/valhalla/ValhallaActor.kt)
delegates each route to [JNI](https://github.com/Rallista/valhalla-mobile/blob/0.5.1/src/wrapper/main.cpp),
which creates a native actor per call. Existing measurement fields retain their
version-2 names; comments and diagnostic labels now distinguish Kotlin wrapper
preparation/reuse from native call time including actor setup. They do not imply
a retained native actor or native graph cache.

There are no remaining variant-specific Kotlin routing classes. Remaining debug
packaging differences are the separate application ID/name/version suffix,
debuggability and explicit development cleartext/default server hint. Release
keeps HTTPS-only sharing and the normal non-debuggable build. Local bundled bridge
methods and exact-origin, main-frame, nonce, lifecycle and binary-transfer gates
are unchanged. Location sharing still requires its separate origin, explicit
user action, disclosure and permissions.

Normal application startup no longer binds the old experiment panel on either
the local or sharing origin. This closes the panel exposure that enabling release
capabilities would otherwise cause on a configured server page. Its isolated
module harnesses remain regression fixtures; normal users use Generate.

## Automated validation

On 2026-09-12, after removal of normal experiment wiring:

- `make check`: **1,031 passed / 16 existing integration deselections**; Ruff and
  strict mypy pass (246 files).
- `uv run python /tmp/sugarglider-pr41-document-browser.py`: **286 cases in fifteen
  browser harnesses pass**, including canonical Python validation of 50 results
  and exact XML equality of 59 GPX exports.
- `uv run python /tmp/sugarglider-pr41-normal-ui.py`: both modes with hiking/cycling,
  normal Generate/GPX, exact map lines and truthful unknown metrics pass after
  server shutdown. The real server-origin page keeps the experiment panel hidden
  with a disclosed synthetic native bridge. This is host evidence.
- Android `testDebugUnitTest lintDebug testReleaseUnitTest lintRelease assembleDebug
  bundleRelease`: **150 debug / 150 release tests**, zero failures/errors/skips;
  no lint errors/fatal findings. Two debug warnings remain (development cleartext,
  ChromeOS ABI support); release has only the ABI warning. Final build: 2 min 25 s.
- All **84 shared assets** in APK/AAB match source bytes. Both artifacts contain
  the same sole ARM64 native library, SHA-256
  `e60d66dba922a17c53397e4a00ba4380a9ec87f8f203d3761fefe86bef9b2bbb`.
  Every ELF LOAD alignment is `0x4000`; SDK 36 `zipalign -c -P 16 4` passes for the
  APK. Delivered Play APK validation remains a separate final release gate.
- `git diff --check` passes. No skipped/xfail test or weakened route constraint
  was introduced. Initial static checks still expected the removed panel wiring
  and old app fingerprint; updated contracts now assert its absence.

Historical ignored artifacts for this preparation (current build-output paths
are superseded by [PR42 integrity](pr42-regional-integrity.md)):

| Artifact | Path | Bytes | SHA-256 |
| --- | --- | ---: | --- |
| Debug APK | `android/app/build/outputs/apk/debug/app-debug.apk` | 151,612,798 | `f51794400f37f4ce56cb5122f1f1d3a56e0722da4fc262990d0c603be8d14e49` |
| Unsigned release AAB | `android/app/build/outputs/bundle/release/app-release.aab` | 47,346,580 | `7dc9fc42bac43e837249aa60e6e00c67a390b18a7e16f0e8e0eaee7f7c8717b9` |

The AAB now contains the routing library. It is unsigned and is not the V1 release
candidate. These artifacts supersede the release-disabled bundle at `5f43bce`.

## Fairphone preparation — 2026-09-12

Fairphone 6, Android API 36, WebView 151; upgrade with `adb install -r`, preserving
all application data. The app opens its packaged HTTPS origin without a setup
server or USB reverse connection. Existing native Marly/Paris development routing
archives remain installed. Its separate origin still has no map/POI/nature pack;
that missing data remains explicit and is not copied from the old server origin.
No radio, hotspot, permission or stay-awake setting changed, and no location
sharing was started.

The initial common-engine artifact passed these normal Import JSON / Generate
cases, with the same native geometry as bundled-shell preparation `5f43bce`:

| Mode / public profile | Time | Native calls | Candidates | Recommended distance |
| --- | ---: | ---: | ---: | ---: |
| Waypoint / hike | 2,364 ms including cold setup | 1 | 1 | 4,226 m |
| Waypoint / city bike | 319 ms | 1 | 1 | 4,249 m |
| Auto Tour / hike | 1,139 ms | 6 | 2 | 14,378 m |
| Auto Tour / city bike | 1,133 ms | 8 | 2 | 14,397 m |

All candidates pass Python's unchanged canonical/submitted-candidate validation.
Map sources match the native geometry exactly, direction arrows remain present,
and missing graph/nature facts remain unknown. All four repeated cases retain
candidate IDs/order, every candidate geometry and distance, and native-call counts.
The exact final APK listed above was then installed preserving data and passed
all four cases again: **2,361 / 304 / 1,136 / 1,088 ms**, with the same distances,
call counts, candidate counts and geometry hashes. Its local resource/origin and
neutral bridge probes also pass. No `/v1` or `/v2` planning request occurs. Module-worker requests resolve through
packaged local resources. This is backend isolation, not a radio-off test.

Outside coverage fails once with `no_covering_routing_pack`, without changing the
source request or retrying through a server. A separate bounded 16-point Paris
native request returns `routing_failure`; the UI subsequently plans normally.
The internal native failure reason is not inferred from that public code.

Process-scoped log collection during the four successful cases and uncovered
failure inspected 117 lines; the separate native-failure run inspected six. No
fixture latitude/longitude or serialized request fields matched. Only summaries
and redacted generic SDK messages are retained, never raw logs. The library emits
ordinary tile-count/hierarchy-default messages, and its JNI source still prints
exception text. This limited check is **not** proof of a silent SDK or every
possible corrupt-input/failure path. Final release privacy/lifecycle review remains
required.

Physical GPX Cancel preserves the selected candidate and re-enables export. Save
through Android's actual document picker produces 22,717 bytes / 518 trackpoints,
zero waypoints, one track/segment and no route/extensions, with complete Python XML
equality and no new routing calls. SHA-256:
`2e8b12321ced15e0b04bac0c2b8011fdace6c8de5da59f10200fe5bf1b7db1c6`.
These shared-engine phone runs use a debug APK; they do not replace physical
acceptance of the final release artifact and useful production region.

Temporary drivers and reports are `/tmp/sugarglider-pr41-native-release-*`.
Generated APK, AAB, native-library inspection output and GPX remain outside Git.
