# PR91: native elevation for selected generated routes

Base: PR90, `32844a401fbb9b2dcf68d4ef346caf4558409a6f`. This change adds
optional, selected-candidate elevation to the normal Android Generate workflow.
It reuses the installed V2 region, PR88 native height helper, application-owned
Valhalla actor and PR89 `distance-box-v1`. Generation, ranking, deliberate points,
route geometry, canonical candidate identities and GPX serialization are unchanged.
There is no final interactive chart; PR92 consumes this versioned result.

## Runtime and ownership

After canonical candidates are published, `app.js` synchronizes one selected
candidate with `createSelectedRouteElevation`. A dedicated bounded module worker
prepares samples from the actual returned geometry. The existing authenticated,
main-frame, exact-origin Android bridge transports those samples. The same native
executor used for routing invokes the existing `NativeOfflineEngine.height`,
then runs the PR89 port off the WebView UI thread. No second actor, installer,
DEM reader, routing call or remote elevation API is added.

Elevation never reserves the routing busy flag. A route can queue behind the
single bounded height operation. Cancellation marks that operation and discards
its result; an in-progress JNI call drains safely with its regional/actor file
leases intact. It is not forcibly interrupted. Cancellation is checked before
height, after height and after analysis. New selections serialize behind this
drain. Page/channel epochs and the existing request ledger protect native
responses; a separate selected-job epoch protects WebView publication.

Route editing, regeneration, activity changes, regional selection/build changes
and pagehide invalidate current work. A changed selection immediately clears its
visible values. Only the current job can publish. An eight-entry page-memory
cache retains complete responses keyed by candidate ID, exact geometry digest,
profile, authoritative distance, complete regional reference, analysis version,
sampling version and interval. Editing/regeneration/region/page changes clear
that cache. Candidate selection alone preserves canonical results and ranking.
No analysis is calculated for every candidate before the initial result appears.

## Sampling and identities

Policy `routed-distance-v1` follows PR88: haversine geometry-edge lengths are
normalized to the backend's authoritative total. Samples interpolate adjacent
routed edges, never requested waypoint chords. Duplicate geometry vertices have
zero length and do not create duplicate progress positions. Start/end and exact
cumulative distances are retained. Request coordinates use Python-compatible
half-even rounding to six decimal places, as in PR88; route geometry is untouched.

Routes must be finite, positive and at most 200,000 m, with 2–20,000 finite routed
vertices. Degenerate and dateline-crossing shapes are rejected explicitly. Default
spacing is 50 m. Through 102,350 m, sample positions are multiples of 50 m plus
the exact end. Above that distance there are exactly 2,047 equal intervals,
`actual_interval_m = route_distance_m / 2047`, and 2,048 samples including both
ends. At 200 km the interval is about 97.704 m, below PR89's 100 m gap threshold.
No route is truncated. Coarser long-route sampling can miss narrow climbs; this
policy is not a promise of sampling-density-independent ascent.

Exact geometry identity is SHA-256 of UTF-8
`"sugarglider-route-geometry-v1\0"`, big-endian uint32 vertex count, then each
longitude/latitude as big-endian IEEE754 binary64. Coordinate signed zero is
normalized to positive zero. No rounding enters this digest. This explicitly
versioned binary identity differs from PR88's experiment-specific JSON geometry
hash and from the canonical candidate's rounded signature; neither existing
identity is rewritten.

`analysis.source_sha256` is SHA-256 of the **exact verified V2 elevation manifest
bytes**. It binds the entire component: component ID, bounds, all four tile
paths/sizes/hashes, coverage, acquisitions and unresolved provenance/datum.
It is not one arbitrarily selected HGT hash, nor independent geographic accuracy
certification. Region/build and the full native reference accompany the analysis.

PR89's portable `profile_sha256` byte contract is retained exactly: magic, four
length-prefixed UTF-8 strings, big-endian route distance/sample count, then
index/distance/presence/optional height. Native numeric zero is normalized before
fingerprinting to survive JSON's signed-zero spelling. Golden fixtures and real
native profiles are compared with the unchanged Python implementation.

