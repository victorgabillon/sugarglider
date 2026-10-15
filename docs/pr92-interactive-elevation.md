# PR92: interactive elevation in the selected route

Base: PR91, `bd67f6995f3357fc1d69dc1499afb815a18d5c22`, branch
`feature/native-elevation-analysis-pr91`. This is a presentation layer for PR91's
optional immutable sidecar. There is no new DEM sampling, smoothing, D+/D−
calculation, native actor, routing call, route cache, chart library or network
dependency. Generation, candidate ranking/identity, geometry and GPX are unchanged.

## Presentation and coverage

The existing selected-route panel contains distance, immediately visible D+/D−,
the observed minimum/maximum altitude, and one responsive SVG. Its typography,
green/cream palette, 44 px actions and focus ring reuse the existing design.
The profile plots only native-returned **filtered** altitude, with a visible
estimate caption. The observed altitude range comes directly from native raw
minimum/maximum fields and may exceed the filtered graph's extrema.

Loading is nonblocking and keeps PR91's Cancel action. Complete coverage shows
native full-route totals. Partial coverage explicitly labels full-route totals
Unavailable and separately identifies measured-segment totals and the share of
route distance supported by those segments. Isolated available points have
altitudes without measurable segment ascent/descent. Fully unavailable/cancelled
analysis retains the route and offers Retry elevation. Unknown altitude never
becomes zero. An idle or absent current analysis has no decorative graph.

Saved routes, immutable snapshots and imported GPX do not acquire fabricated
elevation. They keep their existing behavior. The presentation does not write
analysis into canonical candidates, snapshots, ranking or GPX.

## Projection and distance mapping

`elevation_profile.js` is a deterministic presentation module without DOM/native
dependencies. The SVG viewBox uses actual container width and a 210 px height,
with 48 px left, 14 px right, 27 px top and 42 px bottom margins. Distance maps
linearly from zero to the authoritative routed total. Altitude maps linearly from
the available filtered minimum/maximum, padded by `max(5 m, 0.12 × range)` on each
side. Flat routes therefore have a finite range, including at zero or negative
altitudes. Padding is visual only and never enters ascent/descent.

Each native segment receives its own SVG path. A singleton receives a dot. The
projection rejects inconsistent segment indices, missing/nonfinite heights or
unsupported adjacent gaps instead of drawing a connection. Axis labels specify
kilometres and metres. Short distances use three km decimals; other routes use
two. Summary rounding is presentation only; the immutable source retains full
precision.

Inspection finds the first sample at or after routed progress by binary search.
An exact available sample uses its returned coordinate and filtered altitude.
Between samples, linear interpolation is permitted only when both belong to the
same supported native segment and their gap is within the native maximum. Missing
spans show “Elevation unavailable here” and clear the map marker. There is no
geographic nearest-neighbor lookup: repeated coordinates on loops retain their
distinct occurrences along routed distance.

Interpolated coordinates join neighboring **sample** positions, so a marker
between samples can cut a small route corner. This is the explicit bounded
presentation approximation permitted by the contract, not a geometry edit or
reroute. At an exact sample the coordinate is exact. Coarser adaptive long-route
sampling can miss narrow terrain features, as documented in PR91.

## Ownership, retry and cleanup

PR91's coordinator remains the sole owner of calculation, cancellation and its
eight-entry cache. A narrow `owns(value, candidate, generation, regionId)` check
allows presentation only for its exact current snapshot, selected immutable
candidate object, generation membership and regional selection. Ready ownership
also checks the prepared exact geometry digest/reference, profile, authoritative
distance, regional build/routing pack, elevation component and source manifest.
These bindings are retained from PR91's already validated request/result; the UI
does not hash or scan route geometry on pointer frames. No second cache is added.

Selection invalidates the old graph and marker synchronously before another
result arrives. Generation/edit/region/page invalidation uses the same existing
coordinator. Pointer, keyboard and delayed Show on map callbacks recheck ownership.
An old reply cannot redraw another route or move the viewport later.

Explicit Retry is available only after failure/cancellation or wholly unavailable
coverage. It requeues the same selected candidate through PR91's serialized pump;
an unavailable cached result is evicted by its exact existing cache key. An
in-flight cancelled JNI call drains before retry. Retry does not regenerate a
route, weaken identities or use a remote fallback. A source with no data may
remain unavailable after retry.

`elevation_map_marker.js` owns one noninteractive, style-independent DOM marker,
created through the existing MapLibre module. It reuses that marker for valid
position updates. It adds no source, layer, route redraw or automatic pan/zoom.
Unknown spans, selected-result invalidation, route clearing and map destruction
remove it. Map replacement unregisters the old remove listener. A style reload
does not invalidate a DOM marker, which is independent of style sources/layers.
The existing waypoint/POI/direction/location/spur presentation is untouched.

Show on map is a deliberate mobile action: it switches to the existing Map
workspace, then uses the existing coordinate focus action after the layout frame.
It rechecks that the same position and analysis are still current. Merely hovering
or dragging never moves the viewport. Clear position and Escape remove inspection.

## Accessibility and performance design

The graph control is a focusable horizontal slider with a descriptive SVG title,
description, explicit units and current numeric `aria-valuetext`. Left/right and
up/down inspect neighboring samples, Home/End choose endpoints, and PageUp/
PageDown move ten sample positions. Unknown samples remain inspectable. The
textual summary and position readout do not depend on hover or color. Keyboard
focus remains on the same control during a container resize.

