# PR90: complete V2 offline regions

This change replaces the regional distribution contract with schema 2 and exactly
five mandatory components: `map`, `routing`, `pois`, `nature`, `elevation`.
It builds genuine Valhalla 3.9.1 graphs, enriches their edges from local HGT data,
and connects the installed graph and its own elevation directory to one leased
native actor. PR89's elevation-analysis algorithm is unchanged. Normal planner
results, candidate ranking, GPX and the elevation UI are outside this change.

## Wire contract and identity

The regional manifest includes `schema_version: 2`, `publication_allowed: false`,
region ID/name/bounds, OSM source identity, pinned toolchain, all five component
IDs and ordered file descriptors, and the SHA-256 `build_id`. Serialized fields
must be explicit, including nullable `source_url`. Additional fields, missing
components, duplicate IDs, unsafe paths, wrong formats, unsupported toolchain,
invalid sizes and a mismatched content identity are rejected. Independent map,
POI and nature payload schemas stay unchanged. The routing component manifest
remains schema 2, now requiring engine 3.9.1 and both foot and bicycle access.
There is no V1 parser or automatic migration. Encountering V1 regional metadata
returns `regional_v2_install_required`; old files and the old pointer are retained
until an explicit new V2 installation succeeds. Explicit removal remains a user
action.

Canonical bytes are UTF-8, sorted object keys, no insignificant spaces, unescaped
Unicode and one trailing LF. Bounds and header bounds use Python JSON double
representations, including `.0` for integral coordinates and a two-digit negative
exponent where needed. Signed coordinate zero is normalized to positive zero
before identity hashing, including across worker/message/storage round trips.
`build_id` is SHA-256 of that object without `build_id` and without informational
`source.source_url`. File byte hashes remain hashes of the original bytes.
Synthetic shared Python/browser vectors cover Unicode, signed zero, small
exponents and southern/western tile ordering.

| Component | Ordered paths | Format |
| --- | --- | --- |
| map | `map/manifest.json`, `map/basemap.pmtiles` | `map-manifest-v1`, `pmtiles-v3-mvt` |
| routing | `routing/manifest.json`, `routing/valhalla_tiles.tar` | `routing-manifest-v2`, `valhalla-3.9.1-elevation-tar` |
| pois | `pois/index.json.gz` | `poi-index-v2-gzip-json` |
| nature | `nature/index.json.gz` | `nature-index-v1-gzip-json` |
| elevation | `elevation/manifest.json`, sorted `elevation/skadi/N48/N48E002.hgt.gz` etc. | `elevation-manifest-v1`, `skadi-hgt-gzip-v1` |

Elevation paths are derived from the inclusive floor of all four bounds; an exact
north/east integer boundary therefore requires the neighboring tile. The region
is limited to 16 one-degree tiles, and east=180 is rejected rather than inventing
antimeridian wrapping. Descriptor limits are 16 KiB for map/routing manifests,
2 GiB per map/routing archive, 32 MiB per compressed index, 64 KiB for the elevation
manifest, and 26,982,978 bytes per compressed HGT. The regional manifest is limited
to 32 KiB. Native graph verification reads bounded headers/index entries and
requires complete 272-byte 3.9.1 tile headers, matching header/index tile IDs
and the elevation flag, with at most 100,000
tiles. Flags alone do not prove meaningful embedded values; the real-data
inspection below also checks edge attributes.

## Elevation payload and installation

The elevation manifest contains component ID, exact region bounds, format,
`publication_allowed: false`, `provenance_status: unresolved`, `vertical_datum:
unresolved`, and ordered source rows. Each row records its relative Skadi path,
compressed size/SHA-256, URL, acquisition timestamp, decoded size, valid/void/invalid
pixel counts and available altitude range. An HGT tile has 3,601 × 3,601 signed
big-endian int16 samples, exactly 25,934,402 decoded bytes. The existing PR84 probe
checks gzip/CRC, length, hash, filename identity, values and coverage. The Android
installer independently repeats streamed hash, bounded decompression and coverage
checks using a 64 KiB buffer. It never expands a regional DEM into the Java heap.
Repeated build-time verification retains at most 16 coverage metadata rows;
every reuse still hashes the complete current compressed file. No raster is
cached, and an independent verification process starts empty.
Void values remain unavailable; invalid samples, wholly unavailable tiles and
mismatched metadata prevent activation. Filename and source hash establish the
acquired tile's identity; they do not independently certify source geography,
vertical datum or ground-truth altitude accuracy.

