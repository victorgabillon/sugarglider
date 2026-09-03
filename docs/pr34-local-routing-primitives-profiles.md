# PR34 local routing primitives and profiles

PR34 turns the debug-only Valhalla spike into a bounded ordered-route primitive
for Sugarglider's six public profile identities. It does not implement local
Auto Tour, enable Valhalla in release, replace GraphHopper, or claim profile or
route-quality parity. GraphHopper remains the reference backend.

## Ordered local-route boundary

Local wire request version 2 accepts exactly `profile` and an ordered `points`
array. It requires 2–16 finite geographic coordinates and rejects the former
`origin`/`destination` form rather than silently adapting it. Every point must
be covered by one compatible regional pack. Separate graphs are never stitched
and there is no network, GraphHopper, or straight-line fallback.

All points are sent to Valhalla as ordered `break` locations. The returned leg
shapes are joined only at an identical shared boundary vertex; that vertex is
included once. A missing leg or disconnected shape fails explicitly instead of
fabricating geometry. The 20,000-vertex and 512 KiB reply limits remain in
force, and native routing remains serialized off the UI thread.

Successful replies preserve the requested public profile, selected pack,
engine/version, distance, duration, joined geometry, measurements, and a
bounded `snapped_points` list. The snapped points are the first route-shape
coordinate followed by each leg's last coordinate, so they represent the
actual graph-derived break boundaries rather than echoing requested points.

## Explicit experimental profile policy

The public identities remain exactly `trail_run`, `hike`, `city_bike`,
`gravel_bike`, `mountain_bike`, and `road_bike`. They map to typed options
available in `valhalla-models` 0.5.1:

| Public profile | Access | Valhalla costing | Typed experimental options |
| --- | --- | --- | --- |
| `trail_run` | foot | pedestrian | walking speed 9 km/h; step penalty 120 s; tracks 0.65; hills 0.45; maximum hiking difficulty 1 |
| `hike` | foot | pedestrian | walking speed 5 km/h; step penalty 30 s; tracks 1.0; hills 0.75; maximum hiking difficulty 3 |
| `city_bike` | bicycle | bicycle, Hybrid | cycling speed 18 km/h; roads 0.25; hills 0.35; avoid bad surfaces 0.85 |
| `gravel_bike` | bicycle | bicycle, Cross | cycling speed 20 km/h; roads 0.35; hills 0.50; avoid bad surfaces 0.35 |
| `mountain_bike` | bicycle | bicycle, Mountain | cycling speed 16 km/h; roads 0.15; hills 0.75; avoid bad surfaces 0.0 |
| `road_bike` | bicycle | bicycle, Road | cycling speed 25 km/h; roads 0.80; hills 0.50; avoid bad surfaces 0.95 |

These are deliberate local experimental policies, not translations of
GraphHopper custom models. A preference can act only on attributes present in
the local OSM graph; it is not a safety, legality, condition, or rideability
guarantee. Different policies need not produce different geometry on every
fixture.

## Pack capabilities

The strict PR33 schema v1 remains readable and is always treated as foot-only.
PR34 development packs use schema v2 with one additional bounded field:

```json
{
  "schema_version": 2,
  "pack_id": "marly-dev-v1",
  "engine": "valhalla",
  "engine_version": "3.6.3",
  "bounds": {
    "west": 2.0,
    "south": 48.8,
    "east": 2.16,
    "north": 48.94
  },
  "access_modes": ["foot", "bicycle"]
}
```

The parser rejects missing, extra, duplicate, unknown, empty, or
non-canonically ordered modes while preserving PR33 path confinement and TAR
validation. Selection first finds packs covering every point, then filters by
the profile's access mode, with the existing smallest-area/pack-ID tie-break.
`no_covering_routing_pack` means no single region contains all points;
`no_compatible_routing_pack` means a covering region exists but does not
advertise the requested access mode.

Capabilities expose sorted pack IDs, each pack's access modes, and the exact
public-profile union enabled by those packs. They expose no filesystem path.
The development builder now includes pedestrian and bicycle graph data while
continuing to exclude driving. Generated packs remain ignored.

Both packs were rebuilt cleanly from the same configured Île-de-France PBF with
Valhalla 3.6.3. The TAR comparison against the preceding PR33 foot-only build
is:

| Pack | PR33 foot-only TAR | PR34 foot+bicycle TAR | Change | PR33 SHA-256 | PR34 SHA-256 |
| --- | ---: | ---: | ---: | --- | --- |
| `marly-dev-v1` | 11,653,120 B | 11,939,840 B | +286,720 B (+2.46%) | `df0e21913fc8f44ed26983d91eacca8ffbe00af70b7336e355dd7d7788b4794f` | `bed929ee3e3bfdd7678b70ffdbb68fda3ab4799a6a551ff857859b84f415c856` |
| `paris-dev-v1` | 52,633,600 B | 56,145,920 B | +3,512,320 B (+6.67%) | `51d100794d4d25ecff7d09d307d66ece5250cd3cc2a62990ffaf1cf584163e54` | `9bf69496d5a9ac6bb604645557031dd105bca660f9e7ab259e8ade077bfa7e10` |

