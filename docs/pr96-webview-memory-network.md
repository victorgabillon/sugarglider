# PR96: WebView memory and network investigation

Base: `95b17a9dcbe96401d485736864a427d128428575` (merged PR95).
Private investigation on Fairphone 6, serial ending `28cc`, Android 16,
Google Android System WebView `155.0.8059.43`. No regional bytes, identities,
terrain sources, smoothing policy, routing, ranking or GPX formats change.

The allocation fixes reduce the comparable unprofiled installation/readiness
peak from 1,110,728,704 to 707,513,344 B (36.3%). Reproducible browser-process
requests to Google's Autofill endpoint explain a source of offline-UI traffic;
the strict network/privacy gate remains **NO-GO**. Native routing/elevation
continues to execute locally with zero measured UID traffic.

## Scope and preservation

The four existing production/Debug/research/staging packages were inventoried
before experiments. Experiments use separately signed-with-the-existing-Debug-key
staging namespaces `.v2auditb1`, `.v2auditb2`, `.v2auditf1`, `.v2auditf2`.
Each namespace starts without installed regional data. None of the four existing
applications is overwritten, uninstalled or cleared. Test installations are
retained; no existing region is removed. The normal application ID, version and
Release signing configuration remain unchanged.

Raw evidence, APKs, synthetic QA requests, GPX outputs and traces stay in the
ignored `data/offline-regions/pr96-investigation/` directory. The unchanged
private PR95 HTTPS fixture is bound only to host loopback, exposed over one owned
ADB reverse. It uses the existing staging-only CA. No system certificate,
connectivity, VPN, Safe Browsing or Google Play setting is changed.

## Confirmed unnecessary allocations and fixes

1. `local_region_store.js` constructed a complete planning session solely to
   validate installation. That projected every Nature feature, froze the raw
   document, and built regional spatial trees before discarding the result.
   Installation now consumes a shared polygon-validation generator one feature
   at a time. Runtime sessions consume the same generator into their index.
   Metadata, coordinates, counts, polygon topology and the shared 40-million
   validation work budget still use the same checks. Validation precedes the
   completion marker and active pointer.
2. Bounds reductions allocated a fresh four-number array for every input item.
   They now update a locally owned bounds array using the same `Math.min/max`
   operations. Sorting, projection, work accounting and geometry decisions are
   unchanged.
3. The page kept its installation worker alive after installation. The installer
   now owns a fresh worker per operation and closes it after a definite success
   or failure. Cancel still waits for acknowledgment; termination never races an
   outstanding OPFS write. The worker serving committed planning queries remains
   independent.

The shared shell generation advances from v96 to v97 so browser caches cannot
retain an older installer alongside the changed modules.

### Host allocation attribution

An isolated Chromium page consumed the exact private Yvelines Places and Nature
indexes: 261,132 / 10,634,994 compressed bytes, 3,507,384 / 45,278,253 expanded
bytes, and 4,415 / 62,191 features respectively. The probe decoded both documents
and performed installation validation. It did not route, render a map, or use a
synthetic replacement for the real index.

| Same host probe | Before | After |
| --- | ---: | ---: |
| Validation duration (one profiled run) | 6,363.7 ms | 3,535.0 ms |
| Decode + validation | 7,811.7 ms | 4,965.9 ms |
| Sampled cumulative allocations, including collected objects | 2,149,733,688 B | 1,367,601,720 B |

Sampling interval: 16 KiB, V8 HeapProfiler, with objects collected by minor and
major GC included. These are statistical estimates of allocation churn, **not
live heap, peak memory or PSS**. The before profile attributes large allocation
stacks to polygon validation, `inRing`, spatial-tree sorting, `decodeRegionalIndex`,
`freezeData/Object.values` and projection. This supports a focused allocation fix;
it does not establish a leak.

## Network attribution and remaining failure

The existing strict planner assertion remains: any nonzero transmit or receive
UID delta fails. The new control harness records observations and deliberately
does not equate measurement completion with privacy acceptance.

Each minimal control ran for 60 seconds visible and 15 seconds after Activity
destruction, twice in a newly isolated app. No CDP was attached to these controls.
The application process recorded `TrafficStats` once per second; the host observed
owned TCP metadata and all associated process PSS separately.