Pointer events support mouse hover, tap and horizontal finger dragging. Pointer
capture supports dragging outside the plot. `touch-action: pan-y pinch-zoom`
preserves vertical scrolling and browser pinch zoom; pointer cancellation releases
the drag. Position updates coalesce through one animation frame. The readout has
`aria-live=off`; only state transitions update the polite status, avoiding repeated
live announcements during dragging.

Projection/path construction is O(n), at most 2,048 samples, and occurs only for a
new current result or changed container width. Inspection is O(log n) and updates
only cursor attributes, a short readout and one marker. It does not allocate a
full profile, scan route geometry, rebuild paths or call native height. A resize
observer adapts to the existing layout. Replaced controls abort their own event
listeners; destroying a view aborts remaining listeners, disconnects its observer,
cancels its frame and clears the chart/marker. No coordinate history is stored.

## Automated verification

- `uv run --offline make check`: Ruff, strict mypy, **1,380 passed / 16 deselected**.
- **498 scenarios across 24 browser harnesses**, including 17 new presentation
  cases and existing route, GPX, offline, native-bridge, PWA, responsive layout,
  private-location and UI2 suites.
- Dedicated Chromium acceptance at **360, 390, 420 and 1,280 CSS px**: actual mouse
  hover and keyboard navigation; actual touch drag and vertical scrolling on the
  three mobile widths; stable SVG path identity, no horizontal overflow or external
  requests. Actual MapLibre instances retain the same DOM marker across style
  reload/resize and remove it on map destruction at all four widths. These are
  synthetic browser profiles, not a native-device claim.
- Android **238 Debug + 233 Release** unit tests and lint, Debug assembly, V2 research main/test
  assembly and research lint passed. Native ELF/APK 16 KiB alignment passed.

Reproduction (Python 3.13/uv, Android JDK21/SDK36):

```sh
uv run --offline make check
cd android
./gradlew --offline --no-daemon testDebugUnitTest lintDebug assembleDebug \
  testReleaseUnitTest lintRelease -PsugargliderV2Research=true \
  assembleV2Debug assembleV2DebugAndroidTest lintV2Debug
```

With an existing Playwright/Chromium installation, run the self-contained local
synthetic input suite from repository root. Output must be outside Git:

```sh
ELEVATION_EVIDENCE_DIR=/private/path/pr92-browser \
  node tests/browser/pr92_elevation_acceptance.cjs
```

`PLAYWRIGHT_MODULE` and `CHROMIUM_EXECUTABLE` can select existing installations.
No package download or external server is required; its server serves only the
repository's local test/static files. The broader browser harnesses are under
`tests/browser`; the presentation HTML runs the 17 focused scenarios directly.

## Changed files

| Files | Purpose |
| --- | --- |
| `elevation_profile.js` | Pure SVG projection and binary distance-to-sample mapping |
| `elevation_view.js` | Summary, coverage, graph, input, cursor, resize and cleanup |
| `elevation_map_marker.js`, `map.js` | One reusable DOM marker integrated with map lifecycle |
| `route_elevation.js` | Narrow presentation ownership check and explicit retry through PR91 |
| `app.js`, `index.html`, `styles.css` | Selected-route integration and responsive existing-design UI |
| `service-worker.js`, `android/shell-assets.txt` | Cache generation v92 and three new bundled modules |
| `pr92_elevation_ui_harness.html/js`, `pr92_elevation_acceptance.cjs` | Coverage, identity, map cleanup, keyboard, actual touch and layout acceptance |
| `test_pr92_elevation_presentation.py` | Presentation dependency boundary and accessible summary contract |
| `test_pr26_pwa_architecture.py`, `test_pr30_trail_profiles.py`, `test_pr31_private_planner_location.py`, `test_pr32_on_device_routing_architecture.py`, `test_pr36_offline_maps.py`, `test_pr38_local_waypoint_route.py`, `test_pr39_offline_regional_pipeline.py` | Updated enforced cache generation and exact asset integrity pins |
| `README.md`, this report | Feature and validation documentation |

## Fairphone status: foreground acceptance pending

The isolated research APK was verified before its in-place update: exact PR90/
PR91 package ID, certificate, permissions, version 8 / `1.2.0-v2-research` and
manifest. All **133 bundled assets** match the current source byte for byte.
Research APK SHA-256 is
`51203364060b856f4c0a3e2633ba74db4c44965a6515a3d09685c954d82385bd`
(25,831,459 bytes). The already installed test APK remains byte-identical to
PR91 (`680d75492292e6f79eaac9329c20716aa3ae3589af7fda784645b67761446978`).
The unchanged ARM64 native library has all LOAD alignments at 16,384 bytes.
Production and older Debug package/file checks passed before the update; no
region reinstallation, signing change or connectivity change was performed.

The physical WebView's normal Generate reproduced Hike A's exact PR91 candidate
`geometry:9b7e9cb493acf01ae0f460a50c57bfea465b5af82673c5dfb384f5aa09bcd415`,
9,243 m / 186 samples / complete coverage, native D+ = D− = 172.6175 m.
The UI rendered **9.24 km, 173 m D+, 173 m D−, observed altitude 22–162 m**.
Its initial chart construction took 6.3 ms on the actual WebView.

However, another application became foreground during the test. The research
document reported `visibilityState=hidden`, so that attempt is **not accepted as
foreground touch/screenshot validation**. A foreground-device session has been
requested. The four visible route cases, screenshots, input/marker checks,
foreground memory measurements and final offline counter assertion remain
pending. Browser touch/style tests above do not substitute for that acceptance.

The complete feature is not declared physically validated at this commit. All
real captures, screenshots, APKs, device logs and terrain remain outside Git.
This feature does not resolve DEM provenance, vertical datum or redistribution
obligations; nothing authorizes public terrain distribution or a Play release.