The observed increase is the storage impact for these two development regions,
not a general density estimate. The fixed image, bounded extract, single-thread
build, and TAR-header normalization remain the reproducibility controls.

## PR35 route-analysis feasibility

The inspected `valhalla-mobile` 0.5.1 public wrapper exposes typed
`route(RouteRequest)` only. Its Valhalla 3.6.3 route response provides summary,
leg shapes, basic maneuver data, and locations that are not a stable typed
source of graph-snapped requested points. PR34 therefore derives only the
robust bounded `snapped_points` subset from returned leg shapes.

The current route wrapper does not expose stable edge or way identity,
road/use classification, surface, pedestrian/bicycle access, or hiking/MTB
difficulty along the returned path. The model dependency contains
trace-attribute response types and upstream Valhalla supports a
`trace_attributes` action, but the mobile wrapper's public Kotlin/JNI surface
does not expose that action. PR34 does not use internal ABI calls, debug-string
scraping, or undocumented JSON to bypass this boundary.

For PR35, structural scoring can use route geometry, distance, duration, ordered
anchors, snapped break points, and independently requested graph-derived route
variants. Exact repetition and the existing attribute-based quality analysis
will require a reviewed typed extension of the mobile wrapper for bounded
`trace_attributes` output (or another documented typed API). Until then,
missing edge identity and attributes must remain visibly unavailable.

## Debug verification and comparison

The debug panel provides a deterministic six-profile selector, fixed Marly and
Paris routes, a fixed three-point Marly via route, and a cross-pack request.
It displays the returned profile and pack. Normal Generate and Auto Tour are
unchanged.

The existing `scripts/compare_routing_profiles.py` remains the GraphHopper
reference tool. Valhalla policy-pair probes are observational: they record
success, distance, geometry, and profile identity without arbitrary parity
thresholds. Results depend on mapped attributes in the chosen fixture and do
not establish semantic parity.

A local Valhalla 3.6.3 probe used the rebuilt `marly-dev-v1` pack, the exact
PR34 options above, and the controlled Saint-Germain forest fixture
`48.9210,2.0870 → 48.9060,2.0630`:

| Public profile | Result | Distance | Duration | Geometry | Shape SHA-256 |
| --- | --- | ---: | ---: | ---: | --- |
| `trail_run` | success | 3.167 km | 1,289.199 s | 61 vertices | `46eb2967abafa65e4dfe92893639a1721659e077a8f5017f9470e9b93a6eeae2` |
| `hike` | success | 3.257 km | 2,377.759 s | 55 vertices | `7f55a563f990f8138c664a13990badae13ede99151eea6066799108d721ffd1a` |
| `city_bike` | success | 3.477 km | 880.548 s | 175 vertices | `6346c0efc3fa2ca0649708b041b9a913643ac3240133904e0932a968666d96f0` |
| `gravel_bike` | success | 3.365 km | 759.508 s | 170 vertices | `095c7113eb0f87496ca33d368bae1f6bd7040b0fcf5ec4a3190c5209c147b9a2` |
| `mountain_bike` | success | 3.778 km | 980.717 s | 199 vertices | `4c2cc089330839ce2072936d4048287e6fe71e3e41db2bc82d4983a97ffcaf24` |
| `road_bike` | success | 4.490 km | 761.885 s | 177 vertices | `b3bb25c71feebbe872a84294f0ce866051c88a00e400a326f21002338a09a748` |

Thus `hike`/`trail_run`, `city_bike`/`road_bike`, and
`gravel_bike`/`mountain_bike` were not aliases on this fixture. By contrast,
the shorter PR32 Marly smoke fixture produced one shared bicycle geometry for
all four bicycle policies, with different durations. This confirms that
geometry distinction is fixture-dependent. GraphHopper was not running during
this local probe, so these observations are not a GraphHopper comparison and
no qualitative path or parity conclusion is drawn from them.

## Physical acceptance — PASS

PR34 passed physical acceptance on a Fairphone 6 using the debug package
`io.github.victorgabillon.sugarglider.debug`. The installed schema-v2 packs
were `marly-dev-v1` and `paris-dev-v1`; both advertised `foot` and `bicycle`.
FastAPI and GraphHopper were stopped, all `adb reverse` mappings were absent,
airplane mode was enabled, and Wi-Fi was disabled. The app was force-stopped
and successfully relaunched while already offline: the cached PWA shell
remained usable and the native bridge remained available.