| Control | Repeat 1 Tx / Rx | Repeat 2 Tx / Rx |
| --- | ---: | ---: |
| Native Activity, no WebView | 0 / 0 B | 0 / 0 B |
| Empty WebView, no page load | 0 / 0 B | 0 / 0 B |
| WebView loading `about:blank` | 0 / 0 B | 0 / 0 B |

No owned TCP socket appeared in these six windows. Socket listing emits a
netlink-permission warning on this device, so absence in that listing alone is
not proof of no network. The independent UID counters were also zero.

The full bundled application reproduced an external Google IPv6 TCP/443
connection. A browser-process network trace started **before navigation to the
unchanged planner**, using an empty WebView only to attach CDP early. Both
independent fresh-WebView runs captured request origins for
`https://content-autofill.googleapis.com`, with DNS, certificate verification,
TLS/HTTP2-session and QUIC-attempt metadata. The first trace contained 844 netlog
events: URL-origin fields identified 124 local-app-assets events and eight
Autofill events. These are event counts, not request or packet counts.

| Controlled window | Tx / Rx |
| --- | ---: |
| Fresh planner, repeat 1 | 6,526 / 9,259 B |
| Fresh planner, repeat 2 | 6,428 / 8,713 B |
| Per-Activity Autofill exclusion, repeat 1 | 6,580 / 8,992 B |
| Per-Activity Autofill exclusion, repeat 2 | 6,855 / 9,416 B |
| Trace before planner navigation, repeat 1 | 10,074 / 12,189 B |
| Trace before planner navigation, repeat 2 | 11,696 / 16,655 B |
| Minimal intercepted local HTML, no forms/scripts/map | 72 / 291 B |

Planner controls used fresh WebView data directories, 60 s visible and 15 s after
Activity destruction. The supported Android
`IMPORTANT_FOR_AUTOFILL_NO_EXCLUDE_DESCENDANTS` setting was applied to the decor
view before Activity creation; it **did not prevent the traffic**. It remains a
test control and is not shipped as a purported fix. No supported per-WebView
crowdsourcing opt-out was established. Android's public tracing API stripped
network arguments on this provider; direct CDP netlog supplied the destination
metadata missing from page-level `Network` events.

Chromium's Android Autofill client obtains the browser-process URL loader;
its Autofill manager can request server predictions for forms, and the
crowdsourcing manager defines this Google endpoint. The measured origins and
source mechanism attribute a reproducible source to WebView/Chromium Autofill,
independently of route or elevation calculation. Page-only app-assets requests
and `blockNetworkLoads` do not establish zero UID traffic. Native-only route and
height phases separately measured zero bytes.

This does **not** reconstruct PR95's exact 4,354 / 7,684 B window, assign every
UID byte to one service, identify encrypted payload contents, or establish that
personal route data was or was not transmitted. The small 72 / 291 B local-HTML
control delta remains unattributed. The full UI acceptance also retained its
strict failure (7,523 / 8,899 B in the first window); completing functional checks
does not turn that into a network pass. No application-level Google fetch,
MapLibre download, routing request or native elevation request accounts for the
Autofill events in the startup controls.

Settled UI phase observations use per-second UID samples at host-recorded
boundaries (roughly one-second uncertainty), not individual-request attribution:

| Actual UI phase | Duration | Tx / Rx |
| --- | ---: | ---: |
| No selected region, idle | 15.2 s | 0 / 0 B |
| Select Yvelines, no Generate | 8.9 s | 0 / 0 B |
| First hike Generate/display | 9.0 s | 6,017 / 7,843 B |
| Next five profile Generate/display windows | 4.2–4.6 s each | 0 / 0 B each |
| Forest Generate/display | 4.5 s | 1,506 / 1,056 B |
| Long 2,048-sample Generate/display | 5.7 s | 0 / 0 B |
| Successful chart/map touch window | 2.4 s | 0 / 0 B |
| Cancel and Retry | 4.7 s | 0 / 0 B |
| Auto Tour Generate/display | 10.2 s | 0 / 0 B |
| 60 candidate selections | 72.2 s | 1,129 / 1,114 B |
| Four UI region selections and routes | 29.3 s | 0 / 0 B |
| Three background/foreground cycles | 30.8 s | 0 / 0 B |
| Actual GPX picker/Save in later warm window | 9.0 s | 0 / 0 B |

