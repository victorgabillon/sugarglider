# PR94: V2 elevation distribution staging

Base: main `cac2b415e7eb6db7a9129e6ff50068b3414c29eb`.
Source/host review: 16 October 2026. This is a private release-staging change,
not publication approval. See the [rights dossier](pr94-terrain-rights.md).

## Acceptance assessment

The source/host experiments dated 16 October remain historical evidence. The
18 October recovery and Fairphone measurements below use a **new immutable
private build**, not the lost original artifact. Neither the user's permission
to reconstruct/test nor this report is operator publication approval.

| Requested acceptance decision | Decision after physical acceptance |
| --- | --- |
| PR94 technical integration | **NO-GO for final acceptance:** normal installed-source tests pass; physical failure/lifecycle/final-audit gates remain after USB disconnection. |
| V2 installation engineering | **NO-GO for complete acceptance:** normal phone HTTPS install/cancel/resume/restart pass, but isolated corruption/interruption/quota tests remain unrun. |
| Copernicus terrain quality for hiking | **NO-GO for a validated ground-terrain accuracy claim.** DSM canopy/building effects and the historical ~40% long-route IGN difference remain. The conversion/native format is suitable for private research. |
| Terrain redistribution approval | **NO-GO:** no actual operator publication approval exists; every real manifest remains `publication_allowed=false`. |
| Public Android release | **NO-GO:** exact-build approval, coordinated public V2 catalog and outstanding PR93 device/release gates remain. Normal Release still bundles unchanged V1 offerings and fails the explicit V2 release preflight. |

## Fairphone acceptance and artifact recovery: 18 October 2026

Starting PR94 head: `a6e71f00fa187e0c6850e987f0647fd1321e9cb6`.
ADB serial `014728cc` is the actual Fairphone 6, Android 16. Before any launch or
update, an independent read-only inventory verified installed APK certificates,
package metadata and readable private-file hashes. Staging had **zero private
files**, so there was no existing partial installation to overwrite. Production's
four splits were verified; production private data is inaccessible to `run-as`,
so it is not claimed to have been read or individually hashed.

Both original `/tmp/sugarglider-pr94-source` and `/tmp/sugarglider-pr94-data` were
missing. Searches found only historical Mapzen artifacts, which were preserved
and rejected as substitutes. The user explicitly authorized private reconstruction
and, after the different graph hash was explained, chose the simplest path of
testing the fresh identity with the difference recorded for a later decision.
No assumption of approval or byte equivalence was made.

The existing branch was recovered into ignored durable
`data/offline-regions/pr94-acceptance/source`; sibling `private` and `evidence`
hold all real data, TLS keys, APKs, raw logs, captures and screenshots outside Git.
All 11 originals (489,501,031 bytes) reproduced the pinned SHA-256 values:
14.71 s, maximum process RSS 49,448 KiB. A host reboot interrupted the first
conversion/build-check attempt; its partial output was retained separately.
The successful converter took 474.52 s / 207,388 KiB, with **all four compressed
HGT files byte-identical to 16 October**, including the hashes listed below.
Another 100 original-COG/manual-geoid controls and 14,404 seam comparisons pass;
maximum integer quantization error is 0.489426 m, not terrain accuracy.

The graph rebuild used the same pinned 3.9.1 image, unchanged PBF and verified
map/Places/Nature bytes. It took 523.32 s / maximum process RSS 2,676,276 KiB.
Its 99,481,600-byte graph has a different SHA-256; consequently the documented
region received a new identity. **The original graph was not reproduced.**

| Artifact | Immutable identity |
| --- | --- |
| Lost 16 October private build | `9799c1034b2e581ee1cf9cba522c4cf873c863280f8608506c15af0b4ba46efe` |
| Lost original graph | `7d85ebdeefbbabc1716a4ffd8a50b7e9bea0083741b26b4d4aee596474e8fd09` |
| Actually installed/tested 18 October build | `8df4d6d9c7cb18b5da524dd5ab38291ef77bff2004471a38cbc346dc74c46f6c` |
| Actually installed graph | `cb8bb5dc00e5981c366496515ecc5ae5354a35806bfc334283a3cb416933186c` |
| New regional manifest | `f5500e85efa7b528e72a898cd8abd51e18e5226e0afcb78c3901a6e2f7cf41bb` |
| New elevation manifest | `52f0720ddf5eee7e2b5c1ecec74ca45eb13f520c33757d82c48fd2b3f4caf322` |