## Analysis and result contract

`ElevationAnalysis.kt` ports the exact piecewise-linear distance-box integral,
constant boundary extension, retained original endpoints and stable range-sum
tree. Default radius is 50 m; maximum adjacent gap is 100 m. Missing values and
larger gaps split runs without filling. Filtered variation must not exceed raw
variation by more than **1e-7 m**; failure yields unavailable analysis. Runtime
and Python numeric parity use that same tolerance, with exact fingerprint checks.
There is no JavaScript D+/D− calculation or independent smoothing policy.

The optional immutable sidecar is exposed as `state.selectedElevation`, separate
from the frozen canonical candidate/result. Its states are `idle`, `loading`,
`ready` and `unavailable`; it carries selected candidate ID, diagnostic, cache-hit
status and the versioned native result. A `ready` result can itself have complete,
partial or unavailable altitude coverage. A transport/analysis failure leaves
the generated route, selection, export and ranking usable.

`local_elevation_result` includes schema/elevation version 1, operation and
candidate IDs, exact regional reference, actual sampling interval, sample
coordinates and `analysis`. The analysis has the unchanged PR89 fields: source,
geometry and profile digests; routing profile; authoritative distance; height
reference; algorithm/version/parameters; coverage; available count; analyzed and
unknown distances; raw/filtered observed ascent/descent; nullable complete-route
D+/D−; min/max; segments; and original distances/raw/filtered heights with segment
indices. Measurements report native height, analysis and native-operation ms,
process PSS and actor cold status. JavaScript validates shape, fields, coverage,
segments, parameters and exact request binding, then deeply freezes the result.
It does not recalculate ascent/descent.

Partial coverage has null full-route totals. Observed totals cover supported
runs only; isolated available samples have altitude but no observed ascent.
Unavailable altitude is never zero. The basic status paragraph shows D+/D− or
partial/unavailable state and offers cancellation; it does not implement PR92's
interactive graph. Legacy route summary ascent/descent and clean GPX are unchanged.

## Bridge limits and failure behavior

Only `route_elevation` may exceed the previous 8,192-character request limit;
its hard maximum is 262,144 characters. All other existing messages retain their
limit. The request contains version, random 32-hex operation ID, canonical
candidate ID, public profile, authoritative distance, exact geometry digest,
verified regional reference, actual interval and ordered `[distance,lat,lon]`
rows. Native validation independently enforces public profile, route/sample
budgets, finite coordinates, exact endpoints/spacing, strictly increasing
progress, maximum gap and all reference descriptors. Invalid requests fail
explicitly without JNI. Unknown/corrupt/mismatched regional data fails safely.
The geometry digest is an opaque identity at the native boundary; the trusted
WebView sampler derives and binds it to the canonical route. Native code does
not reroute or receive a second whole route to reconstruct that identity.

Replies are capped at 1,048,576 characters; preparation has a 10 s timeout,
native work has a 60 s deadline checked around JNI/analysis, and bridge waiting
is bounded to 65 s. A stuck JNI call cannot safely be preempted; cancellation
retains leases and drains it. One pending native elevation operation, one
preparation worker, 2,048 samples, O(n log n) analysis, the eight-entry client
cache and the existing 64-entry native ledger bound retained work/memory.
No file paths, capabilities or private storage details enter replies.

The normal mandatory V2 installation/readiness rules still apply: an invalid
region cannot become Ready. Optional elevation failure after generation does
not turn a successful route into a generation failure. None of these results
changes datum uncertainty, DEM accuracy or redistribution obligations.

## Reproduction and evidence

Use the same private, installed Yvelines V2 build documented in
[PR90](pr90-v2-offline-regions.md). Do not reinstall its region for this feature.
Build with Python 3.13/uv and Android JDK21/SDK36:

```sh
uv run --offline make check
cd android
./gradlew --offline --no-daemon testDebugUnitTest lintDebug assembleDebug \
  testReleaseUnitTest lintRelease
./gradlew --offline --no-daemon -PsugargliderV2Research=true \
  assembleV2Debug assembleV2DebugAndroidTest lintV2Debug
```

