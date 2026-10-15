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

## Fairphone 6 acceptance

Completed on 15 October 2026 in the isolated V2 research application, using the
already installed complete Yvelines region. Automated actions used the **normal
Generate workflow** and real returned canonical candidates. Touch/key events
were sent to the actual visible research WebView; no route/elevation result was
injected. Android-composited screenshots show the offline basemap, routed line,
profile cursor and temporary marker. Foreground/window checks protected capture;
interrupted attempts were excluded and repeated with the research app visible.

The research APK was verified before its in-place update: exact PR90/PR91 package
ID, certificate, permissions, version 8 / `1.2.0-v2-research` and manifest. All
**133 bundled assets** match the tested source byte for byte. Research APK SHA-256:
`51203364060b856f4c0a3e2633ba74db4c44965a6515a3d09685c954d82385bd`
(25,831,459 bytes). The installed test APK remains byte-identical to PR91:
`680d75492292e6f79eaac9329c20716aa3ae3589af7fda784645b67761446978`.
The unchanged ARM64 native library has all LOAD alignments at 16,384 bytes.
Actual device execution used 4 KiB pages; 16 KiB compatibility is structural
validation, not a physical 16 KiB-device test.

### Actual routes and displayed values

| Normal Generate case | Routed km | Samples / spacing m | Native D+ / D− m | Displayed D+ / D− |
| --- | ---: | --- | ---: | ---: |
| Hike A | 9.243 | 186 / 50 | 172.6175 / 172.6175 | 173 m / 173 m |
| Trail Run loop | 8.226 | 166 / 50 | 143.9769 / 143.9769 | 144 m / 144 m |
| Open Hike | 2.655 | 55 / 50 | 19.585 / 74.055 | 20 m / 74 m |
| Long Gravel loop | 151.917 | 2,048 / 74.21446018563752 | 1280.455150 / 1280.455150 | 1280 m / 1280 m |

For all four references, the complete native analysis and sample-coordinate
arrays match the private PR91 captures exactly, including source, geometry and
portable profile fingerprints. The long loop was regenerated and matched again.
Six real captures, including an additional 155.720 km open Gravel route, also
passed the unchanged PR89 Python comparison on every field within **1e-7 m**,
with exact fingerprints. PR88's independent four-tile HGT probe agrees within
**0.01 m** at every native sample. This confirms implementation/source parity,
not independently surveyed elevation accuracy. Different geometries were never
forced to reproduce the regression totals.

Touch dragging on each reference produced these readouts, with marker coordinates
checked against the same native-returned samples and supported-segment mapping:

| Route | Inspected progress | Readout altitude |
| --- | ---: | ---: |
| Hike A | 8.32 km | 61.4 m |
| Trail Run | 7.40 km | 101.7 m |
| Open Hike | 2.39 km | 39.5 m |
| Long Gravel loop | 136.73 km | 166.5 m |

The automation's target progress matched within 0.1 m and coordinates within
1e-6 degrees, allowing for touch coordinate conversion. Native analysis uses the
separate 1e-7 m numeric tolerance above. Chart dragging added **zero** native route
or height requests, retained the same SVG path nodes and preserved the exact
canonical candidate/generation. GPX before/after inspection was byte-identical
for every reference: one track, one segment, no elevation points or extensions.

The open-route Show on map action moved to the existing Map workspace and showed
its inspected position on the routed line; inspection alone did not move the
viewport. Keyboard Home then Right selected the next actual sample on a
2,048-sample route. Vertical finger dragging scrolled the Routes container from
481.3 to 563.3 CSS px, confirming it did not trap scrolling.

### Switching, cancellation and failure behavior

Hike A → B → A restored the cached A profile and removed the previous marker.
A further **20 candidate transitions** all hit PR91's existing cache, added zero
native route/height requests, retained one SVG/slider and no stale markers, and
left canonical data unchanged. Profile changes, open/loop changes and regeneration
cleared obsolete chart/marker state. Repeated normal Hike, Trail Run and long-route
generations remained usable.

A new Trail Run analysis was cancelled through the actual Cancel button after
its native height request began. Three generated candidates remained available,
with no graph or marker and an explicit cancellation message. Actual Retry
returned a ready chart using **one height request and zero route requests**, with
the same candidate/generation and serialized canonical data.

Coverage/failure presentation was tested with synthetic browser fixtures for
partial, all-missing, isolated, negative and disconnected profiles. The installed
DEM was not altered to manufacture a physical void. Actual map style reload,
resize and destruction were tested with real MapLibre instances in Chromium;
those lifecycle tests are distinct from the physical normal-Generate tests.

### Render cost, responsiveness and memory

