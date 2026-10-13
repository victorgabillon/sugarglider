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
