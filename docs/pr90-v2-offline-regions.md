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
requires real 3.9.1 tile headers plus their elevation flag, with at most 100,000
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
