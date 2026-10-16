# PR94: V2 elevation distribution staging

Base: main `cac2b415e7eb6db7a9129e6ff50068b3414c29eb`.
Source/host review: 16 October 2026. This is a private release-staging change,
not publication approval. See the [rights dossier](pr94-terrain-rights.md).

## Acceptance assessment

- **Terrain format/native-engine suitability: GO for the tested Copernicus DSM
  pipeline on the host.** Do not describe this surface model as surveyed or
  bare-earth hiking terrain; the independent source differences below remain.
- **Terrain redistribution: evidence prepared; NO-GO for actual publication.**
  The reviewed licence and notices are documented, but affirmative exact-build
  operator acceptance/approval is absent. Every actual regional manifest retains
  `publication_allowed=false`.
- **V2 distribution engineering: NO-GO for complete acceptance; host staging passes.**
  Real TLS byte/range/CORS checks pass. The phone became disconnected after the
  new isolated APK was installed, before installing its new region. Native HTTPS
  installation, failure/restart tests and new-source physical UI remain gates.
- **Public Android release: NO-GO.** Approval, coordinated public V2 catalog,
  physical new-source acceptance and the outstanding PR93 release gates remain.
  Normal Release still bundles the unchanged public V1 catalog; the explicit
  assembled-APK preflight rejects that mismatch. No V1 reader is added.

The build, source and host checks below are actual experiments. Phone results
from PR93 used historical Mapzen data and **are not PR94 acceptance**. The new
staging APK is installed with the verified research certificate; ADB subsequently
reported `device '014728cc' not found`. Reconnect/unlock was requested. No new
source installation, phone routing, chart or GPX result is claimed yet.

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

The new private documented build is
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
used to claim a phone memory improvement. Phone main/WebView measurements remain
blocked by the missing device.

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

The new package is `io.github.victorgabillon.sugarglider.v2staging`, version code 8,
name `1.2.0-v2-staging`. It was verified against the installed research certificate
`e84155df3a2c7ea48723876b1fe8e0e602cb600f8374d6539b9fea9aa42cfbd7` before installation.
Only this previously absent package and its test APK were installed. Exact app ID,
permissions, certificate, bundled staging catalog/CA and absence of real regional
files were checked. Production, old Debug and `.v2debug` were not installed over,
cleared or uninstalled. Their APK/metadata and readable regional-file baselines
were captured before installation. A post-test comparison awaits reconnection.

**Pending physical acceptance:** normal five-component HTTPS installation and full
verification; interrupted/cancelled/corrupt/wrong-hash/wrong-build/storage-failure
recovery; restart/selection readiness; all six profiles, open and loop routes;
new-source native samples versus HGT/original COG; D+/D−/interactive chart; GPX
byte invariance; main plus WebView PSS/latency; actor closure/mapping ownership.
Existing synthetic installer/security regressions do not substitute for these.

## Regression status and reproduction

Final `uv run --offline make check`: Ruff, strict mypy, **1,405 passed / 16
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
4. Complete the pending new-source phone installation/failure/route/chart/GPX and
   aggregate-memory checks. Retain the PR93 startup-network attribution and broader
   device/16 KiB-runtime release limitations until separately verified.
5. Obtain separate deployment and Android release authorization. This PR authorizes
   neither public data publication, Google Play upload, signing/version changes,
   merge nor social activation.