Audit application IDs, certificate, version, permissions, manifests and APK/ELF
16 KiB alignment before installing only `.v2debug` and `.v2debug.test` updates.
The existing Debug certificate remains
`e84155df3a2c7ea48723876b1fe8e0e602cb600f8374d6539b9fea9aa42cfbd7`.
Never clear storage, overwrite production/old Debug, change signing or publish
terrain. Real routes, native profiles, screenshots, APKs and HGT artifacts remain
outside Git. Synthetic golden fixtures contain no terrain/personal snapshots.

The checked-in `V2RegionInstrumentation` has a `planner` phase that opens the
normal Activity and measures UID counters around host-marked Generate actions.
Its cache directory must have a fresh research ID. After startup is ready, a
`planner-ready` marker arms measurement; after the actual UI tests, a
`planner-finished` marker completes it. Optional `block_web_network=true` blocks
only that test WebView's network loads; it never changes phone connectivity or
production behavior. The `analysis` phase runs 17 synthetic missing/gap/noise/
limit goldens on the physical runtime. It does not supply synthetic heights to
the normal planner or modify installed DEM. Real native heights are independently
compared with PR88 HGT probes, and identical samples with PR89's Python analysis.

## Physical results

Fairphone 6, Android 16, existing isolated `.v2debug` installation, installed
Yvelines build `850e2b0576b49966579e1eb01dadb70fe10a9f94546352b0ece69aa92e23d3c6`.
The verified elevation manifest is
`953c51ef75e0217d2476afbb5e7fb1d6b2dd2046e501897aa389304006e71694`.
All rows below are actual normal-Generate results, not injected route responses.
Host UI automation filled editable controls, clicked Generate/candidate/Cancel
buttons and observed the existing bridge. A long-route fixture supplied three
distinct ordered requested anchors; Valhalla produced its entire geometry.
Raw/filtered totals are metres, rounded here only for presentation.

| Generated case | Routed km | Samples | Interval m | Raw D+ / D− | Filtered D+ / D− | Coverage |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Hike selected A | 9.243 | 186 | 50 | 200.970 / 200.970 | 172.6175 / 172.6175 | complete |
| Hike selected B | 9.907 | 200 | 50 | 231.560 / 231.560 | 190.9025 / 190.9025 | complete |
| Trail Run loop | 8.226 | 166 | 50 | 174.050 / 174.050 | 143.9769 / 143.9769 | complete |
| Edited/regenerated Hike | 10.581 | 213 | 50 | 247.620 / 247.620 | 231.0825 / 231.0825 | complete |
| Long gravel loop | 151.917 | 2,048 | 74.21446018563752 | 1639.740 / 1639.740 | 1280.455150 / 1280.455150 | complete |
| Open Hike | 2.655 | 55 | 50 | 24.340 / 78.810 | 19.585 / 74.055 | complete |

All ten captured real profiles were reconstructed in Python using their exact native
heights and distances. Every PR89 analysis field agrees within **1e-7 m**, with
exact portable profile SHA-256. PR88's independent HGT probe checked every sample
against all four pinned source tiles: maximum native/reference height difference
was **0.009999999999990905 m**, within the native helper's centimetre precision.
PR88 geometry sampling also agrees at six-decimal coordinates and within 1e-7 m
of routed progress. This establishes implementation/source parity, not independent
terrain accuracy. No external surveyed or differently sourced profile was used.
The original 25.353 km / approximately 472.45 m PR89 result is not an expected
value for these different geometries and multi-tile source identity.

Selecting B and then A returned A from the bounded cache with identical analysis
and no additional native height request. Selecting A two milliseconds after B's
real height request sent cancellation, drained B, and published only A; no stale
B-ready transition appeared. Profile changes and input edits cleared old values.
Cancelling a new Trail Run analysis preserved its three generated candidates and
reported `elevation_cancelled`; a subsequent Hike Generate succeeded. Fresh
processes reproduced Hike A's exact geometry, samples, heights and fingerprint.
Height calls report `cold_start=false`: normal generation had already opened the
same application actor, which height reused. No extra actor was initialized.