Initial capabilities reported:

```text
Installed regional packs (2):
marly-dev-v1 [foot+bicycle],
paris-dev-v1 [foot+bicycle].
```

The supported local profiles were `trail_run`, `hike`, `city_bike`,
`gravel_bike`, `mountain_bike`, and `road_bike`.

### Main offline observations

| Scenario | Result | Route | Identity | Timing |
| --- | --- | --- | --- | --- |
| Hike Marly #1 | success, cold | 3.98 km, 48 min, 246 vertices, 2 snapped points | `hike`, `marly-dev-v1` | initialization 1,109 ms; route 987 ms |
| Hike Marly #2 | success, warm | 3.98 km, 48 min, 246 vertices, 2 snapped points | `hike`, `marly-dev-v1` | initialization 0 ms; route 55 ms |
| Trail run Marly | success | 4.07 km, 28 min, 247 vertices, 2 snapped points | `trail_run`, `marly-dev-v1` | route 54 ms |
| City bike Marly | success | 4.72 km, 18 min, 282 vertices, 2 snapped points | `city_bike`, `marly-dev-v1` | route 51 ms |
| Gravel bike Marly | success | 4.72 km, 16 min, 282 vertices, 2 snapped points | `gravel_bike`, `marly-dev-v1` | route 56 ms |
| Mountain bike Marly | success | 4.72 km, 19 min, 282 vertices, 2 snapped points | `mountain_bike`, `marly-dev-v1` | route 57 ms |
| Road bike Marly | success | 4.72 km, 13 min, 282 vertices, 2 snapped points | `road_bike`, `marly-dev-v1` | route 44 ms |
| Hike Marly three-point via | success, 3 ordered/snapped points | 4.85 km, 59 min, 247 vertices | `hike`, `marly-dev-v1` | route 42 ms |
| Road bike Paris | success, cold after regional switch | 3.87 km, 11 min, 180 vertices, 2 snapped points | `road_bike`, `paris-dev-v1` | initialization 44 ms; route 152 ms |
| Hike Marly after Paris | success, cold after switching back | — | `hike`, `marly-dev-v1` | initialization 40 ms; route 77 ms |

For Hike Marly #1, PSS before initialization, after initialization, and after
routing was respectively 155.5, 197.9, and 229.8 MiB. For Hike Marly #2 it was
155.5, 197.9, and 239.9 MiB. These latency and PSS observations describe only
these runs; they are not general performance claims.

The cross-pack request failed as expected with
`no_covering_routing_pack` and the message “No single installed regional pack
covers all requested points.” Main-run evidence remains ephemeral at
`/tmp/pr34-physical-acceptance.json` and is not added to Git.

### Legacy schema-v1 compatibility

A separate physical compatibility test temporarily replaced only the Marly
manifest with a valid schema-v1 manifest. Airplane mode was not required for
this second test because offline routing had already been demonstrated, but
FastAPI and GraphHopper remained stopped and `adb reverse` remained absent, so
no Sugarglider backend fallback was available.

Capabilities then reported `marly-dev-v1 [foot]` and
`paris-dev-v1 [foot+bicycle]`. A Marly `hike` request succeeded with profile
`hike`, pack `marly-dev-v1`, 3.98 km, and 246 vertices, demonstrating that a v1
pack remains usable for foot routing. A `road_bike` request against the same
Marly v1 pack failed as expected with `no_compatible_routing_pack` and the
message “The region is installed but no pack supports this profile's access
mode.” Thus a legacy v1 pack is not silently treated as bicycle-capable even
when its temporary test TAR happens to contain bicycle data.

The actual Marly v2 manifest was then restored and verified with
`schema_version = 2` and `access_modes = ["foot", "bicycle"]`. Evidence remains
ephemeral at `/tmp/pr34-v1-foot-only-acceptance.json` and is not added to Git.

### Conclusion and limits

The physical run demonstrated all six stable public profile identities routing
locally while preserving the requested profile, foot and bicycle support from
v2 packs, ordered three-point routing, returned snapped requested points, warm
actor reuse, Marly → Paris → Marly switching, explicit cross-region failure,
v1 foot-only compatibility, explicit rejection of an incompatible bicycle
request, and operation with the backend and network unavailable.

PR34 still does not establish GraphHopper route-quality or profile parity.
Equal geometry for several profiles on the Marly fixture is not a parity claim;
the six distinct geometries on the controlled Saint-Germain fixture show only
that the policies are not aliases. The PR35 attribute limitations above still
apply. PR34 also does not establish Auto Tour generation, alternative-route,
round-trip, isochrone, corridor-penalty, or full path-attribute parity, and it
does not remove the GraphHopper reference backend.