The existing installer owns one transaction: capture manifest → stage map → native
graph and DEM → worker POI/nature installation → verify all five → atomically
commit the regional pointer. No optional elevation installer exists. Native files
are staged together in a fresh immutable directory, with storage allowance for
all native bytes and completion metadata. Partial failure or cancellation cleans
only the newly owned native staging directory. An existing completed build is
verified and reused, never overwritten. Browser staging remains resumable, and a
failed update cannot replace the active pointer. Network reads are bounded, reject
redirects/encodings, carry no cookies or participant authority, and enforce
cancellation/deadlines. Restart does not turn partial data into Ready.

Native layout in the application-private files directory:

```text
regional-routing-packs/<region_id>/<build_id>/<routing_component_id>/
  manifest.json
  valhalla_tiles.tar
  complete.json
  elevation/manifest.json
  elevation/skadi/N48/N48E001.hgt.gz
  elevation/skadi/N48/N48E002.hgt.gz
  elevation/skadi/N49/N49E001.hgt.gz
  elevation/skadi/N49/N49E002.hgt.gz
```

`AdditionalData.elevation` points at that exact `elevation/skadi` directory.
The immutable native reference includes region/build/routing/elevation identities
and every native file hash. Actor keys include that directory and DEM manifest
hash. A persistent actor retains a repository lease until JNI closure; explicit
removal is blocked while a reader or actor owns files. Initialization failures
release leases. Switching actors closes JNI, deletes only its owned temporary
configuration, and releases the old lease. Verified-pack caching lasts only while
leases exist. The application owns one engine, which serializes route/height/
close operations. Active routes retain their request lease even when their
WebView goes away.

Configuration explicitly blanks graph tile URL, DEM URL/credentials and DEM
remote directory. No server engine, DEM interpolation fallback, or arbitrary
remote graph fetching is added. PR88's typed bounded request and nullable response
handling are promoted to a shared internal helper. Height remains internal;
there is no elevation bridge operation or normal planner elevation publication.

Upstream 3.9.1 Skadi maps compressed bytes and decompresses each used gzip tile
into a native allocation (~24.73 MiB), outside the Kotlin heap. Its unpacked-tile
cache threshold is hard-coded to 50, not a configurable 1-tile streaming cache;
in-use entries can remain pinned. The V2 16-tile component budget bounds the
available tile working set to ~395.73 MiB per sampler; Yvelines has four tiles,
~98.93 MiB decoded. Routing and height workers may own distinct samplers inside
one actor, so this is not a bound on total application PSS. Actor replacement
and measured device PSS matter; short tests do not establish long-term leak
freedom.

## Reproduction and private source evidence

Use Python 3.13, `uv`, Docker and the existing bounded OSM input. Raw inputs,
acquisition records, regional artifacts, personal route geometry and device
reports stay outside Git. Each build requires explicit DEM source pins; there is
no automatic terrain acquisition in the application or regional builder.

```sh
SUGARGLIDER_BUILD_MEMORY_MB=3072 SUGARGLIDER_BUILD_CPUS=2 \
uv run --offline python -m sugarglider.offline_regions build \
  --region yvelines-ouest-parisien --pbf /absolute/input.osm.pbf \
  --elevation-sources /absolute/private/dem-acquisition.json
uv run --offline python -m sugarglider.offline_regions verify \
  --region yvelines-ouest-parisien
```

The source-pins file has `publication_allowed: false` and `tiles`; each tile row
contains `tile` (e.g. N48E002), absolute `path`, `source_url`, ISO acquisition
`acquired_at`, exact `byte_size`, SHA-256, nullable HTTP `last_modified`, and a
human-readable `origin`. A single pin file may include other tiles for another
smaller region, but duplicate identities and a missing required pin are errors.