Malformed duplicate progress, non-finite and over-budget requests were rejected
on the real authenticated bridge. Wrong elevation-component and regional-build
references returned unavailable without changing the selected candidate/analysis.
Seventeen synthetic golden cases also passed on the physical Android runtime,
including partial/all-missing/isolated heights, long gaps, noisy slopes, reversal
and 2,048 samples; their complete JSON results match Python within 1e-7 m.
These are explicitly synthetic coverage fixtures: the installed four tiles have
no void cells, and no installed terrain was modified to manufacture missing data.

## Timing and memory

| Case | Native height ms | Analysis ms | Native operation ms | Main-process PSS bytes after operation |
| --- | ---: | ---: | ---: | ---: |
| First Hike A | 139 | 12 | 170 | 312,715,264 |
| Hike B | 12 | 11 | 43 | 276,407,296 |
| Trail Run loop | 13 | 10 | 46 | 279,177,216 |
| Edited Hike | 11 | 13 | 43 | 319,843,328 |
| Long gravel, 2,048 samples | 164 | 76 | 261 | 394,433,536 |
| Open Hike | 3 | 3 | 29 | 402,890,752 |
| Final-package fresh Hike A | 137 | 13 | 166 | 328,880,128 |
| Network-blocked fresh Hike A | 133 | 12 | 160 | 315,063,296 |

Observed foreground loading-to-ready latency, including worker preparation,
bridge, component access and rendering, was 296.4 ms for a fresh Hike A,
943.4 ms Trail Run, 718.5 ms edited Hike, 1,124.0 ms long gravel and 605.2 ms
open Hike. Cached candidate return took 111.8 ms. These are individual physical
measurements, not percentiles or a universal latency guarantee. Native operation
timing excludes subsequent bridge/rendering and final PSS collection.
The final-package fresh Hike took 310.6 ms end to end. The network-blocked Hike
took 2,690.5 ms while a separate full OPFS map/index integrity verification was
running concurrently; its native operation still took 160 ms.

An approximately 631-second earlier main-process poll recorded 899 valid PSS
samples, peaking at 322,433,024 bytes; that window preceded the long-route case.
The maximum observed later per-operation PSS was 402,890,752 bytes. Neither
measurement includes all isolated WebView renderer processes or proves a lifetime
memory bound. Repeated selection, cancellation and fresh-process reproducibility
passed; sustained endurance and low-memory-device profiling remain future work.

## Offline measurement

The first broad startup-plus-UI UID assertion failed. It was investigated rather
than removed: the final harness records startup separately and writes exact
counters before asserting. In a fresh, unmodified WebView, the ready-to-complete
normal Hike Generate interval sent **0 bytes** and received **0 bytes**. Startup
separately sent 3,975 bytes and received 2,827 bytes. A second fresh run with
test-only `WebView.settings.blockNetworkLoads=true` also generated both canonical
Hike candidates and the selected native profile with **0 / 0 bytes** during the
measured interval, reproducing the same geometry/heights/fingerprint. Startup in
that run recorded 4,047 / 2,878 bytes. Phone connectivity settings were unchanged.

A passive DevTools trace of the unmodified run observed only local appassets,
data and blob requests, including bundled fonts and the elevation worker; it did
not attribute the startup UID traffic to a URL. Its cause remains unresolved.
These results validate offline routing/elevation after local readiness, including
with WebView network loads blocked; they do not establish a completely silent
Android/WebView startup. No remote routing/elevation endpoint was configured,
introduced or needed. The harness's strict measured zero-traffic assertion passes
in both final runs, as does the physical synthetic-analysis counter assertion.

## Verification and preserved installations

Final local checks:

- `uv run --offline make check`: Ruff and strict mypy (279 files), **1,378 passed,
  16 deselected**, final run 176.35 s.