The candidate/switch window failed its strict settled assertion at 1,129 /
1,114 B, with a separate startup delta of 5,433 / 8,068 B. The successful GPX
window measured 0 / 0 B **after settling**, but still had 719 / 914 B at startup.
Thus a passing warm settled window does not establish offline-UI network silence.
A network event coinciding with Generate is not proof Generate caused it;
startup-only controls reproduce the service traffic and native-only controls
remain zero. System document-picker traffic belongs to a separate UID; these
measurements make no whole-phone zero-network claim. Private HTTPS installations
are separate expected-download windows and are not included in the zero-network
acceptance numbers.

Tracing uses Chromium's ordinary `netlog` category, not its sensitive category,
raw socket capture or a TLS interceptor. Raw socket capture is never enabled. The first two default traces also
contained TLS handshake byte fields; these were removed, with redaction hashes
retained, and saved network parameters now use an explicit metadata allowlist.
Subsequent startup traces filter before writing to disk. The
fixture has no participant credentials and uses only synthetic public QA points.
Only request origins, allowed local resource paths, event types, counters and
allocation metadata are used for analysis. Device-local socket addresses are
omitted from the host observer output.

Primary references: Chromium's
[trace observer](https://chromium.googlesource.com/chromium/src/+/refs/heads/main/net/log/trace_net_log_observer.h),
[Android Autofill client](https://chromium.googlesource.com/chromium/src/+/refs/heads/main/components/android_autofill/browser/android_autofill_client.cc),
[Autofill manager](https://chromium.googlesource.com/chromium/src/+/refs/heads/main/components/autofill/core/browser/foundations/autofill_manager.cc)
and [crowdsourcing manager](https://chromium.googlesource.com/chromium/src/+/refs/heads/main/components/autofill/core/browser/crowdsourcing/autofill_crowdsourcing_manager.cc).
Source inspection establishes implementation mechanisms, not the contents of
any observed encrypted request.

## Physical memory methodology

Every sample parses every process block from a single
`dumpsys meminfo --package PACKAGE` invocation, summing main and associated
WebView processes. Individual process reads within that invocation have a small
time skew. Sampling is approximately every two seconds; short peaks may be
missed. Failed/restart-gap samples remain invalid, never zero-memory successes.

Android Java/native/graphics/category breakdowns are retained alongside aggregate
PSS. CDP attaches to each worker and the page separately, recording V8 heap and
backing storage. Memory-infra light dumps provide process-wide V8, PartitionAlloc,
malloc, Blink GC and graphics attribution. Those allocator figures overlap and
must not be added to each other or treated as PSS.

Profiled and unprofiled pairs are reported separately. Profiling changes GC and
adds trace-buffer/serialization allocations; comparison to PR95's earlier
1,782,868,992 B peak is historical context only. In the first baseline trace the
renderer's maximum process-wide V8 worker allocation was 313,708,368 B (heap
310,104,064 B); its page V8 maximum was 21,068,500 B. This identifies substantial
worker allocation that a page-only JS heap measurement would miss.


### Comparable Fairphone results

All four runs installed the same 210,223,038 B, five-component IGN Yvelines
build `a92396de46a6fed5fa1a49fc8c939c39bc6371424aa90c9b71f237878294c7fd`.
Each run used a fresh application storage namespace and the normal private HTTPS
installer. The workload was 45 s empty startup, installation plus readiness,
90 s activated idle, normal reopen, and process restart with 60 s observation for
each. The app remained foreground during valid observations except one transition
sample in each unprofiled run. Restart gaps are excluded, not converted to zero.

| Pair | Before installation/readiness peak | After | Reduction |
| --- | ---: | ---: | ---: |
| With worker sampling and memory tracing | 819,375,104 B | 665,151,488 B | 18.8% |
| Without profiling | 1,110,728,704 B | 707,513,344 B | 36.3% |

At the unprofiled peaks, main / associated PSS was 199,588,864 / 911,139,840 B
before and 201,241,600 / 506,271,744 B after. The reduction occurs in the renderer;
it is not explained by measuring only the Android main process.

| Unprofiled lifecycle | Before median / peak | After median / peak |
| --- | ---: | ---: |
| empty-startup-idle | 333.4 / 337.6 MB | 330.1 / 334.3 MB |
| Downloading the map | 348.0 / 369.1 MB | 350.3 / 382.3 MB |
| Downloading routing and elevation data | 362.4 / 362.5 MB | 343.9 / 344.0 MB |
| Downloading and checking places and nature | 597.9 / 797.3 MB | 478.2 / 539.6 MB |
| Verifying all regional data | 676.6 / 679.0 MB | 328.3 / 328.3 MB |
| Region installed | 773.6 / 1020.4 MB | 413.7 / 614.2 MB |
| activated-idle | 577.2 / 1110.7 MB | 541.9 / 707.5 MB |
| normal-reopen | 616.5 / 762.1 MB | 588.0 / 715.7 MB |
| restart | 623.6 / 764.6 MB | 588.5 / 718.5 MB |

Unprofiled final idle samples were 577,215,488 B before / 541,782,016 B after;
post-restart final samples were 582,333,440 / 551,811,072 B. Readiness includes
loading the committed planning index and the map. Download completion alone is
not the end of the memory workload. The two profiled runs have additional
trace-export/serialization work; a baseline label boundary included trace export
in activated idle, so the unprofiled pair is used for idle comparisons.

The profiled installer worker's sampled used-JS peak fell from 230,283,564 to
130,468,768 B. Sampled backing-store maxima were 11,170,638 / 68,594,594 B;
those maxima need not occur at the same time and are not additive peak totals.
The baseline installer target remained alive until tracing ended; the fixed
installer target disappeared after completion, while the separate planning worker
continued serving queries. Renderer-wide traced V8 worker allocation maxima were
313,708,368 / 251,735,972 B. The page's backing-store maxima were 95,512,009 /
48,031,081 B, so page-only used-JS metrics would miss buffers as well as workers.

Fetch/OPFS map transfer awaits each write and does not concatenate the full map
archive in application JavaScript. Hash verification reads 256 KiB slices. The
Places/Nature path still concatenates its bounded compressed download and parses
a bounded expanded JSON document. Chromium may retain dead buffer allocations
until GC; backing-store and PartitionAlloc measurements do not prove each buffer's
exact owner. The trace/source evidence narrows the large allocation stages without
pretending to account for every byte of Android's `Unknown` bucket.

No OOM or process death occurred during these installations. There is no
monotonically growing post-restart baseline here and no established leak.
Measurements are for this device, data and WebView version: 7,761,154,048 B
reported physical RAM, 256 MiB Java growth limit, 512 MiB Java maximum, 4 KiB
physical pages. Java limits are not renderer/native-process memory limits. No
universal device threshold or arbitrary native/cache cap is introduced.

## Automated regression checks

- Python 3.13.5: `make check` passes Ruff formatting/lint, strict mypy over
  291 source files, and **1,440 tests** (16 live-backend integration tests
  deselected by the repository's normal check target). Nine existing rasterio /
  NumPy deprecation warnings remain. The pinned `dem` dependency group is
  installed. The initial incomplete environment and stale mypy import cache were
  corrected before the successful full run.
- Browser: **49 harnesses / 928 reported cases, zero failures**. The existing
  malformed index corpus now rejects through both installation-only validation
  and runtime session construction. Focused new tests cover exact ownership,
  overlapping requests, late Cancel versus successful commit, worker closure on
  success/cancellation/checksum failure/worker failure, and fresh-worker Retry.
  The existing browser CI entry point now runs both the structural-validation
  corpus and all eight new installer regressions; its bundled-startup checks
  also pass with normal and offline configuration.
- Existing explicit host-GC regression passes: Places-only search does not retain
  Nature, retired map archives are released, and no unknown source gets a network
  fallback. Explicit collection is confined to that host regression, not physical
  PSS measurements.
- Four real Chromium viewports (360, 390, 420, 1280 px) pass mouse, touch where
  applicable, keyboard, scrolling and MapLibre reload/resize/remove acceptance.
- Android: **240 Debug + 235 Release unit tests**, no failures or skips. Normal
  Debug and Release assembly/lint pass; isolated staging assembly/lint also pass.
- Normal Debug and unsigned Release APKs pass ZIP 16 KiB alignment and all ELF
  load segments have 16 KiB alignment. The Valhalla library remains byte-identical:
  `09b6d312b19caa5410561b804213641f5f8a772d1b3db570cc17bac8a55fb878`.
  Actual device pages are 4 KiB, so this is packaging/static ELF evidence, not a
  physical 16 KiB execution claim.
- Release retains the normal app ID, version code 8 / version 1.2.0, Internet and
  foreground coarse/fine-location permissions. No private CA, DEM, PMTiles,
  research Activity, test observer or new permission enters Release.

The original zero-UID planner assertion is unchanged. Passing browser and native
checks does not override a failed network/privacy gate.

## Reproduction

Use Python 3.13, `uv sync --group dem`, then `UV_NO_SYNC=1 make check`
(the latter retains the pinned optional DEM tools). Serve the repository
on localhost and open every `tests/browser/*_harness.html` in a fresh Chromium
context with non-local requests blocked. Also run the explicit retention and
interactive-elevation harnesses; the latter requires real pointer/touch events,
not only JavaScript-dispatched events.

From `android/`, with Java 21, Android SDK 36 and external Release signing unset:

```sh
./gradlew --no-daemon testDebugUnitTest testReleaseUnitTest lintDebug lintRelease assembleDebug assembleRelease
```

For physical controls, build the existing private staging workflow with
`-PsugargliderV2Staging`, an independently verified private catalog and existing
staging CA, and a **new** `-PsugargliderV2StagingSuffix=.v2audit...` namespace.
Verify both APK application IDs, target-package identity and the existing Debug
certificate before installation. The default `.v2staging` suffix must not be
used to overwrite an existing acceptance installation.

Create a fresh `cache/<research_id>` directory with `run-as` in that isolated
package. `V2RegionInstrumentation` supports:

- `phase=network_control`, with `control-mode` containing `native`, `webview`,
  `blank`, `assets` or `planner`; optional `fresh_webview=true` and
  `exclude_autofill=true` reproduce the causal controls.
- `phase=network_preload`, `fresh_webview=true`: wait for `preload-ready`, attach
  metadata-only CDP netlog to the blank page, create `preload-start`, wait for
  `preload-finished`, collect/filter the trace and create `preload-collected`.
- Existing `phase=planner`: create `planner-ready` after startup settles and
  `planner-finished` after the window. Its zero-UID assertion remains strict.
  `block_web_network=true` is an additional WebView control, not a whole-device
  firewall or proof of zero platform traffic.

For example, after preparing an isolated directory and control-mode file:

```sh
adb -s 014728cc shell am instrument -w -r \
  -e research_id pr96-control-new -e phase network_control \
  -e fresh_webview true \
  io.github.victorgabillon.sugarglider.v2auditNEW.test/io.github.victorgabillon.sugarglider.V2RegionInstrumentation
```

Replace `NEW` with the lowercase alphanumeric suffix actually built; package
names in commands must match verified APKs. Do not reuse research IDs: logs are
append-protected. Collect `uid-series.jsonl`, control results, exact process IDs,
foreground state and one `dumpsys meminfo --package PACKAGE` snapshot about every
two seconds. Sum all process blocks in that snapshot. Never substitute main-only
PSS or the maximum of separately timed process samples. Preserve invalid gaps.

For the comparable installation workload, install the exact same five-component
Yvelines bytes into two fresh baseline/fixed namespaces; observe 45 s startup,
the normal private HTTPS installation and readiness, 90 s idle, normal reopen
and process restart. Repeat once with worker allocation/memory tracing and once
without it. Separate expected private-download traffic from offline UI windows.
Do not force GC in physical comparisons. Complete onboarding before actual chart
pointer tests; a modal can allow scripted Generate while intercepting touches.

## Evidence boundaries and follow-up

The private evidence directory contains per-run meminfo snapshots, process/UID
series, phase boundaries, component verification, APK/certificate inventories,
metadata-filtered traces and failed attempts as well as passing attempts. It is
intentionally not a public artifact. Investigation helpers use synthetic public
QA coordinates and no participant capabilities. Publication approval records,
DEM provenance, IGN/Copernicus artifacts and the public V1 catalog are unchanged.

A network/privacy resolution requires a supported WebView/provider control or
an independently validated application change that prevents the observed service
requests, repeated cold/warm/lifecycle windows with strict zero UID counters,
and attribution or elimination of the residual local-HTML bytes. Framework
Autofill exclusion alone has already failed this test. Do not disable Safe
Browsing, alter device trust/networking, or whitelist nonzero traffic to obtain a
pass. Additional devices/WebView versions and larger regions need their own
memory acceptance; the reductions here are not a universal memory guarantee.

## Physical functional acceptance

All tests use the separately verified `.v2auditf2` application and its original
Debug certificate, not the existing `.v2staging` installation. Actual native
bridge responses feed the real UI; no successful route/height result is forged.

- Five-component Yvelines installations completed in all four fresh memory
  namespaces, with readiness, reopen and restart. The fixed final namespace also
  installed the genuine smaller IGN Marly region through the normal private
  HTTPS installer (8,471 ms), retaining Yvelines.
- Generate passed for all six public profiles. A forest loop measured 7,942 m,
  160 height samples, D+ / D− both 135.2625 m. The long gravel loop measured
  151,697 m, exactly 2,048 samples, D+ / D− both 990.4214595212833 m. Initial
  long-route sampling/analysis/combined times were 160 / 77 / 258 ms; a later
  traced UI repeat took 301 / 86 / 409 ms. These are observed executions, not a
  universal performance guarantee.
- Actual trusted touch events at three chart positions created the map position
  marker. Keyboard inspection, Show on map and canonical GPX comparison passed;
  route and height bridge-call counts did not increase from chart interaction.
- Visible elevation cancellation was nonfatal: the candidate remained available,
  and Retry completed without another routing call.
- Sixty selections between two genuine returned Auto Tour candidates passed at
  one-second spacing, retaining exactly one chart and one map archive, clearing
  stale position markers, preserving the exact candidate objects and producing
  byte-identical canonical GPX. This functional retention check complements the
  longer installation/reopen/restart observations; it is not an unbounded leak
  proof.
- UI Yvelines → Marly → Yvelines → Marly Generate passed. Every analysis carried
  the selected region's immutable build/source identity and IGN69 reference, and
  none reused a cached analysis across switching. The QA route lies inside both
  regions, so equal route geometry and heights are expected; independent graph
  file hashes establish genuinely distinct regional graphs.
- Three explicit background/foreground cycles completed. The app remained the
  foreground owner in the other functional windows except the owned Android GPX
  picker and deliberate lifecycle transitions.
- Separate headless native phases passed six profiles × open/loop routes, actual
  long-route height sampling plus 20 warm repeats, analysis fixtures, missing and
  void-height semantics, invalid/over-budget/identity-mismatch input rejection,
  boundary sampling, leased-file removal rejection and distinct-region actor
  switching. All five phases recorded **0 Tx / 0 Rx bytes** and **zero regional
  mappings after actor closure**. The long native cold call took 2,516 ms and a
  warm call 174 ms; post-closure main-process PSS was 69,686,272 B, not aggregate
  WebView PSS.

Independent Python analysis reproduces the Android elevation result field by
field within **1e-7 m** for numerical values. Direct verified HGT probes agree
with every available native height within **0.010001 m**, accounting for native
centimetre quantization; null availability must match exactly. All **18 captured
profiles / 7,268 height samples**, including the original
eight six-profile/forest/long captures and subsequent switching/retry captures,
pass this comparison. These checks validate
implementation agreement against the selected source; they do not establish
survey-level DEM accuracy or a universal expected D+.

Failed test attempts are retained. The initial two chart attempts touched the
first-run profile dialog covering the chart; diagnostics confirmed trusted events
hit badge images, not the profile. Completing normal local onboarding made the
same chart test pass. A new QA request asking for four Auto Tour candidates was
correctly rejected by the local three-candidate limit; the existing valid fixture
returned two genuine candidates for endurance. The initial Save driver expected
English text, while Android's picker uses French; its stable button ID is used
for the final attempt. None of these driver corrections changes product behavior
or converts a nonzero UID delta into success.

The actual Android document picker saved a new synthetic QA GPX (7,806 bytes);
the saved file, native payload and canonical exporter output are byte-identical.
The bridge acknowledged `saved`. It contains exactly one track/segment, no GPX
route, extensions or heights. Only that newly named QA file was created; existing
exports were not replaced. Clear removed the generated candidate, all points,
the chart and map position marker, and reset elevation to idle. The initial Clear
driver incorrectly expected a confirmation for a route with zero mandatory
intermediate points; the product had already cleared it. A subsequent verified
Clear and 90 s idle window completed with **0 / 0 B**, including zero measured
startup delta in that run.

### Functional-window memory limits

Aggregate PSS is also retained for these workflows; they are additional windows,
not the controlled baseline/fixed installation pair. The 60-selection phase had
688,075,776 B median / 767,718,400 B peak, ending at 691,143,680 B. Region
switching peaked at 892,019,712 B. The separate long-route/touch window reached
**1,213,277,184 B while loading the selected region**, then 889,273,344 B during
long Generate and 914,551,808 B during Cancel/Retry. Thus 707,513,344 B is the
measured fixed **installation/readiness** peak in the comparable unprofiled run,
not a ceiling on every later UI activation. Runtime index construction and
rendering still need substantial transient memory; these netlog-only windows do
not identify every allocator responsible for that later activation peak.

After verified Clear, the first idle sample was 809,374,720 B; the 90 s idle
median was 619,013,120 B and the final sample 617,961,472 B. No forced GC was
used. Releasing chart/marker/route objects does not require immediate renderer
page or allocator-cache release. These observations do not prove a leak and do
not certify this workload for low-memory phones.

## Final preservation and packaging audit

All **nine installed APKs** across the four protected apps and their two test
packages match before/after SHA-256, paths and signing certificates. All **815
readable private files** in older Debug/research/staging storage match exactly:
no additions, removals or changed bytes. Production private storage is not
readable without privilege, so this audit makes no private-file hash claim for
production; its split APKs and certificates were verified unchanged and it was
never targeted by an installation or clear operation.

All **19 installed component payload files** for Yvelines and Marly independently
match the two verified manifests, including the map/index bytes in OPFS and
native graph/height files. The graph hashes differ (`d47b022d…` / `01a8eab9…`),
as do immutable build and elevation-manifest identities. No published or private
regional artifact was rebuilt or altered for this investigation.

The final normal Debug, unsigned Release and isolated test-app APKs pass ZIP and
ELF 16 KiB alignment, including load-offset/address congruence. Release DEX and
manifest contain no review Activity, instrumentation observer or research class;
all bundled JavaScript matches source, and no private CA, HGT, PMTiles or routing
PBF is embedded. Bundled font glyph PBFs remain intentional application assets.
The app ID/version and permissions are unchanged. The existing Debug certificate
was used only for isolated test installations; Release signing remains untouched.
The owned loopback HTTPS server and ADB reverse/CDP forwards were removed at
completion; ADB connectivity and installed test-region data remain available.

## Acceptance decisions

| Gate | Decision | Evidence and limit |
| --- | --- | --- |
| A. Offline routing/elevation functionality | **GO for tested workloads** | Real six-profile routing, verified IGN heights/math, chart, Cancel/Retry, selection/switching, native Save, cleanup and restart pass. Native phases use zero network. System connectivity was preserved, not switched off; this is local execution evidence, not a whole-device air-gap test. |
| B. Application network/privacy behavior | **NO-GO** | Repeated Chromium Autofill requests under the app UID, failed strict UI windows and an unattributed small control delta. Tested framework exclusion does not prevent them. Warm zero-byte windows do not override these failures. |
| C. Regional installation memory safety | **GO for this FP6/data workload** | Comparable fixed install/readiness peaks fall 18.8% profiled and 36.3% unprofiled, with no OOM during installation and successful reopen/restart. Later runtime activation can still peak at 1.213 GB; low-memory devices/larger regions are not certified. |
| D. Technical code integration | **GO** | Focused allocation/lifetime fixes, unchanged structural validation and golden results, full automated checks, physical regressions and Debug/Release packaging pass. Merge can carry the documented existing privacy release blocker; the PR remains draft for review. |
| E. Public release readiness | **NO-GO** | Gate B remains failed. The unchanged normal bundled catalog still advertises V1 build `902f951b…`; a coordinated, approved V2 catalog/data/app rollout remains required. This investigation grants no publication or rights approval. |

No merge, release, Google Play action, public catalog update or regional artifact
publication was performed. Follow-up privacy work should begin with the captured
Autofill origins and the failed supported-exclusion control, retaining the strict
zero-network gate. Do not reinterpret functional GO or a smaller measured memory
peak as public-release approval.
