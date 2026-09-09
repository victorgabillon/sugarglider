# PR37 Paris and Marly multi-pack acceptance

PR37 exercises the existing PR36 runtime with two installed map packs. Inspection
found that its center-based selection, source replacement, and epoch guards already
support the required transitions. This follow-up adds deterministic tests and this
acceptance record; production code, the builder, and PWA shell **v21** are unchanged.
Map packs remain independent of routing packs, with one active local basemap and
no cross-pack stitching. PR36's completed Marly physical acceptance remains recorded
in [pr36-offline-maps.md](pr36-offline-maps.md).

## Real archive identities

Both archives were built from the existing Île-de-France PBF,
`data/map-packs/sources/ile-de-france-latest.osm.pbf`. The files under
`data/map-packs/<pack_id>/{manifest.json,basemap.pmtiles}` remain ignored generated
data. Marly was reused; Paris was built successfully for PR37. Their sizes,
manifests, SHA-256 hashes, and build IDs were verified locally; subsequent acceptance
runs reused the verified archives without rebuilding them.

| Pack | Bounds (west, south, east, north) | Archive bytes |
| --- | --- | ---: |
| `marly-map-dev-v1` | `[2.0, 48.8, 2.16, 48.94]` | 11,614,476 |
| `paris-map-dev-v1` | `[2.25, 48.8, 2.42, 48.92]` | 29,214,469 |

Marly SHA-256:
`da1eb88daf572190c01359d1679db49191b25f4c47f016ce7704429334dfaff9`

Marly build ID:
`protomaps-3ea8293a2813-pbf-5e8bc36971c21776-pmtiles-da1eb88daf572190`

Paris SHA-256:
`6791c9e03eac9a2369bcca65090d5389d35949b81d5c57097167681e87a7fa42`

Paris build ID:
`protomaps-3ea8293a2813-pbf-5e8bc36971c21776-pmtiles-6791c9e03eac9a23`

The reported Paris build completed successfully: 419 addressed tiles, approximately
2.386 million features, and a 29,214,469-byte archive. The log reported `BUILD SUCCESS`
and `Built paris-map-dev-v1`; the detached shell job's `Done` state was completion.

Both manifests credit OpenStreetMap contributors (ODbL), ESA WorldCover (CC BY 4.0),
Natural Earth, and the Protomaps basemap. Attribution is supplied by the active
source to MapLibre's visible attribution control.

## Automated coverage

`tests/browser/pr37_paris_multipack_harness.html` runs nine deterministic scenarios
against the shared production runtime and vendored PMTiles protocol/style. The
stores and MapLibre map are fakes; no real archives, backend, map data, native
bridge, or remote tiles are needed. Distinct fixture attribution labels make stale
credits detectable even though the real packs share the same credits.

- Both complete sequences below run through actual registered `moveend` handlers,
  using `getCenter()` while the initial config stays fixed.
- Every state checks pack identity, status, exact source URL/build, source count,
  layer references, attribution, neutral/online fallback, and preserved overlay
  objects/order above the basemap. The fake map rejects duplicate IDs and removal
  of a source still referenced by layers.
- Direct Marly/Paris switches verify old layer objects are removed before source
  replacement. Inclusive boundaries, reversed installed order, smaller-area
  selection, and lexicographic ties are also exercised.
- Browser online/offline events reevaluate the gap policy. Deferred promises check
  stale Marly success and rejection after Paris activation, completion after moving
  into the offline gap, and a pending Paris open after returning to active Marly.
  These races use no timing sleeps.

These checks validate lifecycle and style state, including the attribution supplied
to rendering. The real-pack desktop and physical observations recorded below are
separate evidence; rendering, storage, and network measurements are not inferred
from the fakes.

## Acceptance protocol

Install both existing archives explicitly through the shared Offline maps panel.
Retain any displayed route, planner points, Auto Tour, location, or outing overlays
and inspect them throughout the sequence. Move the map center, not just the viewport
edge, to each coordinate and wait for the reported state to settle:

| Step | Center `[longitude, latitude]` | Offline policy | Online policy |
| --- | --- | --- | --- |
| Marly | `[2.10, 48.87]` | Marly local | Marly local |
| Gap | `[2.205, 48.87]` | Neutral | Online raster |
| Paris | `[2.335, 48.86]` | Paris local | Paris local |
| Gap | `[2.205, 48.87]` | Neutral | Online raster |
| Marly | `[2.10, 48.87]` | Marly local | Marly local |

The deterministic harness uses `[2.08, 48.87]` for Marly; both Marly coordinates
are inside the same pack. The physical sequence used `[2.10, 48.87]`.

For precise developer testing, the existing `focusCoordinate()` export in
`/static/map.js` accepts these coordinate arrays. Read `offlineMapSnapshot()` from
`/static/offline_map.js` after each move. Local states must report the expected
`active_pack_id` and `local_pack_active`; gaps must report a null active pack and
`no_covering_map_pack` (offline) or `online_map_active` (online). Check visible
attribution, one local basemap only, no leftover regional layers, and intact overlays.

Capture network requests before navigation, then repeat the sequence with the pack
server unavailable after a full browser/app restart. Covering startup and settled
local states must not require OSM raster or pack-server requests. The online gap
may request the configured raster; the offline gap must remain neutral. Raster
requests already started in an online gap can finish after leaving it, so distinguish
initiation from completion in the capture. Never prefetch or persist raster tiles.

