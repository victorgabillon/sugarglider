# Offline native Valhalla height research — 2026-10-14

A **separate draft experiment based on PR86 `d3f712a`**, with real Fairphone 6
height measurements from the previously generated Sugarglider route. This is
research tooling, not a regional elevation installer, final UI, D+/D− feature,
or elevation-aware routing. PR86's routing/lifecycle acceptance remains separate.

## Acquired and independently validated source

| Fact | Value |
| --- | --- |
| Source | [Mapzen Terrain Tiles / Skadi N48E002](https://s3.amazonaws.com/elevation-tiles-prod/skadi/N48/N48E002.hgt.gz) |
| Acquisition date | 2026-10-14 |
| HTTP Last-Modified | 2016-04-28 20:42:06 UTC |
| S3 version ID | `null`; the URL is not an immutable source version |
| Compressed bytes | 5,885,987 (5.61 MiB) |
| SHA-256 | `f5f6c6744cd3bb7fc46d59bb49400574e9c22e8916c3b59c5dc35ffc454cbd2d` |
| Decoded bytes | 25,934,402 (24.73 MiB) |
| Grid | 3601 × 3601, signed big-endian int16 |
| Valid / void / invalid pixels | 12,967,201 / 0 / 0 |
| Whole-tile valid min / max | −36 / 201 m |

The exact bytes passed both PR84's HGT probe and PR85 candidate build/verify.
The staged `marly` candidate retains **`publication_allowed: false`**. Its region
bounds describe the PR85 staging exercise, not permission to install elevation
for the full Yvelines region. The native experiment reads the verified full
one-degree HGT tile directly; the entire test route is inside that tile.

All DEMs, pin/candidate manifests, acquisition headers, full route snapshots,
plan/results, CSV/plots, APKs and device evidence were kept **outside Git**.
The experiment's source geometry came from the actual Fairphone Generate result:
25,353 m, 1,051 native-routed vertices, `trail_run`, unchanged exact waypoints.

## Native contract and independent comparison

The published `valhalla-mobile:0.6.4` wrapper exposes
`Valhalla.height(HeightRequest): HeightResponse`. The prototype uses an explicit
coordinate `shape`, `range: false`, an owned request ID, and
**`height_precision: 2`**. It verifies the response ID, shape/count, absence of
unexpected range/encoded data, and finite valid heights before returning them.

Two contract details were established during the physical experiment:

1. [Core 3.9.1's parser](https://github.com/valhalla/valhalla/blob/3.9.1/src/worker.cc)
   accepts only height precision **0, 1 or 2**. Our initial value 3 was ignored,
   yielding integer metres. The final request/test uses 2.
2. At positive precision, the [native serializer](https://github.com/valhalla/valhalla/blob/3.9.1/src/tyr/height_serializer.cc)
   uses `SetMaxDecimalPlaces`, which [truncates decimal output](https://github.com/Tencent/rapidjson/blob/master/include/rapidjson/internal/dtoa.h).
   Two decimals therefore permit an absolute serialization discrepancy below
   **0.01 m**, rather than a nearest-rounding half-centimetre bound. The comparator
   permits 0.010001 m, including a one-micrometre numerical allowance. A synthetic
   regression reproduces an error greater than the incorrect half-centimetre bound.

The generated model declares `height` elements as `Double`, although native
missing cells are JSON `null`. The adapter widens to `List<Double?>` **before
unboxing**. Real missing-neighbor, empty-directory and all-void responses decoded
successfully and remained unavailable. Actual sea-level zero remains distinct
in unit tests; no unavailable value is converted to zero.

The height actor uses a fresh owned configuration path, never the application's
`valhalla.json`. `AdditionalData(elevation = localDirectory)` selects only the
explicit local directory. Both `mjolnir.tile_url` and native 3.9.1's
`additional_data.elevation_url` are empty; URL credentials and download-directory
settings are also empty. The latter native settings are absent from config models
0.6.0 and are explicitly added to the research JSON. The height actor has no
routing archive and is closed before the next test actor is opened.

## Actual Fairphone results

| Check | Observation |
| --- | --- |
| Route sampling | 509 points; 50 m intervals and an explicit final endpoint |
| Available / unavailable | 509 / 0 |
| Native profile min / max | 61.16 / 169.98 m |
| Maximum native/Python absolute difference | 0.0099999999993 m |
| Native actor initialization | 1,122 ms |
| Cold / warm complete height request | 236 / 69 ms |
| Total native calls / allowance | 7 / 8 |
| Total native call elapsed | 374 ms |
| Missing west/north/east neighbor tiles | `null`, including exact north/east boundaries |
| Empty local DEM directory | all three fixture values `null` |
| Separate synthetic all-void HGT | all three fixture values `null` |
| Malformed native JSON | `ValhallaError(code=100, Failed to parse json request)` |
| Empty / oversized / nonfinite local shapes | rejected before JNI |
| UID transmitted / received bytes during suite | 0 / 0 |

A preceding successful run measured initialization 1,109 ms and cold/warm
231/130 ms. Cold and warm heights were identical within each run, and all 509
values matched across the repeated physical runs. These are observations from
one device and one real tile, not a general performance benchmark.

Known repository fixtures were compared separately:

| Location | Python bilinear HGT | Native height |
| --- | ---: | ---: |
| Marly fixture start | 106.5200 m | 106.52 m |
| Saint-Germain fixture end | 92.8384 m | 92.83 m |
| Marly intermediate fixture | 95.0000 m | 95.00 m |

These are plausible local values. The [official Marly terrain report](https://www.yvelines.gouv.fr/content/download/14426/91757/file/Note%20de%20pr%C3%A9sentation_Marly-Le-Roi_OCTOBRE2017_Consultation_mise_en_ligne.pdf)
places the commune's low area around 48 m NGF and Fort du Trou d'Enfer around
178 m NGF. This broad plausibility check does **not** establish a surveyed error,
vertical datum equivalence, bare-earth accuracy or current terrain conditions.

## Bounds, memory and isolation

`native_height_experiment.py` reuses the shared geodesic edge-distance function
and normalizes routed-edge lengths to the supplied authoritative backend total.
It samples only adjacent native geometry edges; the source route is immutable.
Six-decimal coordinate quantization applies only to the independent height shape.
Each point retains its source edge/fraction and normalized distance. Source and
plan SHA-256 identities bind the native output to the exact compared inputs.

Limits are explicit: 20,000 input vertices, 200 km route distance, 2,048 height
samples, 1–1,000 m spacing, bounded input bytes, and eight native calls in the
physical suite. Oversized sampling requests fail rather than silently coarsening
spacing or returning a partial profile. Native `skadi.max_shape` is also 2,048.
Duration gates are 5 s per native call and 20 s total; they check after JNI
returns. The host ADB operation has a 120 s timeout. Safe native cancellation
before a JNI return remains future work.

The one real tile needs 5.61 MiB compressed storage and a 24.73 MiB decoded grid.
The final instrumented process PSS was approximately 45.3 MiB before native
initialization, 98.1 MiB after it, 131.0 MiB at the real-data peak, 88.8 MiB after
closing the real actor, and 90.0 MiB after the suite. These are **whole-process**
measurements, including the native library and JVM; neither an incremental tile
cache budget nor long-duration leak acceptance is inferred from them.

The adapter is in `src/debug`; Release contains no height research classes.
The custom instrumentation runner is compiled into the test APK, never exposed
through an Activity, WebView bridge, public capability or startup hook. Runtime
routing still uses `AdditionalData(elevation = "")`. The production APKs and both
installed routing archive hashes were checked before/after and were unchanged.
Only matching-certificate, exact-ID Debug/test APKs were installed. Main Debug
manifest bytes were identical, with no added permissions. Only fresh owned
research cache/staging directories were removed afterward.

## Reproduce with explicitly supplied research files

Use Python 3.13, JDK 21 and the existing local Android SDK/signing certificate.
The tools do not download tiles. Keep inputs/outputs outside Git.

```sh
uv run python -m sugarglider.offline_regions.elevation_hgt_probe \
  --tile /research/source/skadi/N48/N48E002.hgt.gz \
  --sha256 f5f6c6744cd3bb7fc46d59bb49400574e9c22e8916c3b59c5dc35ffc454cbd2d

# route.json has routing_profile, distance_m and the already returned
# candidate.route.geometry; no generation or routing occurs in this command.
uv run python -m sugarglider.offline_regions.native_height_experiment prepare \
  --route /research/route.json --spacing-m 50 --maximum-samples 2048 \
  --tile /research/source/skadi/N48/N48E002.hgt.gz \
  --sha256 f5f6c6744cd3bb7fc46d59bb49400574e9c22e8916c3b59c5dc35ffc454cbd2d \
  > /research/plan.json

(cd android && JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 \
  ANDROID_HOME=/home/pompote/Android/Sdk ./gradlew --offline --no-daemon \
  testDebugUnitTest lintDebug assembleDebug assembleDebugAndroidTest \
  testReleaseUnitTest lintRelease)

ANDROID_HOME=/home/pompote/Android/Sdk uv run python \
  scripts/run_native_height_research.py \
  --plan /research/plan.json --tile /research/source/skadi/N48/N48E002.hgt.gz \
  --output /research/fresh-fairphone-run

uv run python -m sugarglider.offline_regions.native_height_experiment compare \
  --plan /research/plan.json \
  --native-result /research/fresh-fairphone-run/native-result.json \
  --tile /research/source/skadi/N48/N48E002.hgt.gz \
  --sha256 f5f6c6744cd3bb7fc46d59bb49400574e9c22e8916c3b59c5dc35ffc454cbd2d \
  > /research/elevation-profile.json
```

The runner independently verifies the installed Debug certificate, both APK IDs,
version code, instrumentation target and byte-identical main manifest before
installation. It revalidates the host HGT, checks the transported SHA on-device,
records native timing/PSS/traffic, and verifies production/routing preservation.
It retains evidence on failure and cleans only its owned directories on success.

## Checks completed

- `make check`: Ruff, strict mypy; **1,267 Python tests passed**, 16 integration
  tests deselected. Unit tests use synthetic inputs and require no DEM/service.
- Strict mypy including the research runner: 268 source files, no issues.
- Android: **225 Debug / 220 Release unit tests**, both lints, Debug app/test APK
  assembly; corrected precision Debug tests/lint/assembly repeated successfully.
- Six browser routing/planning/candidate/GPX/integrity harnesses: **139 scenarios**.
- Debug APK 16 KiB page alignment passed; the Valhalla ELF was unchanged.
- Actual native integration: the cases above executed on the Fairphone, not mocks.

## Provenance, attribution and redistribution review

The [AWS registry](https://registry.opendata.aws/terrain-tiles/) identifies the
Mapzen-managed public bucket and points its license field at
[Joerd attribution](https://github.com/tilezen/joerd/blob/master/docs/attribution.md).
That document requires investigation of each applicable provider's terms.
[Joerd sources](https://github.com/tilezen/joerd/blob/master/docs/data-sources.md)
include EU-DEM, SRTM, GMTED and ETOPO. The fetched 8.4 MiB source-footprint inventory
(SHA `1882c61652283929aad1564734d1eb01575116f5936e9836ccd140c6d852d8b1`)
contains spatially intersecting entries for those datasets. Footprint overlap
identifies **possible contributors**, not the exact composition of this 2016 HGT.
Its S3 response supplies no contributing-imagery header or immutable version ID.

Applicable European attribution includes “Produced using Copernicus data and
information funded by the European Union - EU-DEM layers.” USGS and NOAA source
credits may also apply. The [Copernicus policy](https://land.copernicus.eu/en/data-policy)
permits redistribution subject to source attribution, modification disclosure
and no implied endorsement; this does not by itself clear every underlying
contributor, vintage, mixed product or transformation in this tile.

Exact contributor/version provenance, the resulting vertical datum, terrain
quality and all redistribution obligations remain unresolved. No terrain or
route-coordinate artifact is distributed in the PR; research manifests/profiles
remain unpublished. A versioned optional regional elevation component and its
installer need a separate design/rights review. D+/D− smoothing, public region
publication, final UI and elevation-aware ranking remain subsequent work.