TAR member metadata/order/offsets/sizes match the retained archive layout. The
original graph bytes are absent, so the cause of the difference is unresolved.
The actual [Valhalla 3.9.1 build-ID implementation](https://github.com/valhalla/valhalla/blob/3.9.1/src/mjolnir/util.cc#L405)
derives the tile-set ID from content hashes; it must not be dismissed as a random
nonce or timestamp. No graph-header editing, identity coercion or claim of exact
reconstruction was used. This limitation remains explicit for the user's later
artifact/reproducibility decision.

A fresh local CA/server chain and catalog were generated because the old private
keys were gone. Only staging and its test APK were updated **in place** after
independent ID/version/certificate/permission/asset/catalog/alignment audits.
No package was uninstalled or cleared. The cert is unchanged:
`e84155df3a2c7ea48723876b1fe8e0e602cb600f8374d6539b9fea9aa42cfbd7`.

| Installed item | SHA-256 |
| --- | --- |
| `.v2staging`, code 8, `1.2.0-v2-staging`, 25,618,063 bytes | `74b3bcd740e4c26a67e5e4ac232624852a4ef202e3664b1489a744d9e0dd5a26` |
| `.v2staging.test`, 258,008 bytes | `6ded2bcda55086473aa3c2690555c807772797f66fdadf631b338cceee292c5e` |

### Actual HTTPS installation, restart and immutable-file checks

The server binds only `127.0.0.1:9443`, reached by a task-owned USB reverse tunnel.
No phone connectivity, trust store, USB authorization or system CA was changed.
Strict TLS 1.3 with explicit private CA/hostname verification, exact origin CORS,
identity encoding, no redirect/cookie/credentials and real 127-byte PMTiles ranges
pass. Default system trust correctly rejects the private CA. All 11 component
files (218,670,766 bytes) and the catalog/root manifest were fetched and matched;
actual APK/catalog preflight passes privately and public-mode preflight rejects.

The actual Regions UI discovered the bundled catalog. Cancelling the fresh map
download at 4.6 MB left an explicit incomplete state and **no active build**.
Normal Download resumed it and committed all five components; all five checkmarks
were Ready by the 30.91 s observation after resume. This is an observed upper bound
for download/verification/readiness, not a more precise installer timer.
Installation UID traffic, including cancelled bytes/TLS/startup, was
129,738 bytes TX / 225,518,036 bytes RX. It is intentionally separate from offline
routing traffic. All 11 installed component files were independently SHA-verified:
native graph/elevation via actual private files and map/Places/Nature via bounded
OPFS reads. The committed build and five-component Ready state survive process
restart. No raw regional files were pushed into Android storage.

| Installed component payload | SHA-256 |
| --- | --- |
| Map archive | `a5e2af1ac3785d370c84a5fc0c46e65ba764a2331d4d86b7e2c6b25de52bce3d` |
| Routing graph | `cb8bb5dc00e5981c366496515ecc5ae5354a35806bfc334283a3cb416933186c` |
| Places gzip | `1ace12b6869ae74f97a673ac9fe6f706cb17a6b7f29b35a9b0dbafd095ea4649` |
| Nature gzip | `abb0819a4f4b02d8ee844aa19de71c1760e0b63a1a9f7bd3410513d82dca7b90` |
| Four HGT gzip files | Exact four full hashes in the HGT table below |

### Actual normal Generate, native heights and interactive UI

All **24** normal Generate cases pass: six public profiles × open/loop × two runs.
Every repeat preserves the exact returned geometry, authoritative distance,
profile, candidate identity and elevation analysis. Each result binds the new
region/build and `0.6.4/valhalla-3.9.1`; no online routing fallback was available.
Distances and filtered totals equal the six-profile table below. Each case used
normal request-file import followed by the application's Generate button; neither
candidate geometry nor elevation results were injected.

A fresh long gravel loop contains **152.163 km / 2,048 samples**, with actual
74.33464 m spacing, complete EGM96 coverage, min/max 103.16/196.64 m.
Its raw D+/D− is **1,879.93/1,879.93 m**; unchanged `distance-box-v1` filtering
(radius 50 m, maximum gap 100 m) gives **1,402.06847/1,402.06847 m**.
It is a newly routed geometry, not the historical 151.917 km comparison line.
A normal 9.279 km Hike tour gives raw 248.68/248.68 m and filtered
182.53325/182.53325 m.

Across **26 actual captured profiles / 4,741 height samples**, all Python analysis
fields/fingerprints agree within `1e-7` numerical tolerance. Native-versus-decoded
HGT maximum error is 0.010000 m (native decimal precision); maximum original-COG
plus independently interpolated NGA-grid error is **0.491676 m**. The long route's
maximum is 0.474511 m. These check the same DEM and documented transformation,
not independent ground truth or a new hiking-quality endorsement.

Actual Android WebView touch/keyboard inspection moves the map marker to the
matching cumulative-distance coordinate. End inspection reaches the actual final
route coordinate. No additional `route_elevation` request occurs during graph
interaction. Before/after actual worker GPX exports are byte-identical and have
one track/one segment, no route, elevation or extensions. Normal Cancel during a
real native request leaves the route available with explicit cancelled status;
normal Retry restores only the current candidate/source. Raw screenshots and
route/GPX captures remain private.

### Sustained workload and the new physical blocker

**At 09:41:20 Europe/Paris the host kernel recorded `usb 3-13: USB disconnect`.**
`adb devices -l` subsequently has no device and `lsusb` has no Fairphone. No
USB/network/trust setting was changed to work around it. A reconnect/unlock was
requested; dependent phone work stopped and all raw/partial state was preserved.
This is a missing physical device, not evidence of a native crash or a product
regression. It prevents claiming complete Fairphone acceptance.

Before disconnection the checkpoint records **99 paced candidate selections,
eight normal regenerations and two Home/foreground cycles over 439.461 s**.
Every checked selected result kept its exact candidate/source binding, one SVG,
one chart control, one map archive and a cleared inspection marker after Escape.
The intended 144-selection/12-regeneration/three-cycle run did not finish. The
finished 99-selection checkpoint is explicitly partial; no clean-idle, explicit
actor-close or final UID-network measurement is inferred from it.

PSS is `dumpsys meminfo --package` for the actual staging package and **all
associated WebView processes from the same observation**, matching PR93's
definition. It does not exclusively attribute shared Android system services.
Collection is about 1.5 s plus command time; subsecond peaks can be missed.
First-use startup already opens an empty map. Native replies and chart observation
provide separate timings, not an invented isolated height/chart PSS peak.

| Physical phase | Median aggregate PSS, bytes | Observed peak, bytes | Main + associated WebView at that same peak |
| --- | ---: | ---: | --- |
| First startup/empty map/idle | 327,265,792 | 349,797,376 | 189,506,560 + 160,290,816 |
| Install/verification/readiness window | 599,928,832 | **1,096,246,272** | 199,291,904 + 896,954,368 |
| Restarted V2 region + map | 683,239,424 | 694,212,608 | 282,174,464 + 412,038,144 |
| Six-profile Generate/height/chart workload | 720,296,960 | 788,017,152 | 271,389,696 + 516,627,456 |
| Long route/chart/interaction window | 791,434,240 | 856,914,944 | 395,165,696 + 461,749,248 |
| Interrupted sustained workload | See 30 s windows below | 828,903,424 | 383,217,664 + 445,685,760 |

Sustained first/last 30 s median aggregate PSS: **769,648,640 / 796,721,152 bytes**.
Two short background-window medians: 765,076,480 / 735,950,848 bytes. There was no
observed monotonic unbounded rise, but the incomplete run and absent cleanup/idle
cannot establish long-term stability or exclude retention. The installer peak is
larger than PR93's 989,039,616-byte route/region-return peak and must remain
visible. These are different workloads/artifacts/renderer states, not evidence
of a regression or a saving. No arbitrary memory ceiling or leak claim is made.
Observed staging private-storage peak during installation was **224,171,008
allocated bytes** (`du` across files/WebView/cache/no_backup, excludes APKs);
later route captures/cache reached 224,302,080. This is a sampled allocation peak,
not a sum of logical component sizes or proof that no short staging overlap exists.

Native reply timings captured before interruption include 37 actual route calls:
18–769 ms, median 35 ms (warm actor, different path/search lengths). Across the 26
captured profiles, native height is 4–177 ms, analysis 3–55 ms. The 2,048-sample
route specifically measures **149 ms native height / 55 ms analysis / 223 ms total**.
Nineteen passive reply-to-SVG MutationObserver intervals are 2.7–12.9 ms. These
include reply handling/validation/render scheduling and are **chart-ready upper
bounds**, not isolated construction CPU time. Test probes forward unmodified
messages and retain bounded metadata only; memory includes the test harness.

WebView network loads were blocked for the actual post-install route/UI run
without changing phone connectivity. Real offline routes/heights/charts passed.
The independent install traffic is recorded above. The planner's strict final
UID TX/RX assertion was not retrieved before disconnection, so **zero-byte offline
UID activity is not claimed**. The server trace and a blocked WebView alone do
not prove zero native/network activity in every process.

### Unfinished gates and preservation limits

The physical all-four-tile/integer-boundary/missing-coordinate probe, synthetic
partial/void JNI fixtures, explicit native close/reopen/mapping-zero checks,
post-clear 75 s idle, final native Save-document chooser path and isolated
wrong-hash/wrong-build/corrupt-HGT/quota/interrupted-transfer/retry tests remain
**unrun** in this new-source acceptance attempt. Controlled faults were prepared
only in fresh private host directories and were never used to damage the
successful Android installation. Existing automated fixtures cover these contracts,
but are not labelled physical results. Normal UI download cancellation/resume and
actual elevation cancellation/retry **did** pass, as detailed above.

The fresh pre-update preservation audit matches all nine installed APK files,
package paths/versions/install timestamps, 220 old Debug and 271 previous V2
research private files byte-for-byte. All 11 files in each retained host Mapzen
Yvelines/Marly region independently match their original identities. Only the
staging app/test update and their new owned state were written. **A final
post-workload device preservation comparison is blocked**, so the earlier audit
is not presented as a final after-test result. Production private data was never
read. Published V1 data/catalog, signing, Play and social were not modified.

No new production defect was confirmed by the completed physical cases. Added
instrumentation asserts regional mapping ownership/zero after explicit closure,
records a 15 s closed idle, keeps the explicit installer test awake and separates
installation traffic. These assertions compiled and passed host checks, but their
new-source physical execution remains a gate. Raw personal routes, all DEM/input
bytes, keys, APKs, screenshots and logs remain outside Git.

Private evidence integrity pins (not a claim that raw artifacts are committed):

| Evidence | SHA-256 |
| --- | --- |
| recovered-apk-audit.json | `1df3fa40032c6b37270ba51b25fe55200218f4de1481573e0772ceef301daac0` |
| host-https-final.json | `63a5bf836067b82c2597f708a60284c22dadb27c28f675fd4ab99a155cc2adf0` |
| installed-native-verified.json | `cacb7e085166eb76637bf507cb80471269934e77985475c193da6ce1e3f72b21` |
| installed-opfs-verified.json | `1035736a00af3394c5a799a42f636c6cdb9e55749a9033f2e72d39e208a24dc6` |
| profiles-summary.json | `39263743aa92c085a1504f37ddbd24c1d763ef81bf2f07d01d05d5dfc67acf67` |
| phone-comparison.json | `a990341bb719337d9f9cf1f6e5160e24ec1d5407e310bdd31c42f7207338cbd2` |
| long-interaction.json | `6931eb13bbf8e1bb2fc68b649fdb0a4a1aec6c5ee0cc55e59a7daa961ff09e48` |
| cancel-retry.json | `93f38272ca9b23e4b81619859aa79b6b0642d06ac8a3a1fc6454c0e3bfc1756c` |
| endurance-progress.json | `ff60f658c8b464b569013e31b5b13afcb5cc3f1ac03defc4a26e4b96ad9f53e5` |
| memory-summary-partial.json | `bb71d3c3230d49960669e2de67c971358335c01a26fb5e361119f59664fdcc3d` |
| device-before.json | `cb9cf621d5a6846065210ef9aa674915734018c33d72220437fe3a0a91306929` |
| preservation-after.json | `3c8dec531a57bdaad698d730e9c11234d967d6472584d6dcefd6ef670d1e05e4` |
| old-host-regions-verified.json | `1d4d4baf212d5fe44a0a09fc807996f7ba4d92832bfbb722f5a2425cea4e02bf` |


## Implementation and confirmed integration changes

- Bounded, pinned, redirect-free source downloader and complete product/URL/hash
  verification. Eleven explicit files, at most 90 MB each; no implicit downloads.
- Deterministic COG node-grid to signed big-endian 3,601² Skadi conversion with
  mandatory EGM2008/EGM96 grids, north-to-south rows and no-data `−32768`.
  COGs removed east/south shared nodes: nine source COGs are necessary to produce
  four complete HGT tiles, including the external south/east halo. No clamping,
  extrapolation, zero filling or fabricated terrain. Missing sources fail.
- Fresh graph rebuild against the same derived HGT, with a graph/DEM/PBF/tool
  identity receipt. Reuse of unaffected verified map/Places/Nature bytes is
  explicit; the old elevation-enriched graph is never reused.
- Private documented and independently authorized V2 modes. Datum/status pairs
  are exactly historical `unresolved/unresolved` or documented `documented/EGM96`.
  Python, JavaScript and Android retain strict field, identity and size checks.
- **Confirmed metadata defect fixed:** route elevation replies previously always
  said “unresolved vertical datum.” The native actor now retains the reference
  from its verified, leased component before JNI creation; browser parsing accepts
  only the two known references. Analysis/scoring/geometry/GPX algorithms do not change.
- Exact-build approval request/copy/export/preflight. Neither a boolean edit nor an
  approval file merely found beside data authorizes publication. The operator must
  separately provide a trusted approval-record digest. The record binds canonical
  evidence, the proposed public build, reviewed terms acceptance and derived graph.
  This is an explicit operational trust boundary, not a claim of cryptographic
  signature or legal approval by the software. Synthetic test approvals are never
  actual operator records. Approved retained builds require separate future
  per-build authorization; this implementation rejects them rather than applying
  one approval to several versions.
- Static distribution notices keep DEM-enriched graph rights separate from ODbL
  database obligations; retained private versions do not inherit a newer DEM's
  licence or approval. Required Copernicus notices remain in the prepared artifact.
- Dedicated `.v2staging` Debug package, explicit external CA/catalog inputs and a
  localhost-only trust rule. Default Debug/Release need neither input and receive
  neither the CA nor staging catalog. No device/system certificate settings change.
  Gradle fingerprints certificate/catalog **bytes**, so same-path replacements
  cannot reuse stale generated resources. A real same-path catalog-change task
  experiment re-executed and copied the changed bytes; canonical inputs were restored.
- Normal Regions UI exposes exact-source terrain attribution. The active public
  catalog, versionCode/versionName, signing, production and historical regions are
  unchanged. No data or APK is committed.

## Measured source, transformation and build

The source ledger records product/release, original HTTPS locator, byte size,
SHA-256, acquisition time and observed Last-Modified/ETag/object version.
**489,501,031 bytes** were acquired: nine 2021-release COGs and two NGA grids.
Hashes pin observed HTTPS-authenticated bytes, not provider-signed checksums.
The implemented downloader was also run again against all eleven official
endpoints: **11.56 s**, peak RSS **48,104 KiB**, all pinned hashes reproduced.
The mutable mirror's 2021 release identity is documented; the original COG object
Last-Modified dates are May 2022, not fabricated terrain acquisition dates.

The initial artifact experiments used Python 3.13.5, NumPy 2.4.4, Rasterio 1.4.3 /
GDAL 3.9.3 and pyproj 3.7.2 / PROJ 9.5.1; gzip metadata is fixed to empty
filename/mtime zero. The optional build group retains main's unchanged NumPy
2.5.1 instead of downgrading the normal Python environment. Each conversion
record identifies its actual toolchain.
Full transformation records retain source hashes, pipeline, software versions,
void/range counters and all derived hashes outside Git.

| Measurement | Actual result |
| --- | --- |
| First four-tile conversion | 420.52 s, peak RSS 525,560 KiB |
| Repeat with explicit 32 MiB GDAL cache | 465.89 s, peak RSS 162,576 KiB |
| Full CLI, including generated source pins (NumPy 2.4.4) | 405.08 s, peak RSS 211,344 KiB; same HGT/record hashes |
| Locked NumPy 2.5.1 replay | 426.15 s, peak RSS 179,468 KiB; every compressed HGT byte identical |
| Reproducibility | Same-toolchain records identical; 2.5.1 record differs only in declared NumPy version |
| Independent boundary/source checks | 14,404 shared-seam samples identical; 100 original-COG/manual-geoid checks pass |
| Largest checked integer quantization error | 0.494683 m; theoretical bound 0.5 m, not terrain accuracy |
| Full regional rebuild/verification | 542.26 s, maximum process RSS 2,677,700 KiB, including OSM extraction |
| Valhalla builder container peak | 907,808,768 bytes; configured 3,072 MiB / 2 CPU build resource bound |
| Graph | 22 genuine 3.9.1 GPH tiles, embedded elevation flag independently verified |
| Regional components | 218,670,766 bytes; 218,674,036 including regional manifest |

The **16 October** private documented build was
`9799c1034b2e581ee1cf9cba522c4cf873c863280f8608506c15af0b4ba46efe`.
Graph SHA-256:
`7d85ebdeefbbabc1716a4ffd8a50b7e9bea0083741b26b4d4aee596474e8fd09`.
Its size is unchanged at 99,481,600 bytes, but its bytes differ from the old graph.
The selected PBF is unchanged, SHA-256
`2ac2b0d9c7ca8374af078a6f564c342a08a2634a110c1f18bae1cbd1cda5d849`.

| Component | Bytes |
| --- | ---: |
| Map | 81,570,965 |
| Routing including manifest | 99,481,878 |
| Places | 261,132 |
| Nature | 10,634,994 |
| Elevation including manifest | 26,721,797 |

All four decoded tiles have **zero void/invalid cells**. Their available integer
ranges are respectively 10–307, −1–209, −3–272 and 6–261 m. Real zero/negative
heights remain distinct from the missing-data sentinel.

Independent GNU `sha256sum` and full regional-format verification also passed for
the original inputs, final HGT, new region and both historical regions.

The previous private Yvelines build `850e2b…e23d3c6` (216,176,479 bytes) and Marly
`36e42e…e51d8e` are preserved. The new region adds approximately 2.50 MB / 1.16%,
without changing install/storage budgets. Conversion requires bounded raster/cache
memory and reserves enough free disk for the worst permitted four HGT outputs.
Keep roughly 0.49 GB source bytes, 0.027 GB converted terrain and 0.219 GB region;
site plus uncompressed publication ZIP duplicate the latter. OSM extraction and
optional independent IGN reference add temporary disk; no existing caches were
cleared to make room.

| HGT | Bytes | SHA-256 |
| --- | ---: | --- |
| N48E001 | 5,731,294 | `fac3ef52cbea26ca5736a597923562f79e36c0ef041e4ddde0f5e3d4f655de95` |
| N48E002 | 6,762,026 | `eea1345034e3110af7d2a0b9a706358be987182b3fb4b9e180a97e21e0f7ca7e` |
| N49E001 | 7,510,161 | `1b2b3dfd1a59691f81cf3f7a33043be9dc8c4f147d7f1a13ce9ec37141a18111` |
| N49E002 | 6,716,261 | `3c18a4d200ea418549ca097893338d52d47efd8eddb4b00edb2cf1cb7f457454` |

## Independent terrain comparison

Existing private **routed geometries** are reused unchanged for source comparison.
The PR89 policy remains `distance-box-v1`, radius 50 m, maximum gap 100 m. No
parameters were selected to reproduce a desired historical D+. Sampling is 50 m,
except the 151.917 km route's actual 2,048-sample budget (74.21446 m). All sources
had complete coverage on these five cases; unavailable samples remain null.

IGN reference: official D078 RGE ALTI 5 m edition `2020-07-30`, delivery
`2021-10-00009`, archive 90,690,133 bytes, provider MD5 checked and SHA-256
`cdd5637135c86a0779e4eed7b0398b6de1ec25e78e000b94fddc2ee00915ca38`.
Its Lambert-93 point grids were sampled locally; no private route was sent to an
online elevation service. IGN heights remain labelled **IGN69 normal heights**.
Cross-datum absolute altitude differences are not asserted. Raster comparisons
are not surveyed vertical validation; a datum gradient can also affect differences.
The flat/steep cases are exact contiguous routed subsections selected by independent
IGN elevation range, with original route distance normalized to their edge spans.

Values are metres, `raw D+/D− → filtered D+/D−`, rounded here only for presentation.

| Routed case | Historical Mapzen/Skadi | Copernicus EGM96 | IGN ground model, IGN69 |
| --- | --- | --- | --- |
| Marly woodland open, 2.655 km | 24.3 / 78.8 → 19.6 / 74.1 | 27.9 / 79.7 → 21.2 / 73.0 | 21.9 / 74.3 → 19.9 / 72.3 |
| Marly woodland loop, 6.451 km | 150.6 / 150.6 → 135.8 / 135.8 | 156.1 / 156.1 → 140.6 / 140.6 | 148.5 / 148.5 → 136.8 / 136.8 |
| Yvelines valley/hills loop, 151.917 km | 1,639.6 / 1,639.6 → 1,280.5 / 1,280.5 | 1,859.8 / 1,859.8 → 1,393.0 / 1,393.0 | 1,116.5 / 1,116.5 → 995.1 / 995.1 |
| Flat subsection, 3.414 km | 21.4 / 35.2 → 12.2 / 26.0 | 26.5 / 34.7 → 14.1 / 22.3 | 7.6 / 21.7 → 6.3 / 20.4 |
| Steeper subsection, 3.185 km | 95.8 / 23.0 → 86.4 / 13.6 | 126.7 / 52.9 → 103.7 / 30.0 | 90.5 / 14.6 → 87.1 / 11.2 |

| Copernicus filtered D+ | 25 m samples | 50 m | 100 m |
| --- | ---: | ---: | ---: |
| Woodland open | 21.74 | 21.22 | 21.00 |
| Woodland loop | 143.57 | 140.63 | 138.66 |
| Flat subsection | 14.82 | 14.12 | 12.63 |
| Steeper subsection | 107.58 | 103.74 | 94.94 |

The long loop gives 1,393.05 m at 74.21446 m and 1,311.35 m at 100 m. Denser
sampling would exceed the native budget; it is not silently used in production.
These differences show the combined effects of sampling, filtering and source
surface. The long-route Copernicus/IGN difference is about 40%; it must remain
visible in the source decision. Neither a 1 m grid nor a smooth chart proves metre
accuracy. Canopy, buildings, mixed source ages/infill, horizontal placement,
interpolation, geoid models and integer quantization remain uncertainty sources.
No independently surveyed route/control-point validation was provided or verified.

## Native host validation of the actual rebuilt graph

The pinned Valhalla **3.9.1 native Python actor**, with networking disabled and
read-only new regional files, routed all six numeric profile policies for both
open and loop requests. This checks the native core/graph; it is not an Android
WebView or Valhalla-Mobile packaging test. Sampled points came from the returned
native polylines and native total distances, with continuous leg boundaries.

| Profile | Open distance / D+ / D− | Loop distance / D+ / D− |
| --- | --- | --- |
| Trail run | 2.656 km / 21.19 m / 72.94 m | 6.564 km / 141.01 m / 141.01 m |
| Hike | 2.655 km / 21.22 m / 72.97 m | 6.432 km / 140.92 m / 140.92 m |
| City bike | 3.472 km / 28.78 m / 80.53 m | 7.399 km / 146.43 m / 146.43 m |
| Gravel bike | 3.472 km / 28.78 m / 80.53 m | 7.399 km / 146.43 m / 146.43 m |
| Mountain bike | 3.472 km / 28.78 m / 80.53 m | 7.399 km / 146.43 m / 146.43 m |
| Road bike | 3.472 km / 28.78 m / 80.53 m | 7.399 km / 146.43 m / 146.43 m |

A native map-matching diagnostic inspected **154 graph edges** with genuine
nonzero mean elevations and grades, independently of the tile header flag. Exact
edge-walk matching rejected the rounded polyline; the explicit map-match is an
attribute diagnostic, not an exact-route oracle or a route-generation fallback.
Native spatial probes also passed all four tiles, integer seams and neighboring
positions, with two missing outer-tile positions returning null.

Profile policies can legitimately return the same geometry. The above routes use
the new graph; they differ from the fixed historical geometries in the source
comparison. No route was chosen to preserve a historical ascent screenshot.
Native height sampling also passed the five comparison routes, including a real
2,048-sample route. Maximum decoded-HGT error was 0.010000 m (the native reply's
2-decimal precision); maximum original-COG/manual-geoid error was 0.487220 m,
within the quantization/interpolation bound. These are pipeline checks against
the **same DEM**, not independent terrain-accuracy evidence.

Host route latency: 16.97–33.63 ms warm, 208.33 ms for the first route. Five-route
native height calls took 1.13–200.06 ms; the long 2,048-sample call took 193.89 ms.
Host actor peak RSS was 145,152 KiB; regional file mappings went from five to zero
after actor destruction. Host RSS cannot be compared to phone aggregate PSS or
used to claim a phone memory improvement. Actual 18 October phone main/WebView measurements are reported separately above;
these host figures are not substituted for them.

## Private distribution and phone boundary

A real server binds **only 127.0.0.1:9443**. A dedicated USB reverse tunnel is the
planned phone path; no public host, account, Pages or DNS changes. Local CA and
server keys remain outside Git. The isolated Debug variant trusts that CA only
for `localhost`; other HTTPS uses system roots. Certificate/hostname verification
is enabled. An initially incomplete local test CA was rejected by strict TLS;
the fixture was corrected with CA key usage/constraints and passed strict OpenSSL
validation. No permissive verifier or device-wide trust workaround was used.

Actual HTTPX transport fetched all 11 component files and verified exact sizes,
SHA-256, no redirects/cookies/Content-Encoding, exact bundled-origin CORS and a real
127-byte PMTiles range. Total: **218,670,766 bytes**. This demonstrates host private
HTTPS, not public hosting acceptance or Android installation. The staging catalog
uses outer schema 1 with an exact **V2 regional manifest**, immutable build URL,
bounds and component byte total; its local manifest/component preflight passes.

The 16 October staging package is `io.github.victorgabillon.sugarglider.v2staging`, version code 8,
name `1.2.0-v2-staging`. It was verified against the installed research certificate
`e84155df3a2c7ea48723876b1fe8e0e602cb600f8374d6539b9fea9aa42cfbd7` before installation.
Only this previously absent package and its test APK were installed. Exact app ID,
permissions, certificate, bundled staging catalog/CA and absence of real regional
files were checked. Production, old Debug and `.v2debug` were not installed over,
cleared or uninstalled. Their APK/metadata and readable regional-file baselines
were captured before installation. Those 16 October raw baselines are now missing
with the temporary directory; the fresh 18 October preservation inventory is
recorded above, without claiming a comparison against unavailable files.

The 16 October phone installation was interrupted by disconnection. The actual
18 October reconstruction, replacement identity, in-place staging update, normal
HTTPS installation and new-source physical acceptance are reported above. Neither
historical Mapzen phone evidence nor synthetic fixtures substitute for those tests.

## Regression status and reproduction

The 18 October rerun after the instrumentation changes passes **1,405 / 16
deselected**, Ruff and strict mypy (186.56 s). Browser reruns pass all 48 harnesses /
918 scenarios, focused 22-case V2/release checks, controlled retention and real
four-viewport chart/map input. Android reruns pass **239 Debug + 234 Release**
tests, both lint/build variants and isolated staging/test/lint; all three APKs
pass ZIP/ELF 16 KiB alignment. All 134 shared assets are pinned; only staging
receives the explicit new CA/catalog, and its permission list is byte-identical
to the previously installed staging APK. Final committed-head reruns and CI are
linked from the PR94 delivery update.


Historical 16 October `uv run --offline make check`: Ruff, strict mypy, **1,405 passed / 16
external-service tests deselected**, 179.01 s under main's retained NumPy version.
All **25 focused tests** pass, including deterministic synthetic HGT,
signed/no-data/orientation checks, known terms and exact approval, source
corruption, graph/DEM binding, per-file provenance, APK catalog binding and mocked
HTTPS failures. Unit tests use no network, real DEM, Docker or external services.
The real TLS/source/build/native experiments are recorded separately above.

Browser: **48 harnesses pass**, including source-matched attribution, both V2 wire
modes and explicit EGM96 replies. Existing cancellation/identity/storage/GPX suites
remain. Normal Android Debug/Release tests, lint and assembly passed; isolated
staging APK/test assembly and lint passed. Final normal
reruns pass **239 Debug + 234 Release tests**, both lint variants
and assembly (110 s), including the new datum tests. All **134** declared shared
assets match their sources; the staging variant has only its explicit catalog
override. Normal Release contains no private CA, terrain, research classes or
custom trust rule. All three APKs pass ZIP/ELF **16 KiB** alignment; the native
SO hash remains `09b6d312b19caa5410561b804213641f5f8a772d1b3db570cc17bac8a55fb878`.
Static 16 KiB packaging checks are separate from a physical 16 KiB-device claim.
The implementation head `05ea8cdc27e46fea0a8fcb3624620c23571e1551` passed all seven
push/PR CI runs. The delivered PR head is checked again after this report update.

Install optional build dependencies with `uv sync --frozen --group dem`. The normal
application runtime does not import or require the converter's Rasterio/PROJ tools.
Keep data outside Git and use fresh output directories:

```sh
uv run --group dem python -m sugarglider.offline_regions.terrain_pipeline acquire \
  --pins offline-regions/sources/copernicus-2021-yvelines.json --output /private/originals
uv run --group dem python -m sugarglider.offline_regions.terrain_pipeline convert \
  --pins offline-regions/sources/copernicus-2021-yvelines.json \
  --source /private/originals --output /private/skadi
uv run python -m sugarglider.offline_regions.terrain_pipeline rebuild \
  --previous-region /private/pr90-yvelines --pbf /private/ile-de-france-latest.osm.pbf \
  --elevation-pins /private/skadi/elevation-inputs.json --output /private/new-region
uv run --group dem python -m sugarglider.offline_regions.publication_cli request \
  --private-region /private/new-region --output /private/documented-region \
  --source-pins offline-regions/sources/copernicus-2021-yvelines.json \
  --originals /private/originals --transformation /private/skadi/transformation.json \
  --graph-build-record /private/new-region-graph-build.json \
  --evidence /private/unsigned-publication-request.json
```

The last command cannot create an operator approval or set publication true. Only
`approved-copy`, supplied a separately authorized record and trusted digest, can
create a new approved copy; it rechecks originals, transformation, graph and all
identities. This command was exercised only with synthetic test approvals, never
with actual research data. Do not infer authorization from this documentation.

Prepare the private catalog using `prepare_distribution` with the documented
region, `base_url="https://localhost:9443/"`, an explicit description and the
unsigned evidence path. This creates a fresh site/archive without deployment.
Create local certificates with `scripts/create_private_v2_test_ca.sh` into a fresh
external directory; serve with `scripts/serve_private_v2_https.py --root …
--certificate … --key …`. Both certificate and catalog Gradle properties are
required only for `assembleV2Staging`:

```sh
cd android
./gradlew -PsugargliderV2Staging \
  -PsugargliderV2StagingCA=/private/tls/ca.pem \
  -PsugargliderV2StagingCatalog=/private/site/catalog.json \
  assembleV2Staging assembleV2StagingAndroidTest
```

The explicit release gate is `python -m sugarglider.offline_regions.release_catalog
--apk ACTUAL_RELEASE_APK --catalog CATALOG --site SITE --base-url HTTPS_BASE
--evidence EVIDENCE --approval OPERATOR_RECORD --trusted-approval-sha256 TRUSTED_DIGEST`.
It checks the **actual APK catalog bytes** and the exact V2 region, then requires
publication authorization. `--private` validates staging only and never approves
release. Ordinary main CI performs tests/builds, not this authorized publication.

## Coordinated launch gates

1. Resolve/accept the documented source-quality and combined-database terms; obtain
   affirmative exact-build operator approval through an independently trusted record.
2. Prepare and verify the approved immutable copy, complete notices and byte-stable
   HTTPS artifacts. Keep the existing public V1 artifacts for the code-8 app.
3. Stage a V2 offering and rebuild the normal app with that coordinated catalog;
   pass the assembled-APK preflight. The outer catalog schema may remain 1.
4. Retain the measured phone acceptance and explicitly decide the replacement
   graph/reproducibility issue. Retain the PR93 startup-network attribution and
   broader device/16 KiB-runtime release limitations until separately verified.
5. Obtain separate deployment and Android release authorization. This PR authorizes
   neither public data publication, Google Play upload, signing/version changes,
   merge nor social activation.