## Recorded real-pack acceptance

The following desktop and Fairphone results were reported from the real acceptance
runs. They distinguish network observations, Android radio state, and the runtime's
offline-shell policy rather than treating those as interchangeable.

### Desktop Chrome: online and DevTools-offline PASS

Both real archives were installed in Chrome OPFS. The full
Marly → gap → Paris → gap → Marly sequence passed in both modes:

- Online: local steps reported `local_pack_active` with the matching Marly/Paris
  pack; both gaps reported `online_map_active` with `active_pack_id = null`.
  Real PMTiles reads occurred, with no temporary pack-server requests after
  installation.
- DevTools network emulation offline: local steps again selected Marly/Paris;
  both gaps reported `no_covering_map_pack` with `active_pack_id = null`.
  Real PMTiles reads occurred. The capture observed zero OSM requests and zero
  pack-server requests.

### Fairphone 6: partial genuine radios-off evidence

Both real packs were installed in the actual Android WebView OPFS at the exact
archive byte sizes listed above. An earlier setup established
`airplane_mode_on = 1`, Wi-Fi disabled, no `adb reverse`, and FastAPI, GraphHopper,
and the pack server stopped. Nevertheless the WebView reported
`navigator.onLine === true`; that value is not a trustworthy physical-connectivity
oracle on this device.

This is partial radios-off evidence, **not** a completed five-step radios-off
multipack run. No Android security or connectivity implementation changed.

### Fairphone 6: full reduced-motion/offline-shell multipack PASS

The Fairphone was awake/unlocked with Sugarglider Debug's `MainActivity` visibly
foregrounded. Throughout the final sequence, `document.visibilityState` was
`"visible"`, `navigator.onLine` was `true`, and DevTools emulated
`prefers-reduced-motion: reduce`. The existing production `focusCoordinate()`
therefore used its zero-duration camera path. The diagnostic waited for initial
Marly activation and positive PMTiles reads, made exactly four camera moves without
retrying, checked each viewport midpoint, and polled state from the host.

Observed centers below are viewport midpoints, rounded to six decimal places,
not a separately exposed raw MapLibre center:

| Step | Approximate center `[lon, lat]` | Active pack | Status | PMTiles reads / bytes |
| --- | --- | --- | --- | --- |
| Marly initial | `[2.100000, 48.869976]` | `marly-map-dev-v1` | `local_pack_active` | 4 / 185,155 |
| Gap | `[2.205000, 48.869976]` | `null` | `no_covering_map_pack` | No active local source diagnostics |
| Paris | `[2.335000, 48.859976]` | `paris-map-dev-v1` | `local_pack_active` | 4 / 220,848 |
| Gap return | `[2.205000, 48.869976]` | `null` | `no_covering_map_pack` | No active local source diagnostics |
| Marly return | `[2.100000, 48.869976]` | `marly-map-dev-v1` | `local_pack_active` | 4 / 185,155 |

All centers reached the requested coordinates within the diagnostic's 0.001-degree
midpoint tolerance. Local attribution contained MapLibre, OpenStreetMap
contributors, ESA WorldCover, Natural Earth, and Protomaps basemap. Both gaps
displayed only MapLibre; local credits returned with each local pack.

Final diagnostic: `PR37 FAIRPHONE REDUCED-MOTION MULTIPACK: PASS`.

This exercised real `focusCoordinate()` → real MapLibre camera → normal `moveend`
handling → existing offline-map runtime, with real OPFS, two real PMTiles archives,
local source replacement/removal, and real reads. It was a physical WebView PASS
using the existing offline-shell behavior and a DevTools reduced-motion override.
It does **not** establish that the complete sequence ran with Android radios
disabled. The final five-step script did **not** capture OSM or pack-server traffic,
so it does **not** prove zero network requests; that observation belongs to the
desktop DevTools-offline capture above.

### Earlier physical-driver failures

Earlier attempts found Android at `mWakefulness = Dozing`, with `NotificationShade`
in front and WebView visibility `"hidden"`. Animated MapLibre `easeTo()` movement
could stall; fresh MapLibre load/offline-basemap attachment could also remain
pending at `map_pack_ready`. A single Marly → gap diagnostic passed once the phone
was awake/unlocked and Sugarglider visible, before the full sequence above passed.

The audit and foreground results identify those earlier failures as acceptance-
driver/environment artifacts, not evidence of a multipack defect requiring a
production fix. No production camera, load, connectivity, or pack-selection change
is justified by these results.

## Acceptance status

| Acceptance | Status |
| --- | --- |
| Automated deterministic multi-pack tests | PASS (9 browser scenarios) |
| Real Paris archive build | PASS (built for PR37; size/hash verified) |
| Desktop real two-pack switching, online | PASS |
| Desktop real two-pack switching, DevTools offline | PASS; zero OSM/pack-server requests observed |
| Fairphone genuine radios-off evidence | Partial setup evidence only; no complete sequence claimed |
| Fairphone real two-pack switching, visible/reduced-motion/offline-shell | PASS; final-run network traffic not captured |

PR37 remains tests/docs-only, with PWA shell **v21** unchanged. No rendering-latency,
memory-usage, or additional device-network measurement is claimed.
