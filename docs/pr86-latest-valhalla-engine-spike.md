# PR86 — Valhalla Mobile 0.6.4 / Valhalla 3.9.1 compatibility spike

**DRAFT / ENGINE MIGRATION GATE — NOT A RELEASE.** This branch upgrades the
Android wrapper only for compile/unit-test and separately authorized debug-device
acceptance. Do **not** merge, produce a signed release, update Google Play, or
publish a regional build solely because CI passes.

## Why prioritize the native engine

As of 2026-10-13, the latest stable releases verified on GitHub/Maven Central
are **Valhalla 3.9.1** (2026-10-06) and **valhalla-mobile 0.6.4**
(2026-10-06). Valhalla Mobile 0.6.4 embeds Valhalla 3.9.1 and exposes:

- `route`: routed geometry and distance, as today;
- `height` / `heightRaw`: sample elevations under a shape, provided
  `additional_data.elevation` points at valid local Skadi/HGT tiles;
- `trace_route`, `trace_attributes`, and `sources_to_targets`.

**Important:** `height` without an installed elevation-tile directory
returns missing values (`null`). The upgrade alone does not provide D+/D−,
terrain data, or route profiles.

Upstream:
- [Mobile 0.6.4 release](https://github.com/Rallista/valhalla-mobile/releases/tag/0.6.4),
  [native Kotlin API](https://github.com/Rallista/valhalla-mobile/blob/0.6.4/android/valhalla/src/main/java/com/valhalla/valhalla/Valhalla.kt),
  [native actor lifecycle](https://github.com/Rallista/valhalla-mobile/blob/0.6.4/android/valhalla/src/main/java/com/valhalla/valhalla/ValhallaActor.kt).
- [Valhalla 3.9.1 release](https://github.com/valhalla/valhalla/releases/tag/3.9.1).
- [Maven dependency](https://central.sonatype.com/artifact/io.github.rallista/valhalla-mobile/0.6.4).

## Precisely what this experimental branch changes

1. Pins Android dependency versions to `valhalla-mobile:0.6.4`,
   `valhalla-models:0.6.0`, and `valhalla-models-config:0.6.0`.
   The upstream library is compiled using Java 21; verify Gradle,
   Kotlin and Android D8 compatibility with our existing JDK/AGP toolchain.
2. Keeps one native actor per selected archive, closing its old persistent
   actor **before** constructing one for a different archive. The old wrapper
   created an actor per call and didn't offer explicit native `close()`.
   The new wrapper requires it. Tests cover pack switches, failed init,
   idempotent release and recreation. Route measurements now reflect the
   new long-lived actor (the first call includes native setup).
3. Reports `0.6.4/valhalla-3.9.1` as the runtime engine version.

This branch **does not**:
- modify any published four-component region or its strict manifest;
- enable elevation files, `height` bridge, route D+, elevation UI or GPX;
- rebuild `3.6.3` graph archives or upgrade the region builder;
- publish a new AAB/APK, change signing, or alter the Play tracks;
- change routing profiles, app permissions or social feature policy.

## Compatibility questions before merge

### Native / Gradle / model API

- [ ] Both Android build variants compile against published 0.6.4 with
  JDK 21, existing AGP/Gradle versions, and unmodified signing configuration.
  CI runs Debug+Release JVM tests/lint but **only** assembles a Debug APK.
  The workflow checks 16 KiB APK page and native ELF LOAD alignments.
- [ ] `RouteRequest` fields, direction flags, six cost profiles,
  typed route status/summary/leg decoding and polyline6 interpretation
  are compatible with the newer model package.
- [ ] Unit tests pass without weakening assertions. Preserve
  16 KiB compatibility checks for native binary / eventual release.
- [ ] Native actor creation, reuse, replacement and closure are physically
  exercised with two distinct graph archives; no leaked mmaps or use-after-
  close in route calls or region removal.

### Critical old-graph risk

Existing Yvelines and development routing archives and their immutable
manifests explicitly declare **Valhalla 3.6.3**. The new engine embeds
**Valhalla 3.9.1**. **Do not infer binary graph compatibility merely from
matching major version numbers, a green Android build, or the fact the archive
has a valid TAR index.** CI unit fixtures do not execute the native graph.

- [ ] On the separate `io.github.victorgabillon.sugarglider.debug`
  package only, route known coordinates using a 3.6.3 archive and compare
  actual geometry/candidate success to the established baseline. Observe
  crashes, incompatible tile reader errors and performance. Never touch the
  Play-installed package, app storage or phone radios.
- [ ] If old graph data fail, do not enable the new engine for existing
  region builds. Implement a versioned region/graph migration using
  *new immutable build IDs*, preserving old readable versions, then validate
  update/cancel/rollback atomically. Do not overwrite public old URLs.
- [ ] Independently rebuild a small, disposable Valhalla 3.9.1 development
  archive and verify real local route outcomes for hike, trail_run and
  representative cycling profiles. Use the same bounded source PBF.
- [ ] Check compatibility of updated
  `valhalla_build_config`/`valhalla_build_tiles`/`valhalla_build_extract`
  flags, TAR index and manifest schema before changing
  `scripts/build_pr33_valhalla_pack.sh` or the regional format.

### Height integration follows a proven runtime upgrade

- [ ] Supply an existing SHA-pinned, verified local Skadi tile source
  (PR83–85 research pipeline) in an **isolated test directory**.
  Check real `Valhalla.height` values including missing/void positions;
  ensure no network fallback (`additional_data.elevation` local only).
- [ ] Design strict origin/length/identity/sample-count checked height
  requests over the native bridge against the *selected routed geometry*.
  Route generation and GPX must not be altered by missing elevation data.
- [ ] Establish sampling interval and deterministic D+/D− filtering
  against independent trail baselines, then add UI.

## Physical acceptance / rollback

After a compile-green draft, optionally build/install **the debug APK only**.
The Play production package stays on version 1.2.0 code 8. No `pm clear`,
uninstall of Play package, tester change, radio/hotspot change, signing,
or public region publication is authorized.

If compatibility cannot be proven, keep this PR draft and retain 0.5.1 on
`main`; split out tests/research and only merge a proven migration.

## Fairphone routing failure diagnosed and corrected — 2026-10-14

The upgraded Debug app's `routing_failure` / `no_route_candidate` was reproduced
on a physical Fairphone 6 using its existing Yvelines routing archive. Native
actor construction and pack selection succeeded. The first failing operation
was **typed response deserialization** inside `Valhalla.route`, before Sugarglider
could decode the polyline or validate/publish a candidate:

```text
com.valhalla.valhalla.ValhallaException$InvalidResponse: Invalid response data
cause: com.squareup.moshi.JsonDataException:
Required value 'maneuvers' missing at $.trip.legs[1]
```

`localValhallaRouteRequest` moved the direction options to the new model's
request root, including `directions_type: none`. Valhalla consequently omitted
leg maneuvers, which the 0.6.0 `RouteLeg` model requires. `maneuvers` alone would
also fail: `RouteManeuver.instruction` is required. Request **`instructions`**
so the native response satisfies the wrapper's typed schema. See the
[upstream direction-option semantics](https://github.com/valhalla/valhalla/blob/master/docs/docs/api/route/api-reference.md#directions-options).
No raw-response compatibility adapter or fabricated fields were introduced.

### Focused change

- `NativeRouteEngineFactory.kt`: request instruction-bearing maneuvers.
- `ValhallaLocalConfigurationTest.kt`: update the serialized request expectation.
- `ValhallaRouteResponseTest.kt`: reproduce both missing-maneuver and
  missing-instruction decoding errors, verify complete shape/summary decoding,
  and require instruction responses for every public profile while retaining
  all ordered break points, including loop closure. These are offline wire-schema
  tests; physical graph evidence is recorded separately below.

Temporary Debug-only exception logging was removed from the final APK/source.
Profile policies, pack manifests, actor lifetime/close behavior, snap limits,
geometry validation, planner ordering/budgets and GPX serialization were unchanged.

### Physical results using the installed 3.6.3 archive

Both installed routing-build paths retain the same unmodified 96,051,200-byte
archive, SHA-256:

```text
988672888aa4542ad4c456faffbc75c08e5ff58c758ac34006e0081cb9aec1b4
```

Their routing manifests still truthfully declare `engine_version: 3.6.3`.
Before the correction, Hike open, identical Hike repeat, Hike loop, City Bike
open and the user's original Trail Run loop all returned `routing_failure`.
A separately built pre-upgrade `main` baseline (`6c0b022`, Mobile 0.5.1 /
Valhalla 3.6.3) was also installed in place on Debug only, under the same
ID/certificate/manifest checks, then replaced again with the fixed APK. All five
baseline requests succeeded. Distance, duration and snapped coordinates matched
the fixed 3.9.1 results exactly. The four fixture shapes also matched exactly.
The original multi-waypoint loop retained the identical ordered path after
collapsing consecutive duplicate vertices for comparison only: both versions
returned 1,051 vertices, but a zero-length duplicate start vertex moved from the
end to the beginning. Runtime/export geometry was preserved exactly as returned.
Baseline cold initialization/routing measured 1,093/939 ms and the repeated warm
Hike route 44 ms; these are individual observations, not a benchmark.

After the correction, all six public profiles routed the repository's Marly
fixture in both open and loop form:

| Profile | Open distance | Loop distance | Result |
| --- | ---: | ---: | --- |
| `trail_run` | 4,066 m | 8,133 m | success |
| `hike` | 3,985 m | 7,970 m | success |
| `city_bike` | 4,716 m | 8,757 m | success |
| `gravel_bike` | 4,716 m | 8,757 m | success |
| `mountain_bike` | 4,716 m | 8,757 m | success |
| `road_bike` | 4,716 m | 8,757 m | success |

The exact original request was restored through the application's JSON import
and generated with its normal **Generate** button: one 25,353 m Trail Run loop,
1,051 vertices, one successful backend call out of a budget of 16, and no
rejected attempts/publications. Required-point order and coordinates were retained.
The original flexible 20 km target was visibly missed; its warning remains in
the canonical result and UI. No constraint or distance preference was weakened.
Exporting that returned candidate passed the one-track/one-segment/no-route/
no-extensions GPX contract with all 1,051 vertices.

Initial Hike actor initialization took 1,168 ms, cold routing 627 ms, and the
immediately repeated warm route 34 ms. Twenty additional warm Hike routes took
20–27 ms each and returned identical geometry, snaps and authoritative distance.
Process PSS fluctuated during the mixed/UI/repeat run (roughly 222–299 MiB);
this short run is not a long-duration leak assessment. Switching between the
two existing installed build paths produced fresh actors (49/47 ms initialization)
and successful routes. A read-only `/proc` inspection afterward showed exactly
one routing-archive mmap. The two paths contain identical graph bytes, so this
does **not** complete the distinct-graph lifetime gate. No Sugarglider/Valhalla
crash was found in the device crash buffer.

### Validation

From the isolated PR86 checkout:

```sh
uv run --offline make check
cd android
JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 \
ANDROID_HOME=/home/pompote/Android/Sdk \
./gradlew --offline --no-daemon testDebugUnitTest lintDebug assembleDebug \
  testReleaseUnitTest lintRelease
```

- Ruff formatting/lint and strict mypy: passed (265 source files).
- Python: 1,253 passed, 16 integration tests deselected.
- Android: 220 unit tests per variant, both lints and Debug assembly passed.
- Browser: PR34 profiles (4), PR38 waypoints (34), PR41 normal planner (19),
  PR41 candidates (40), PR41 GPX (27), PR42 integrity (15): all 139 scenarios
  passed with external requests blocked and an already installed Chromium.
- `zipalign -c -P 16 4`: passed; native ELF LOAD alignments all `0x4000`.

Every installed test APK was independently checked for the exact Debug
application ID, version code 8, matching installed SHA-256 certificate
`e84155df3a2c7ea48723876b1fe8e0e602cb600f8374d6539b9fea9aa42cfbd7`,
and a byte-identical Android manifest. Only `adb install -r` on the Debug
package was used. Routing archives were hashed before and after. Diagnostic
logs, full requests/results, APKs and screenshots were kept outside Git.

### Remaining migration gates

The tested 3.6.3 archive can be read and routed by 3.9.1; the reported failure
was caused by the upgraded request/model contract. This is evidence for that
archive and those routes, not a blanket compatibility statement for all graph
data. Keep PR86 **draft**: independently built disposable 3.9.1 graph tests,
two genuinely distinct archives, longer memory/lifecycle tests, and height
with verified local Skadi/missing-data cases still remain. No region migration
or publication is justified by this decoding fix. A separate height experiment
can now proceed against a working route engine; production elevation remains
disabled until its own acceptance gates pass.