The builder is pinned to Linux/amd64
`ghcr.io/valhalla/valhalla:3.9.1@sha256:18cb42988e03c70dc4bc4ca095a259ec4db5e5df928be65956fc1c64c280b47a`.
It verifies the executable version, builds from the freshly bounded PBF, and
sets the local DEM path before `valhalla_build_tiles`. That build runs its elevation
stage exactly once, then produces and normalizes the indexed archive. Docker
graph building uses `--network none`. The standalone `valhalla_add_elevation`
requires explicit tile arguments in 3.9.1. A controlled tiny-graph comparison
found that reapplying it to an already enriched, finalized graph returned success
but made routing fail with invalid graph-ID levels. The same graph built with
only the integrated elevation stage routed successfully. Production therefore
uses the integrated stage once and does not reapply the standalone utility.
The first Yvelines attempt failed closed on the missing CLI tile list and left no
published directory. The correction above was made before the rebuild reached
its graph phase.

Upstream elevation enrichment writes node elevation, edge mean elevation,
weighted grade and maximum uphill/downhill slope, and encoded edge elevation for
eligible non-shortcut/non-bridge/non-tunnel/non-ferry shapes. These mapped DEM
attributes are distinct from route-height samples and PR89 D+/D− analysis. The
archive's elevation flag by itself cannot establish valid source coverage.

The four private acquisitions on 2026-10-15 came from
`https://s3.amazonaws.com/elevation-tiles-prod/skadi/<N48-or-N49>/<tile>.hgt.gz`.
N48E002 reuses the exact PR88-validated bytes. Every tile had 12,967,201 valid,
zero void and zero invalid pixels; all gzip and decoded-length checks passed.

| Tile | Compressed bytes | SHA-256 | Min/max available m |
| --- | ---: | --- | ---: |
| N48E001 | 5,357,770 | `5c34fa008d27f3fbb7767c5183b161684da75d4f567c170db8839865ad426389` | −7 / 299 |
| N48E002 | 5,885,987 | `f5f6c6744cd3bb7fc46d59bb49400574e9c22e8916c3b59c5dc35ffc454cbd2d` | −36 / 201 |
| N49E001 | 6,802,511 | `9ac959dac7ae6018a8f3c305bcc2790fa3f1c66d94f906a7b0bdfd36b5bd746f` | −25 / 257 |
| N49E002 | 6,176,144 | `f6829b5748f600f01484ca115f353f58d78c8fa5a093cd2d5a11428bd4304b40` | −20 / 246 |

Total compressed terrain is 24,222,412 bytes; decoded raster data is 103,737,608
bytes. Pixel availability is not accuracy validation. Original provenance,
vertical datum, attribution and redistribution obligations remain unresolved.
The dataset stays unpublished, the public catalog is unchanged, and the static
publication CLI rejects these manifests by default. Its explicit `--private`
option permits local extraction/verification only and grants no redistribution
permission.

## Device evidence and automated verification

The isolated build type `v2Debug` uses
`io.github.victorgabillon.sugarglider.v2debug`, version code 8, and the existing
Debug certificate SHA-256
`e84155df3a2c7ea48723876b1fe8e0e602cb600f8374d6539b9fea9aa42cfbd7`.
It has the same permissions as Debug after application-ID normalization. The
manifest differences are the separate package/version/provider/permission
identities; no location sharing is enabled. Both APK zip entries and native ELF
LOAD segments pass 16 KiB alignment checks. No production or existing Debug APK
is overwritten, uninstalled or cleared.

```sh
cd android
JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 \
ANDROID_HOME=/home/pompote/Android/Sdk \
./gradlew --offline --no-daemon -PsugargliderV2Research=true \
  assembleV2Debug assembleV2DebugAndroidTest
```

The acceptance runner requires the exact isolated package, an explicit private
cache directory and reference metadata for an already-installed region. It does
not install regional files. `routes` exercises six profiles × open/loop,
`height` samples actual routed geometry and repeated deterministic calls,
`switch` exercises A→B→B→A immutable references, and `void` uses explicitly
synthetic disposable missing/void JNI fixtures. These synthetic fixtures are not
claimed as validation of void pixels in the real four-tile dataset, which has
none. The runner records PSS, cold/warm times, closure/reopening, pinned identity,
and application-UID network byte deltas. Production package/split hashes and
existing Debug regional-file hashes are recorded before and after testing.

PR91 should keep height-analysis failure nonfatal to routing, retain exact
selected route geometry/source/build identity, and publish PR89 coverage and
algorithm parameters with results. PR92 should expose unavailable/partial data
and the DEM/filtering uncertainty rather than treating missing values as zero.