- Android Debug **238** and Release **233** unit tests; both lint variants and
  Debug assembly passed. Strengthened native partial/unavailable response checks
  passed in a subsequent Debug/Release run.
- All **309 browser scenarios across 16 harnesses** passed, including 11 new
  elevation scenarios. Existing service-worker generation/hash assertions were
  updated for the actual new bundled assets; their checks remain enforced.
- Research main/test assembly and research lint passed. APK zip alignment and
  ARM64 ELF LOAD alignment are 16 KiB. The physical device has 4 KiB pages;
  structural 16 KiB compatibility was checked, not executed on 16 KiB hardware.

Final research APK SHA-256:
`818b81b7c84588ace132d9b2f740005a896b8b215fa924e203d961102ce678a2`
(25,831,228 bytes); test APK
`680d75492292e6f79eaac9329c20716aa3ae3589af7fda784645b67761446978`
(261,417 bytes). Application ID, version 8 / `1.2.0-v2-research`, certificate,
permissions and manifest match the PR90 research installation. The native
Valhalla library is unchanged. Only those two research packages were updated.
The nine installed native files retain identical paths and SHA-256. OPFS map and
index verification through the existing bounded readers also passed. Existing
production/old Debug package versions, APK hashes and timestamps, and all 83
previously inventoried old Debug private files remain unchanged. No regional
reinstallation, storage clearing, signing change or release publication occurred.

## Changed files and PR92 integration

| Files | Purpose |
| --- | --- |
| `ElevationAnalysis.kt`, `RouteElevationProtocol.kt` | Exact PR89 runtime port, profile fingerprint, bounded request validation and native height orchestration |
| `BridgeProtocol.kt`, `BundledShellPolicy.kt`, `MainActivity.kt` | Existing secure bridge, executor, cancellation and page ownership |
| `elevation_sampling.js`, `elevation_sampling_worker.js`, `route_elevation.js` | Routed sampling, geometry identity, strict reply binding and selected sidecar/cache |
| `app.js`, `state.js`, `index.html` | Async selected-candidate integration, minimal coverage/status and Cancel control |
| `service-worker.js`, `android/shell-assets.txt` | Versioned bundled application assets |
| `ElevationAnalysisTest.kt`, `RouteElevationProtocolTest.kt`, `V2RegionInstrumentation.kt`, `android/app/build.gradle.kts` | Golden/runtime/protocol/physical coverage and fixture packaging |
| `runtime-v1.json`, `sampling-v1.json`, `test_pr91_elevation_contract.py`, `pr91_route_elevation_harness.html/js` | Synthetic cross-language sampling/analysis/identity and browser lifecycle regressions |
| `test_pr26_pwa_architecture.py`, `test_pr30_trail_profiles.py`, `test_pr31_private_planner_location.py`, `test_pr32_on_device_routing_architecture.py`, `test_pr36_offline_maps.py`, `test_pr38_local_waypoint_route.py`, `test_pr39_offline_regional_pipeline.py` | Enforced asset/cache generation pins |
| `README.md`, this document | Runtime contract and measured acceptance evidence |

PR92 should consume only the current immutable `state.selectedElevation`, plot
native-returned sample distances/filtered heights by segment, and preserve visible
missing spans. Check candidate/region/version identity before drawing or hovering;
selection and stale-result ownership already belong to the coordinator. Display
coverage and algorithm/sampling parameters, and distinguish partial observed
totals from full-route totals. Keep chart interactions out of canonical route
geometry, generation/ranking, snapshots and clean GPX. Provide explicit retry or
selection transitions after unavailable analysis. There is no final chart here.

The 50 m radius is the established PR89 versioned policy, not a claim of optimal
smoothing for every terrain. DEM vertical accuracy/datum, horizontal positioning,
50–97.704 m sampling and filtering all affect measured ascent. Fine summits may
be missed; source parity cannot validate those uncertainties. Dataset provenance,
vertical datum and redistribution obligations remain unresolved. Terrain, real
route captures, device logs, APKs and raw profiles remain unpublished outside Git.
