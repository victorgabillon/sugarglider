# PR44 — patched MapLibre attribution handling

The dependency audit found that bundled MapLibre GL JS 4.7.1 is affected by
GHSA-jrc7-96c5-q579 / CVE-2026-85061. Its sanitizer can leave an adjacent event
handler in untrusted attribution HTML. Upstream identifies 6.4.1 as the patched
release. This follow-up replaces the vulnerable distribution with the unmodified,
integrity-verified official 6.4.1 package.
[Upstream advisory](https://github.com/maplibre/maplibre-gl-js/security/advisories/GHSA-jrc7-96c5-q579),
[patched release](https://github.com/maplibre/maplibre-gl-js/releases/tag/v6.4.1).

## Packaging and behavior

Version 6.4.1 ships an ESM entry, shared module and module worker. The map adapter
and offline-map runtime import that entry directly. All three modules, CSS and
license are packaged locally; the old global script is removed. Android serves
`.mjs` with JavaScript MIME, and the existing optional service-worker shell
allowlist contains the three files at generation v41. The Android generated
allowlist contains 103 assets. No CDN, remote module/worker or tile fallback is
introduced, and the shared regional OPFS/PMTiles implementation is unchanged.

The upstream source revision is `37e08c1901bee38fb5103510436b590c0460b44f`.
The npm tarball SHA-256 is
`21d78393afc6db78f1f9963dfd979057b536b309d8c48c1a4dde95277a522fef`,
with npm SHA-512 integrity independently checked before extraction. Exact runtime
file hashes and license provenance are in the vendored README. Runtime files are
copied byte-for-byte, without patching/minifying. Existing artwork is unchanged.

## Regression evidence

The real-browser security harness exercises consecutive dangerous attribution
attributes, attributed style replacement, local module-worker GeoJSON rendering
and a literal-text popup. It also asserts that the OpenStreetMap credit/link
remain present. All four cases pass with 6.4.1. Passing the actual previous 4.7.1
bundle into the same harness fails on the surviving event-handler assertion.
The payload only changes a test counter and makes no external request.

All 27 browser harnesses pass, totaling 479 cases. This includes the preceding
361 regional/planning/GPX/PWA/native-adapter cases, four new security cases and
114 live/responsive/profile/location/endpoint UI cases. Canonical Python checks
still validate 51 full PlanResults, 30 submitted-candidate fixtures, 16 diagnostic
snapshots and 60 GPX tracks against the Python serializer.

A separate real-page host run uses the actual bundled-origin files, workers,
OPFS and PMTiles with an explicitly synthetic native adapter. Download and
four-component activation pass, followed by reload with the distribution
unavailable and Show region without planner mutation. Waypoint Route and Auto Tour
both pass for hiking and city bike. Map geometry matches canonical candidates,
direction arrows remain available, GPX matches Python with no extra route calls,
and outside-coverage failure is explicit. No uncaught page error or routing API
request is observed. These are synthetic host tests, not Fairphone route evidence.

The page diagnostic was updated to capture the module-owned map and use the public
`GeoJSONSource.getData()` API; its old global/private `_data` probes are obsolete.
No product behavior or assertions were weakened to accommodate those probes.

`make check` passes 1,055 tests / 16 existing integration tests deselected, Ruff
and strict mypy. Three ASGI tests verify exact module bytes and executable MIME
for the entry/shared/worker modules. Existing integrity and full module-graph
cache checks now cover the new distribution and shell generation.

An exact-version OSV query on 2026-09-12 returns no matching advisory for 6.4.1.
This closes the identified dependency issue after integration validation; it is
not a claim of an exhaustive security audit or of Google approval.

## Remaining release gates

The combined native build passes in 4 min 15 s: 196 JUnit tests per variant,
zero failures/errors/skips, both lint checks with the two debug / one release
existing warnings, and APK/AAB assembly. All 103 packaged files are byte-identical
to source, and the sole ARM64 library retains SHA-256
`e60d66dba922a17c53397e4a00ba4380a9ec87f8f203d3761fefe86bef9b2bbb`.
The unsigned bundle passes official bundletool 1.18.3 validation. It is 47,495,818
bytes, SHA-256
`ffdcfc5520e2b81cc8ee0aa324fba5429d38eddda8f4faee472c1b6c3a48526e`,
retained at `/tmp/sugarglider-pr44-maplibre-unsigned.aab`.

The separate debug app was updated on the authorized Fairphone without clearing
its data or replacing the Play-installed app. APK: 151,938,674 bytes, SHA-256
`f5c15540013e5605c73aee1423640da52bad78c198623c9841df9e54c4313dad`.
An unlocked visible check confirms bundled HTTPS startup, MapLibre 6.4.1 module
loading, no error banner and disabled Generate with no region installed. Privacy
opens readable local details and closes without changing page identity or an
edited distance. Rotation preserves the page/edited distance and native process;
the original automatic-rotation mode and distance were restored. No geolocation
or sharing was started, no radio/hotspot setting was changed, and temporary ADB
forwards were removed.

A deliberate CDP crash of only the empty test WebView renderer also passes:
the native process survives, the visible warning explains unsaved edits and
ongoing native sharing, and explicit Reopen returns to the bundled planner with
Generate disabled. No route, participant authority, location session or GPX save
was active. This proves empty-page recovery, not in-flight regional/GPX/sharing
acceptance. A small follow-up will improve status-bar contrast on the native
recovery screen, where Android 16 draws behind the bars.

The physical check found a separate readiness-text defect: with no region, the
panel still says “Checking regional data…” despite completed discovery. Generate
is correctly disabled and the unavailable download is explicit. A focused UI
follow-up will replace stale progress text and test finished/error states. The native integration is draft PR #53 / `e58acdd`; this is its
separate dependency-security follow-up. Consumer-region publication approval,
physical install/planning/restart/recovery, public privacy identity/URL, existing
upload-key configuration and publisher declarations remain open. No current
artifact is described as Play-ready and no milestone has been merged on the basis
of these host-only checks.

Evidence: `/tmp/sugarglider-pr44-maplibre-{check,all-browser,baseline}.log`,
`/tmp/sugarglider-pr44-other-browser.log`, `/tmp/sugarglider-pr44-normal-ui.json`,
the verified npm metadata/tarball and the temporary device/build reports. Generated
artifacts, screenshots, GPX and test data remain outside Git.
