# Code 3: default bundled activity

The immutable accepted V1 is commit `35d2a69c313ad68990eec8c882abca227b5b691c`,
tree `10d12c76457e50db89a8fbce6f501ee3ce5520ed`, Play Internal 1.0.0/code 2.
This follow-up targets **1.0.1/code 3**. It does not revise historical acceptance,
merge main, or authorize a Play upload. Instrumented device acceptance uses only
`io.github.victorgabillon.sugarglider.debug` with the existing debug signature.

## Behavior

Previously, `state.routingProfile` remained null on bundled startup even when all
six profiles were available. A map tap correctly created the start and START
marker, but Generate reported “The selected routing profile is unavailable.”

`renderRoutingProfiles()` now resolves an absent local selection explicitly to
`trail_run` when available. `initialLocalPlannerProfile()` names that product
default independently of metadata or option order. Existing selections always
win, even while unavailable. If Trail run is unavailable and selection is absent,
the deterministic fallback is the first available supported ID in this order:
`hike`, `city_bike`, `gravel_bike`, `mountain_bike`, `road_bike`. With none available,
selection remains null and Generate remains disabled. An implicit fallback stays
selected during that page's life; a fresh startup re-evaluates the Trail run default.

Only an explicit activity-selector change stores a preference. The existing PWA
store's `public_runtime` entry `planner-routing-profile` holds a versioned public
profile ID, restored before event binding and regional startup. No new database
or schema migration is needed. Implicit defaults and imported/snapshot identities
are not persisted as preferences. Rapid writes are serialized; invalid records
are ignored. Optional-storage failure leaves the current page usable and uses
the existing storage warning; restart persistence requires working storage.
Saved snapshots and outing pages retain their own initialization.

`generationAvailability()`, endpoint handling, routing/native algorithms, regional
formats, permissions, package IDs, signing configuration and map data are unchanged.

## Narrow text corrections

Activity help now refreshes with the local controls and distinguishes checking or
absent selection from unavailable selection. When readiness returns, request status
replaces only the previous availability/placement guidance with “Ready to generate.”
It does not overwrite an unrelated operation/result message. The shared footer now
says “Routes use OpenStreetMap data.” Map attribution is retained. Neither correction
changes routing behavior.

The shared shell cache advances to v45 and includes `planner_profile.js`; the
Android asset allowlist and exact cache/hash assertions advance with it.

## Full application regression

Run with an isolated output directory outside Git:

```sh
uv run python scripts/check_planner_startup.py --output /tmp/code3-startup
uv run python scripts/check_planner_startup.py \
  --app-root ../sugarglider-v1-code2 --output /tmp/code2-startup
```

Requires local Google Chrome and OpenSSL. The runner serves the unmodified
application at the exact bundled HTTPS origin, inside an isolated Chrome profile.
It seeds a synthetic installed region through the real OPFS staging, validation
and activation APIs, including valid PMTiles and the existing golden POI/nature
indexes translated around the unchanged bundled initial center. Only Android's native message port is replaced by fixture capabilities;
this browser test does not prove native archive installation or route generation.
The native descriptor is tar-aligned to satisfy the real regional-reference check.

`fresh_bundled_auto_tour_loop_map_tap_enables_generate` loads the actual `index.html`
and normal startup. It never writes planner state or invokes endpoint helpers.
It observes Auto Tour/Loop, empty endpoints/points, six ready activities, Trail run,
and the missing-start reason. A native CDP pointer event hits the map at a coordinate
calculated from the actual viewport projection. It checks the coordinate against
installed bounds, start fields, one-point list, null end, START pin tip, profile
availability, empty point validation and both enabled Generate buttons. Reload
retains OPFS and repeats the untouched-default sequence. JSON and screenshots
capture both launches. Frozen code 2 fails the default-profile and enabled-button
assertions on both launches; code 3 passes.

Additional full-page guards use actual selector keyboard events and mode/region
controls. Hike and Gravel survive mode changes, readiness checks and reloads.
A native-boundary capability change temporarily removes foot support; Hike stays
selected and disabled until support returns. The status/help corrections are
checked through that transition. The focused `planner_profile_harness.html`
adds eight cases for reordered catalogs, late readiness, all six explicit choices,
unsupported/no profiles, deterministic fallback, persistence, rapid writes,
invalid records and storage failure. Existing endpoint/profile harnesses remain.

## Release evidence boundary

Automated and physical receipts are stored outside Git under
`sugarglider-v1-artifacts/code3-2026-09-14/`. Release APK/AAB assembly is unsigned;
only the matching debug APK may be installed with `adb install -r`. Physical
acceptance cold-starts the debug package with retained Yvelines, observes the
normal defaults, and uses one real screen tap. It never clears app storage,
installs over the Play package, changes radios/permissions or modifies a region.
The preserved code-2 acceptance remains the historical baseline; code 3 is its
first corrective candidate, subject to later authorized Internal delivery.

Recorded validation on 2026-09-14:

- `make check`: Ruff, strict mypy (255 source/test files), 1,100 Python tests;
  16 existing live-GraphHopper integration tests deselected.
- All 28 browser harnesses: 490 scenarios, including canonical Python
  candidate/result/diagnostic validation and GPX equivalence checks.
- Full startup: frozen code 2 fails on both launches; code 3 passes both, plus
  full-page profile-preservation and copy guards.
- Android: 196 tests per variant, no failures/errors/skips; lint has no errors
  (two existing debug warnings, one existing release warning); debug/release APK
  and release AAB assembly, bundletool validation and 16 KB APK zip alignment pass.
- All three packages contain exactly 106 shared assets, byte-identical to source.
  The arm64 native library hash remains
  `e60d66dba922a17c53397e4a00ba4380a9ec87f8f203d3761fefe86bef9b2bbb`.
- Fairphone 6 / Android 16, debug 1.0.1-debug/code 3: two cold launches with retained
  Yvelines, automatic Trail run, one real ADB screen tap each, matching START and
  fields, no end, one point, and both Generate buttons enabled. No generation,
  GPX save, sharing, region mutation, or Play-package installation was performed.
  Screenshots 01–05 and associated JSON/XML record the valid sequence; an earlier
  notification-shade-obstructed capture is explicitly excluded.