Upstream implementation references: [Skadi gzip/cache behavior](https://github.com/valhalla/valhalla/blob/3.9.1/src/skadi/sample.cc),
[elevation graph enrichment](https://github.com/valhalla/valhalla/blob/3.9.1/src/mjolnir/elevationbuilder.cc),
and [standalone elevation CLI](https://github.com/valhalla/valhalla/blob/3.9.1/src/mjolnir/valhalla_add_elevation.cc).


Completed checks on the implementation: `uv run --offline make check` passed
Ruff, strict mypy and 1,376 tests (16 service integration tests deselected).
Required Android checks passed 233 Debug and 228 Release tests plus both lint
variants. Fifteen relevant browser harnesses passed 298 scenarios, including
V2 transactions, old-metadata retention, corruption, identity vectors and PWA
behavior. The isolated instrumentation variant also compiled and passed lint.

An independent trace on the real new Yvelines graph, run with `--network none`
and **without mounting any DEM**, traversed 107 edges. Forty-eight had nonzero
weighted grade; mean elevations ranged from 36 to 108 m, weighted grades from
−8.333% to +8.333%, and maximum uphill/downhill grades reached +15% / −16%.
These are embedded graph attributes, independently distinct from runtime HGT
sampling. They establish enrichment and offline readability, not ground-truth
vertical accuracy.

## Completed Yvelines artifact (2026-10-15)

The full Yvelines build completed successfully, then a **fresh Python process**
independently verified every component, file hash, native tile header, decoded
HGT and index. That second verification took 32.62 s (maximum host RSS
1,058,028 KiB). No smaller substitute region was used.

Build ID: `850e2b0576b49966579e1eb01dadb70fe10a9f94546352b0ece69aa92e23d3c6`.

Regional manifest: 3,270 bytes, SHA-256
`c76ec406297727a8d20791e756ddf360b34901e74dc5c21e3cebb82a44ec1553`.

OSM input: `ile-de-france-latest.osm.pbf`, 335,288,680 bytes, SHA-256
`2ac2b0d9c7ca8374af078a6f564c342a08a2634a110c1f18bae1cbd1cda5d849`; header bounds
`[1.445097, 48.11918, 3.560409, 49.24271]`. No source URL is asserted for this existing local input.

| Component | Immutable component ID | Payload bytes |
| --- | --- | ---: |
| map | `yvelines-ouest-parisien-map-v1` | 81,570,965 |
| routing | `yvelines-ouest-parisien-routing-v2` | 99,481,878 |
| pois | `yvelines-ouest-parisien-pois-v1` | 261,132 |
| nature | `yvelines-ouest-parisien-nature-v1` | 10,634,994 |
| elevation | `yvelines-ouest-parisien-elevation-v2` | 24,224,240 |

Component payload: **216,173,209 bytes**; including the root manifest,
**216,176,479 bytes** (216.176 MB, decimal).

| Non-DEM file (DEM hashes are above) | Bytes | SHA-256 |
| --- | ---: | --- |
| `map/manifest.json` | 631 | `ee0f29b2f831afdc60db4a45e50abbf412e6b4e803e4a9347d70821dbd4e63b3` |
| `map/basemap.pmtiles` | 81,570,334 | `a5e2af1ac3785d370c84a5fc0c46e65ba764a2331d4d86b7e2c6b25de52bce3d` |
| `nature/index.json.gz` | 10,634,994 | `abb0819a4f4b02d8ee844aa19de71c1760e0b63a1a9f7bd3410513d82dca7b90` |
| `pois/index.json.gz` | 261,132 | `1ace12b6869ae74f97a673ac9fe6f706cb17a6b7f29b35a9b0dbafd095ea4649` |
| `routing/manifest.json` | 278 | `3d87397c8f997cdb1a4622cd3e3ad52eb3481ff777723da7031ca14e2f71927a` |
| `routing/valhalla_tiles.tar` | 99,481,600 | `bc0dfe06b9402c1d9ae999a5bab4765d214786505154ba64f1f221854f89931e` |

Elevation manifest: 1,828 bytes, SHA-256
`953c51ef75e0217d2476afbb5e7fb1d6b2dd2046e501897aa389304006e71694`.
The graph archive has 22 genuine elevation-enriched tiles. Places has 4,415
features; Nature has 62,191. Their existing component IDs/formats are retained.

Successful complete rebuild: **58m 04.09s**, including map support-data acquisition
and verification. Map generation took about 14m 38s; Valhalla's graph stage took
112s, Places 1,594.326s and Nature 445.465s. The command's maximum host/child RSS
was 2,877,176 KiB (2.744 GiB); independently monitored Docker cgroup peaks were
3,221,229,568 bytes for map generation and 895,504,384 bytes for graph generation.
Those measurements cover different processes/accounting domains and are not
added into an invented simultaneous peak. Containers used two CPUs and a 3 GiB
memory limit; no swap/OOM occurred. This is one measured build, not a throughput
benchmark. Immutable output refuses an in-place rebuild.

Private artifact location on the test host:
`data/offline-regions/pr90-work/source/data/offline-regions/yvelines-ouest-parisien`
relative to the original checkout. Detailed build, acquisition, source, device
and timing records live beside that isolated checkout under `pr90-work/evidence`.
Neither generated artifacts nor personal route snapshots are tracked.

## Completed Fairphone acceptance

Fairphone 6, Android 16, actual kernel page size 4 KiB. APK ZIP and native ELF
16 KiB alignment were checked independently; this phone is not a physical 16 KiB
page-size device. The research app APK is 25,826,004 bytes, SHA-256
`276e0df4e3d9e7b602c03093094379d1a3696c0f260775671a0bd8e3d5b222b9`.
The final test APK is 47,093 bytes, SHA-256
`07d740e2d15a7ee0c26966181886947af7c43ff9675e37070f5c709c8ca47c95`.
Both use the verified existing Debug certificate. Before each installation,
application ID, certificate, version, permissions and manifest were compared.
Only the separate research/test packages were installed or updated.

The complete real artifact was downloaded through the **existing normal Regions
installer**, not copied into application storage. Its source was a private
HTTP server bound only to host loopback and reached through ADB USB reverse.
A temporary CDP adapter in this isolated research WebView supplied that catalog
and represented the development source to the existing HTTP-origin policy in
the page/worker. The actual HTTPS appassets bridge origin, checksums, installer,
component readers, native downloader and atomic version commit were unchanged.
This tests the installer with a private development transport; it does not
validate public HTTPS hosting or grant terrain redistribution permission.
Only reference/height-plan metadata was subsequently uploaded for instrumentation.

The UI stayed unavailable during transfer/verification and then displayed
**Ready: Map ✓ · Routing ✓ · Places ✓ · Nature ✓ · Elevation ✓** for the exact
build above. Installed native files were independently rehashed on-device;
OPFS map/Places/Nature were rehashed through their existing bounded readers.
All identities matched. Reopening after instrumentation killed/restarted the
research process preserved the selected committed build and all five checks.
The unchanged public catalog can offer its different old download as an update;
that does not replace the selected V2 build. The private test catalog displays
this build as Ready.

Download clicked at `2026-10-15T13:00:54.077Z`; not Ready at +15.014s, and
Ready observed at +34.148s. Thus first installation completed
within **15.0–34.2s**, an observation interval rather than a fabricated exact
completion time. Two-second `du -sk` observations of the isolated app's
`files`, `app_webview` and `cache` recorded 957,440 baseline bytes,
**217,431,040 peak/final allocated bytes** during installation, and
216,473,600 additional bytes. These include metadata/cache and filesystem
block rounding; the sampled peak can miss shorter transients. Native files used
120,980 KiB, WebView storage 90,821 KiB and cache 534 KiB.

Two complete six-profile × open/loop runs passed after separate process starts
(**24 strict routes**). Requests use real common graph vertices; every returned
snap was checked within 25 m (maximum 8.188 m, endpoints below 0.074 m).
All snapped points occur on returned geometry; loops close exactly, open routes
remain open, and geometry length agrees with the authoritative native summary
within 0.16%. Distances, durations, snaps and every geometry vertex were identical
on repetition. No online engine or straight-line fallback was used.

| Profile | Open distance m / duration s | Loop distance m / duration s | Warm route ms, open / loop |
| --- | ---: | ---: | ---: |
| `trail_run` | 2659 / 1094.487 | 6449 / 2891.095 | 601 cold / 80 |
| `hike` | 2655 / 1966.950 | 6451 / 5161.004 | 52 / 48 |
| `city_bike` | 3472 / 686.293 | 7479 / 1621.495 | 31 / 53 |
| `gravel_bike` | 3472 / 625.232 | 7479 / 1468.270 | 58 / 58 |
| `mountain_bike` | 3472 / 776.182 | 7479 / 1809.294 | 43 / 68 |
| `road_bike` | 3472 / 508.330 | 7479 / 1202.973 | 21 / 54 |

On the second run, cold actor initialization was 1,077 ms; its first route took
601 ms, subsequent routes 21–80 ms. All twelve routes completed in 3.510s,
including verification, initialization, PSS readings and closure. Route-process
PSS was 44.59 MiB initially, 103.48 MiB before closure and
82.75 MiB afterwards. Removing files while the persistent actor held a
lease was rejected as busy.

The actual hike loop was **6451 m**, with 131 PR88 samples at
50 m nominal spacing and preserved routed distances. Every sample was available;
maximum absolute native/Python difference was **0.009999999988 m**,
within the unchanged **0.010001 m** serialization tolerance. Additional fixtures
covered all four installed tiles and an exact integer boundary; two outside
the tile footprint remained null. These establish interpolation/serialization
agreement, not ground-truth vertical accuracy. DEM datum/positioning/accuracy
uncertainty remains unresolved.

Cold height sampling took 168 ms; the full cold call including installed-file
verification and initialization took 2420 ms. The first warm call took 36 ms;
twenty further calls were exactly deterministic, 27–39 ms
(median 32.5 ms). A 2,048-point API-budget stress fixture took
180 ms; it repeats actual sample coordinates and is not represented as a real
route. Over-budget, empty, NaN and wrong component/build inputs failed explicitly.
Closing/reopening the actor reproduced the same heights with a new cold actor.

Height-process PSS was 44.68 MiB initially; repeated-route-sample PSS
rose from 131.22 to 134.47 MiB across twenty calls. After loading all four
tiles it reached 232.56 MiB; after JNI closure it was 98.81 MiB. Native
samplers, model/class caches and allocator retention contribute; this short test
does **not** establish long-term leak freedom or a constant total process heap.

The disposable JNI missing-directory and all-void raster tests passed: heights
remained null and malformed native JSON was rejected. These never modified the
installed DEM. Routing, height and void phases each recorded **zero transmit and
receive byte delta for the research app UID**, with graph/DEM remote URLs blank.
The device's Wi-Fi/mobile settings were not changed. No research native crash
appeared in the crash buffer. Only one complete V2 region was built/installed,
so physical multi-region switching is **not claimed**; deterministic ownership,
A/B actor replacement and cross-region identity isolation are covered by unit
tests. Existing production APK/split hashes, version/install/update timestamps,
old Debug APK and all 83 recorded Debug private-file hashes remained unchanged.
Production private regional contents are not readable through `run-as`; no claim
of direct production private-file hashing is made.

For another private run, build/verify a fresh V2 artifact as above, serve it through
a reviewed private development source, and use the normal Regions installer.
Prepare `reference.json` from its manifest using `regionalRoutingReference` (the
same wire reference used by the installer), then upload only that metadata into
`cache/<fresh-research-id>/` of the isolated app with `adb shell run-as`.
Run the checked-in instrumentation:

```sh
adb shell am instrument -w -r \
  -e research_id pr90-new-private-run -e phase routes \
  io.github.victorgabillon.sugarglider.v2debug.test/io.github.victorgabillon.sugarglider.V2RegionInstrumentation
```

Read `cache/<research-id>/routes-result.json` through `run-as`; retain this personal
route data privately. Select the actual hike-loop geometry and native summary
distance, construct PR88 `ResearchRoute`, and use its unchanged `height_plan`
with the matching verified HGT probe. Upload its `height-plan.json` to the same
private cache directory, then run phases `height` and `void` identically. Compare
`height-result.json` with PR88 `compare_heights` and independently probe the four
tile/boundary fixtures. Each phase returns raw `INSTRUMENTATION_CODE: -1` and an
explicit acceptance result on success; inspect both result JSON and status.
`void` requires a fresh fixture directory. `switch` requires a second complete,
legitimate V2 region and `reference-control.json`; it must never relabel Yvelines.

All implementation checks listed above passed. After strengthening the endpoint
fixture, `assembleV2DebugAndroidTest lintV2Debug` passed again in 46s. The final
research main APK's native/runtime bytes did not change. Full CI checks are also
required on the final PR head. Remaining release blockers are terrain provenance,
vertical datum/attribution and redistribution review; the region and APK remain
private. PR91/92 integration stays future work.