| Device case | Native height ms | Native analysis ms | SVG construction ms | Median / maximum input-to-readout ms |
| --- | ---: | ---: | ---: | ---: |
| First Hike A | 184 | 14 | 8.3 | 4.35 / 10.0 |
| Trail Run, repeated | 12 | 11 | 3.1 | 3.2 / 8.1 |
| Open Hike | 6 | 3 | 2.6 | 2.6 / 8.8 |
| Long loop, first | 159 | 75 | 5.5 | 1.0 / 6.5 |
| Long loop, repeated | 122 | 61 | 19.8 | 0.65 / 11.4 |

Trail Run native timings are from its first matching capture; SVG/input timings
are from the repeated matching route. These are individual observations, not
percentiles or a controlled benchmark. SVG duration measures synchronous
projection/DOM construction, excluding raster/compositor completion. Input delay
runs from the actual WebView input event to the readout mutation, with 22 records
per listed scrub; it does not claim hardware-touch-to-photon latency. The 19.8 ms
construction may exceed one 60 Hz frame, while subsequent inspection updates
retained the existing paths. Native height reused the routing actor throughout
(`cold_start=false`).

A 652.9-second trace recorded 661 valid package-memory samples, about one second
apart including collection time. It includes generation, map loading, native
analysis, repeated selection and some background pauses:

- Main-process peak PSS: **410,943,488 bytes** (391.9 MiB).
- Associated WebView-process peak PSS: **602,204,160 bytes** (574.3 MiB), at a
  different time from the main-process peak.
- Simultaneous aggregate peak: **865,814,528 bytes** (825.7 MiB), comprising
  410,943,488 main + 454,871,040 WebView bytes.
- Aggregate final observed sample: **758,388,736 bytes** (723.3 MiB).

During the 20 cached transitions, aggregate PSS went from 740,043,776 to
730,089,472 bytes, with a 742,369,280-byte peak. The browser's coarse reported JS
heap estimate remained 39,600,000 bytes. No DOM accumulation or monotonic PSS
growth appeared in that short switching window. This is not an endurance/leak
proof or an isolated chart-allocation measurement. The totals include native
routing/data, maps, workers and WebView; they must not be compared with PR91's
main-process-only 403 MB as if they measured the same scope. Aggregate memory is
substantial and remains a release-readiness investigation.

### Offline and preserved installations

The strict planner harness passed: the research UID sent **0 bytes** and received
**0 bytes** during the complete measured ready-to-finish suite. Startup separately
recorded 4,039 / 2,877 bytes; as in PR91, that small startup traffic remains
unattributed. This validates offline generation/elevation/map interaction after
local readiness, not a globally silent Android/WebView startup. Phone connectivity
settings were unchanged.

Final checks confirmed all nine native regional files retained their exact paths
and SHA-256, and production/older Debug package checks plus all 83 inventoried old
Debug private-file hashes passed. No regional reinstall/removal, production or
old Debug overwrite, signing change, public artifact/catalog update or release
occurred. Python/native analysis, routing generation, candidate ranking and GPX
source modules are unchanged from PR91.

### Private visual evidence and limitations

Actual Fairphone PNGs remain outside Git; these hashes identify the private
acceptance artifacts without publishing route snapshots:

| Artifact | SHA-256 |
| --- | --- |
| `hike-phone.png` | `83d7b797baa392aad1c018d30a5c819cb6d8b3c635794e37ed44cca3c79ac4f1` |
| `trail-phone.png` | `178808b663cf44a671251cff899fdaf1a0c2047085b0bac78fe8120bd86344b6` |
| `open-phone.png` | `dfeb3f56d73ce475e55cc3ebc659846b1727ce5bb2ae8debeb78042d6c014cf1` |
| `open-summary-phone.png` | `d859e64a248929b3f3d14cb3c6653e32cc9676b4e8fcdddc81488b53dcdc51c3` |
| `open-map-phone.png` | `9bb551da00015bbafe8101a9db927e71f14a49cd619be4d30f5087456f2297a3` |
| `long-phone.png` | `5fa1d01e11e195e6879729c6786c2956c27163fd79da61130f4f6874d09264ee` |

There is no profile zoom; finger precision on a 152 km route is limited by plot
width, while keyboard navigation can inspect each actual sample. In-between
positions use the bounded sample-to-sample approximation described above. Browser
pinch zoom is retained. Screen-reader semantics and keyboard behavior were tested;
this is not a human TalkBack usability study. Broader device/RAM classes,
long-duration memory behavior, DEM provenance/datum/attribution and redistribution
obligations remain release work. No public terrain distribution or Play release
is authorized by this feature. CI status and final commit are recorded on draft
PR92 so its exact head remains reviewable.
