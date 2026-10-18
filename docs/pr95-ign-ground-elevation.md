# PR95 — private IGN ground-elevation implementation and acceptance

Evidence date: 18 October 2026. Base: `main` at
`d9ee4e884498b9f40f276ed6b6db80668d9cab05`. No terrain, route snapshot,
APK, screenshot, private CA, catalogue deployment or publication approval is
included in this change. The durable private evidence directory is
`data/offline-regions/pr95-ign/evidence` in the original checkout; source and
derived data are in its sibling `private` directory, outside this worktree.

**Acceptance boundary:** the Marly pilot is physically validated; full Yvelines
conversion, fresh graph and private catalogue pass host verification. The final
full-Yvelines phone installation/forest/long-route/native Save run remains
**pending: the connected Fairphone is locked**. An availability request is
pending. No lock bypass or physical pass is claimed. The final audited staging
APK is installed, retaining all existing regions.

## Implementation and boundaries

The existing PR94 acquisition, conversion, HGT writer, component verifier and
regional rebuild pipeline now accept strictly pinned mainland **IGN RGE ALTI
5 m terrain**. This adds a source adapter, not another regional builder. Routing
graphs are rebuilt once with the verified IGN HGT using the pinned Valhalla
3.9.1 image. Map, Places and Nature components retain their previously verified
bytes. Routing policy, generation, candidate ranking, geometry, waypoint order,
GPX serialization and the mathematical elevation implementation are unchanged.

The component records full original source identities, prepared-index identity,
transformation identity and derived tile identities. These participate in the
regional build identity even when two derivations produce identical heights.
Native verification accepts IGN69 only with the complete private derivation;
Python and native code reject mismatched product, URL, datum, archive identity,
dates, missing fields and publication flags. Existing components without an IGN
derivation retain their exact wire fields. The existing public publication gate
is unchanged and rejects IGN69. This PR grants no new publication authority.

The chart displays **ground model / NGF-IGN69 normal heights / IGN / Licence
Ouverte 2.0**. Source credit is cleared with the selected analysis and removed
with the chart. The service-worker shell version advances to v96 with updated
asset fingerprints. Release contains the normal catalogue, not the private
staging catalogue or its CA. No runtime GIS download or terrain fallback exists.

Confirmed pipeline problems fixed during actual execution:

* Relative `../private` conversion/rebuild paths failed native canonical-file
  verification. New output references are canonical; old immutable files stay
  untouched. A synthetic end-to-end rebuild regression covers this CLI case.
* An eight-dataset LRU repeatedly reopened granules along one degree-wide row.
  The bounded cache now permits 32 datasets. Every input is still hashed and
  checked; only byte-identical duplicate granules are sampled once. Different
  overlapping available values remain an error. A 432,120-point comparison
  produced identical output hashes: 178.674 s at eight handles versus 5.266 s at
  32. That isolated benchmark used the default GDAL cache; production conversion
  independently limits GDAL to 32 MiB. Its actual process measurements appear
  below; the benchmark is not a production-memory claim.

## Source evidence, coverage and vintages

[The committed source ledger](../offline-regions/sources/ign-rge-alti-5m-four-tiles.json)
contains every exact official archive URL, filename/edition, size, SHA-256,
acquisition timestamp and available HTTP identity. Seventeen archives total
**3,098,550,581 bytes**. All provider MD5s and locally computed SHA-256s were
independently verified (`ign-originals-verified.json`). No source bytes enter Git.

IGN's [official RGE ALTI record](https://www.data.gouv.fr/datasets/rge-alti-r)
describes a ground-node model, heterogeneous acquisitions, principally LiDAR
since 2010, updates stopped in 2024 and explicit ZICAD no-data. A departmental
edition date is not an acquisition date for every terrain cell. Vegetation,
building removal, water treatment, interpolation and vintage can still produce
errors; “ground model” is a product meaning, not proof of local accuracy.

The four complete Skadi footprints cover longitude 1–3° and latitude 48–50°.
Official administrative polygon intersection requires departments **02, 27, 28,
41, 45, 60, 75, 76, 77, 78, 80, 89, 91, 92, 93, 94, 95**. A bounding-box-only
query also returned Nord; polygon intersection excluded it. The actual Yvelines
rectangle intersects seven departments; Marly touches 78 and 92. One Yvelines
archive is therefore insufficient. Source discovery uses the official RGEALTI
Atom catalogue and per-delivery metadata, with bounded requests and no login.

The missing historical D078 archive was reacquired from IGN. Its **90,690,133
bytes / `cdd5637135c86a0779e4eed7b0398b6de1ec25e78e000b94fddc2ee00915ca38`**
exactly match PR94, rather than assigning the old identity to different bytes.
Its edition is 2020-07-30; delivery metadata identifies 2021-10-00009.
The 17 selected delivery editions span 2019-07-09 to 2023-01-03; the ledger
retains each one rather than presenting a homogeneous 2026 terrain survey.

### LiDAR HD

The [official MNT LiDAR HD record](https://www.data.gouv.fr/datasets/mnt-lidar-hd)
advertises 0.5 m, 1 km² GeoTIFF grids and describes a 5 m version as forthcoming.
The current WFS namespace is `IGNF_LIDAR-HD_METADONNEE:metadata`; the older
advertised `IGNF_MNT_LIDAR-HD:dalle` endpoint failed. That failure is not evidence
of absent coverage. The valid Marly query returned **220 tiles**, including
missions 21LHDJE and 22LHDKE, with 2022/2023 acquisitions. No separately released
official 5 m LiDAR product was established. Requesting a 5 m WMS raster would
not establish such a product.

Only route-crossed 0.5 m cells were acquired: nine urban-control cells and twelve
forest-control cells, with exact URLs, hashes and metadata retained privately.
These are **official WMS GeoTIFF exports**, not untouched archive deliveries or
point clouds. Their CRS WKT names EPSG:2154 but lacks a recognized datum/authority
and uses a WGS84 spheroid. The comparison explicitly uses the metadata/request's
Lambert-93 grid, after checking its projection parameters and exact node centres;
it does not silently rewrite the source header. This export metadata defect
limits its independence as a geodetic reference. RGE production input is not
affected. Coverage outside these downloaded cells stays visibly partial.

## Reprojection, datum and deterministic conversion

RGE ASCII cells are point nodes at multiples of 5 m. Their corner headers are
offset by half a pixel; treating those corners as samples would introduce a
2.5 m registration error. Preparation decodes verified 7z deliveries through a
bounded libarchive TAR stream; links, traversal, special files, excess entries,
expanded bytes and insufficient disk are rejected. One 1000² granule at a time is written to tiled GeoTIFF, preserving GDAL's
decoded float32 nodes, with original ASCII and archive hashes retained. This
compression is lossless for those binary nodes; decimal-to-float representation
is not exact real arithmetic. Independent ASCII comparisons allow 2×10⁻⁵ m. The strict preparation index is bounded to 16 MiB/40,000 grids.

For each 3601² geographic node grid:

1. Local PROJ converts longitude/latitude to EPSG:2154 with explicit axis order,
   network disabled, `only_best=True`, `allow_ballpark=False`.
2. Bilinear interpolation uses the correct four 5 m point nodes across granules.
   Every positive-weight node is mandatory. Missing nodes produce no-data, never
   zero, Copernicus infill or nodata weight renormalization at this conversion step.
3. Heights stay **EPSG:5720 / IGN69 normal metres**. There is no vertical shift.
4. Nearest integer, ties-to-even quantization adds at most 0.5 m per node. Missing
   becomes −32768; output is big-endian signed int16, exactly 25,934,402 decoded
   bytes per tile. The existing gzip writer fixes filename, timestamp and level.

IGN's [RAF20 documentation](https://geodesie.ign.fr/grilles-de-conversion)
relates RGF93v2b ellipsoidal and IGN69 normal heights. RAF20 alone does not
establish a validated IGN69→EGM96 operation with appropriate reference frames,
epochs and grids. This implementation chooses the explicitly permitted IGN69
contract instead of an arbitrary offset or an EGM96 label. The horizontal
operation reports nominal 1 m accuracy; formula agreement below is not proof of
centimetre registration on the ground.

Independent controls read original ASCII float64 values and implement Lambert-93
analytically, separately from production raster sampling. All **144 Marly
controls** are available, projection disagreement is at most **4.657×10⁻⁹ m**
and HGT node quantization at most **0.5 m**. The known Lambert origin
(3°,46.5°)→(700000,6600000) and unchanged vertical coordinate have synthetic tests.
Two pilot conversions produced identical HGT and transformation bytes:
`ced0d54161a192935194da274dee177ffffb6f4ada9ba01c845b9836e1818d77`.
Repeat conversion took **53.76 s**, maximum process RSS **184,348 KiB**.

The runtime's existing Skadi sampling semantics are preserved, including its
available-corner weighting at the edge of a void. Node-coverage counts below
must not be interpreted as guarantees for all subpixel route positions. Large
missing profile intervals still break analysis under the unchanged gap policy.

## Comparisons on identical routed geometry

Every row for a given route uses the **same geometry, authoritative routed
distance and sample positions**. Production analysis remains `distance-box-v1`,
radius **50 m**, maximum gap **100 m**. No smoothing parameter was tuned to a
preferred D+. Raw sums and filtered sums are different measurements. Min/max
below refer to available input samples; metres are rounded for presentation.

The retained 9.279 km Auto Tour is an **urban control**, not a forest experiment:
its original nature analysis reports 77.5% urban and zero woodland. An earlier
private log called it woodland; that annotation was corrected after inspecting
the evidence. The new 7.942 km loop is genuinely Valhalla-routed through Marly;
intersection with the verified local OSM woodland polygons covers **94.4%** of
its length. Its remaining edges are not guessed to be forest. Raw private
geometry and controls remain outside Git.

### 7.942 km Marly forest loop, 160 samples at nominal 50 m

| Source | Raw D+ / D− (m) | Filtered D+ / D− (m) | Min / max (m) | Coverage |
| --- | ---: | ---: | ---: | --- |
| IGN original 5m | 153.97 / 153.97 | 135.76 / 135.76 | 119.97 / 179.45 | complete |
| IGN Skadi | 153.29 / 153.29 | 135.23 / 135.23 | 120.08 / 179.41 | complete |
| Copernicus Skadi | 252.12 / 252.12 | 180.95 / 180.95 | 130.36 / 197.29 | complete |
| LiDAR 0.5m WMS export | 162.13 / 162.13 | 140.53 / 140.53 | 120.37 / 178.91 | complete |
| Mapzen unresolved | 183.15 / 183.15 | 149.21 / 149.21 | 126.16 / 189.86 | complete |

### 9.279 km urban control, 187 samples at nominal 50 m

| Source | Raw D+ / D− (m) | Filtered D+ / D− (m) | Min / max (m) | Coverage |
| --- | ---: | ---: | ---: | --- |
| Copernicus EGM96 | 248.67 / 248.67 | 182.53 / 182.53 | 21.01 / 161.80 | complete |
| IGN RGE original 5m IGN69 | 183.63 / 183.63 | 162.88 / 162.88 | 20.90 / 159.48 | complete |
| IGN RGE Skadi IGN69 | 188.15 / 188.15 | 166.10 / 166.10 | 22.22 / 159.70 | complete |
| IGN LiDAR HD official 0.5m WMS export IGN69 | 187.74 / 187.74 | 164.27 / 164.27 | 20.91 / 159.48 | complete |
| Historical Mapzen unresolved datum | 203.54 / 203.54 | 176.58 / 176.58 | 22.07 / 162.40 | complete |

### 151.917 km retained route, exactly 2,048 captured samples

| Source | Raw D+ / D− (m) | Filtered D+ / D− (m) | Min / max (m) | Coverage |
| --- | ---: | ---: | ---: | --- |
| Copernicus EGM96 | 1,859.84 / 1,859.84 | 1,393.05 / 1,393.05 | 103.16 / 196.73 | complete |
| IGN RGE original 5m IGN69 | 1,116.46 / 1,116.46 | 995.11 / 995.11 | 101.89 / 180.49 | complete |
| IGN RGE Skadi IGN69 | 1,123.04 / 1,123.04 | 991.40 / 991.40 | 102.00 / 180.00 | complete |
| Historical Mapzen unresolved datum | 1,639.64 / 1,639.64 | 1,280.48 / 1,280.48 | 104.55 / 191.27 | complete |



Absolute heights from EGM96, IGN69 and historical unresolved Mapzen must not be
subtracted as if they shared a datum. The different cumulative sums are source
sensitivity evidence, not a canopy-error measurement. RGE and LiDAR share a
producer and may share source lineage. No matching surveyed terrain transect or
reliably calibrated barometric activity was acquired. IGN levelling marks on
walls/structures are not interchangeable with the surrounding terrain cell;
they were not used as fictitious ground control.

### Resolution and sampling sensitivity

The HGT grid is one arc-second: about 20 m east–west by 31 m north–south locally,
plus integer quantization. Comparing original 5 m and downsampled HGT isolates
this practical loss; neither a finer grid nor denser route sampling alone
establishes accuracy. The runtime route sampler preserves backend distance and
its 2,048-sample budget. The 151.917 km reference therefore uses about 74.21 m
spacing; 50 m would exceed that budget and was not silently substituted or
stitched from separately filtered chunks.

Forest loop, identical geometry and fixed policy; filtered D+ in metres:

| Nominal spacing | Original IGN 5 m | IGN HGT | Copernicus HGT | LiDAR 0.5 m export |
| --- | ---: | ---: | ---: | ---: |
| 5 m | 142.38 | 142.03 | 198.45 | 145.49 |
| 10 m | 142.12 | 141.75 | 197.37 | 145.21 |
| 25 m | 140.56 | 140.13 | 191.95 | 143.77 |
| 50 m | 135.76 | 135.23 | 180.95 | 140.53 |
| 75 m | 129.70 | 130.06 | 169.41 | 132.69 |
| 100 m | 126.95 | 126.90 | 161.02 | 131.95 |

For the long route, original IGN filtered D+ is 994.11 / 980.74 / 969.87 m
at 75 / 90 / 100 m; Copernicus gives 1,380.72 / 1,344.96 / 1,311.35 m.
These are new sample schedules on the unchanged retained geometry, distinct
from the exact captured 2,048-point schedule above.

At 5 m route sampling, the largest 100 m endpoint rise in the original forest
profile is 25.52 m; the same endpoints give IGN HGT 24.80 m and LiDAR 24.19 m.
After the fixed smoothing: 23.52 / 22.97 / 22.73 m. The largest 50 m rise is
14.49 m original versus 13.37 m HGT; the 200 m rise is 39.15 versus 38.48 m.
Selection uses the original IGN maximum, not independent maxima per source.
Original-versus-HGT point differences on this dense loop reach 2.089 m.
These checks show preservation of this particular meaningful climb, while
quantifying the loss; they do not validate every short steep feature.


Changing sampling density changes raw and filtered ascent even with fixed
smoothing. Fine sampling can expose local shape and noise that sparse samples
miss. Short steep terrain, steps, gullies, source registration and source vintage
remain limitations. A higher-resolution native format needs a separate design
and evidence of useful route-level improvements; this PR does not redesign the
runtime or claim that 5 m source detail survives the entire current stack.

## Private regions and Fairphone acceptance

Marly's new five-component build is
**`0d0563364bd255956c39edd97d27c2cf3cba225ec0775bdebbdde11f4a4cdc2d`**,
**25,722,739 bytes** total. Its freshly enriched routing archive is
`01a8eab994555d6366fa77918e305bd06a20f69c955c0f657bfd9291674ddcf4`,
different from the retained Marly graph. All five component byte identities pass
independent regional verification. Rebuild took **233.29 s**, host maximum RSS
**2,554,268 KiB**, container measured peak **269,172,736 bytes**. Graph processing
was about 12 s; source PBF extraction dominated host work.

Fairphone 6, Android 16, 4 KiB physical page size. Only the isolated
`io.github.victorgabillon.sugarglider.v2staging` and matching test APK were
updated, after package, version, permissions and certificate verification.
Required debug certificate:
`e84155df3a2c7ea48723876b1fe8e0e602cb600f8374d6539b9fea9aa42cfbd7`.
The normal Regions UI installed all five Marly components from the private
localhost HTTPS fixture. No region bytes were pushed directly into native or
OPFS storage. Production, older Debug, V2 research and existing downloaded
region versions were preserved; no clear/uninstall or connectivity change.

Pilot physical results (tested APK SHA-256
`900ab3194c5d5a1694438306376b2fe396feee50d279716dec5025fa9dc26a6f`):

* All six profiles × open/loop: **12 normal Generate operations**, complete IGN
  analyses; one additional Auto Tour, chart touch/keyboard inspection, synchronized
  map marker, source credit and map attribution exercised on the actual WebView.
* Native sampling **8–107 ms**, analysis **3–8 ms**, elevation request **28–127 ms**
  in this set. These are actual captured measurements, not an installation-time
  claim. The installation driver's 75.95 s included waiting for manual selection;
  it is unsuitable as a pure transfer benchmark.
* Native/Python HGT heights agree within **0.010001 m** (Valhalla two-decimal
  serialization tolerance), mathematical analysis/fingerprint agrees within
  **1×10⁻⁷**. Original 5 m versus native HGT differs by up to **3.69735 m** at
  arbitrary route positions: resampling loss, not a failure of node quantization.
* Actual visible elevation Cancel/Retry preserved the successful route and retry
  added no routing calls. Restart required explicit selection when multiple
  regions were installed, then the region and native analysis were ready.
* UI switching retained Copernicus Yvelines→IGN Marly→Copernicus Yvelines→IGN
  Marly showed correct immutable identities and height references without stale
  cached analysis. A separate native actor test exercised both genuinely
  different graphs, verified closure/recreation, zero mappings after explicit
  close and **zero native UID transmit/receive bytes**.
* GPX worker output before/after chart inspection is byte-identical, one track,
  one segment, no route, elevation or analysis extensions. Native file-save
  acceptance is reported separately below; serialization alone does not prove
  that a file was saved through Android's picker.

### Network observation requiring follow-up

The broader blocked-WebView UI window recorded **6,333 transmitted / 8,947
received UID bytes**. The existing strict zero-network instrumentation assertion
**failed**. Startup counters for that window were zero; traffic cannot honestly
be attributed to startup from this evidence. The cause remains unattributed.
The failed log/counters are retained (`phone-planner.log`,
`phone-pilot-network.json`). Native route/height switching separately recorded
zero bytes. A native-only result does not establish zero traffic across all UI
work. No device connectivity, trust settings or counters were altered to force
a pass. Any later settled-window measurements are narrower observations.

### Aggregate memory observations

The pilot sampled all package-associated processes together at roughly 1.5–2 s
intervals for **1,275.4 s / 676 observations**. PSS is simultaneous aggregate
main+associated WebView, not the sum of separate process maxima. This is an
instrumented Debug run, not a release-performance or absolute instantaneous-peak
guarantee. No forced GC or arbitrary acceptance threshold was applied.

| Window | Median aggregate PSS | Observed aggregate peak | Main + associated at that peak |
| --- | ---: | ---: | ---: |
| Six profiles, 50.3 s | 535,203,840 B | 585,837,568 B | 274,161,664 + 311,675,904 B |
| Chart/map/GPX, 51.8 s | 507,525,120 B | 612,421,632 B | 283,943,936 + 328,477,696 B |
| Restart/switch/cancel window, 307.6 s | 465,510,400 B | **1,333,019,648 B** | 255,414,272 + 1,077,605,376 B |
| Normal-app post-test idle after restart, 262.7 s | 290,738,176 B | 308,909,056 B | last aggregate 288,618,496 B |

The large transient was predominantly WebView: its raw meminfo records 973,644
KiB in `Unknown`, not the native actor's heap. This identifies an accounting
bucket, not its allocator or cause. Subsequent lower values and a separate
restart do not prove absence of retention; this is not enough evidence to label
a leak. Native close left zero regional mappings and PSS 85,603,328 B in a
headless test, which is not directly comparable to a visible map/chart process.
The early phase labelled `idle-before-ign-install` included installation and
selection and is deliberately not presented as a clean idle baseline.

## Full Yvelines conversion and build

All 7,520,006 target-grid nodes (including shared tile edges) are available.
Across all four full degree tiles, 166,357 nodes outside the target bounds
remain void. Four shared seams / 14,404 samples are byte-identical. Of 256
independent controls, 255 are available and one remains unavailable; maximum
quantization is 0.5 m and projection formula disagreement 5.588×10⁻⁹ m.
The first conversion took 576.98 s with maximum RSS 207,664 KiB.
There are 3,518 prepared records / 3,042 distinct lattice granules; all 435
overlapping granules have identical prepared bytes (476 duplicate records).
All duplicated departmental input granules match exactly, so the merger
introduces no priority-dependent join there. That does not rule out acquisition
seams already present in IGN's heterogeneous master grid.

The repeat conversion passed in 553.26 s / maximum RSS 163,532 KiB: all four
HGT files and the transformation record are byte-identical. Transformation
SHA-256: `fcf7187c3c3916403fc5cc8e83c65fec33b5ef74d60baa75ede061deda9a71a9`.

The fresh full region is **210,223,038 bytes**, build
`a92396de46a6fed5fa1a49fc8c939c39bc6371424aa90c9b71f237878294c7fd`.
Its new routing archive SHA-256 is
`d47b022dc2036800bfa5eadc902a90d94de2cff8df32e6377ac9c0ff5fe9fb3d`.
The four-tile elevation component is 18,274,069 bytes. Rebuild: **495.65 s**,
host maximum RSS **2,666,508 KiB**, container peak **902,815,744 bytes**.
The native graph stage took 94 s and applied elevation once. Full independent
component/catalogue verification passed. Final full-region device acceptance
remains pending while the phone is locked; the earlier pilot is separately
identified above.


### Storage and final host artifacts

Original archives occupy 3,026,020 KiB on disk; the 3,518 ASCII/prepared-grid
records occupy 27,841,816 KiB (originals retained alongside random-read rasters).
The separate two-department pilot preparation occupies 1,129,536 KiB. Nothing
was deleted to recover space. Preparation of all departments took approximately
50 minutes by directory/record timestamps, not an instrumented benchmark.
Private LiDAR references occupy 140,656 + 187,540 KiB, including cells from the
retained preliminary mixed forest/urban loop. These are host storage measurements,
not compressed regional download sizes.

| Final artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| debug APK | 25,882,631 | `db66d62dda3f4a3046f13b9d7b1436e8cc1cae02638438c7f971f38c78183146` |
| release APK | 24,370,671 | `1384a42c93cb1ccf8edd78fb370e93afa01b42199ae0e59fa6707ef2ce7099bf` |
| v2Staging APK | 25,884,161 | `a4ecb351754dccb6a0053dfc35adc15e57739e28011b03bc4a48a1e2f61dcf9e` |
| v2StagingAndroidTest APK | 226,870 | `6d859a5ea4fff6d302768e61376419627ca43d4a61b24186bc4ba90b9b7faf66` |

The final staging update retained the verified pilot certificate and installed
with replacement, without uninstalling or clearing data. Its test APK is
byte-identical to the pilot instrumentation APK. The first final-artifact audit
correctly detected a stale shared asset during the licence-link correction;
all variants were rebuilt and the complete final audit then passed.
The final audited APK has not yet completed physical UI acceptance; pilot
measurements are not silently reassigned to it.

The post-update preservation audit independently confirms unchanged production
APK/certificate identities, all 220 older Debug private files, all 271 V2 research
private files and 41 previously installed staging regional/OPFS payload files.
All eight installed Marly component files independently match their expected
hashes. Production private files are inaccessible to `run-as`; their contents
were not claimed to be byte-audited. No operation targeted production data.

| Derived HGT | Compressed bytes | SHA-256 |
| --- | ---: | --- |
| N48/N48E001.hgt.gz | 3,597,713 | `a7d55ab92559ace1c64069bdf7669717e2ddd8acfbc9c8b041a770d0461688d3` |
| N48/N48E002.hgt.gz | 4,248,630 | `d47f7dc9e0947cacd975be249fb73c8c7212f98b9cdb384d9044da87f81ca5e0` |
| N49/N49E001.hgt.gz | 5,527,281 | `d79a01593f51fa01589242892505b90e3a13479405c864373462d2b094bd7611` |
| N49/N49E002.hgt.gz | 4,891,056 | `7955eec7df9675fdf2d897d6f581379c87940365353a2505c420ee6565415cb3` |

## Automated verification and packaging

* `make check`: Ruff formatting/lint, strict mypy, **1,440 passed, 16 integration
  tests deselected**, 221.63 s in the final run. Synthetic DEM fixtures use no real map/DEM,
  network, service or Docker. New tests cover source identities and timestamps,
  safe archive extraction, strict preparation metadata, duplicate/hash checks,
  bounded cache behavior, grid origin, seams/voids/conflicts, vertical identity,
  deterministic full HGT writing, full source/component/build identity and the
  unchanged publication rejection. NumPy 2.5 emits nine rasterio shape-deprecation
  warnings; no failing assertions. An earlier restricted-sandbox run stalled in
  local SQLite/async tests; the normal host-accessible full run passed and its
  stale owned process was terminated.
* Browser: **48 harnesses / 920 assertions, zero failures**, plus the four-viewport
  real mouse/touch/scroll/MapLibre lifecycle check and explicit-GC retention
  acceptance. Focused parser and chart tests include the truthful IGN reference
  and clearing prior source credit.
* Android: **240 Debug / 235 Release unit tests**, zero failures; lint and normal
  Debug/Release assembly passed after the final native metadata validation. The
  private staging and instrumentation variants also built successfully.
* All pilot APKs passed ZIP/ELF **16 KiB alignment** checks; native library bytes
  are unchanged (`09b6d312b19caa5410561b804213641f5f8a772d1b3db570cc17bac8a55fb878`).
  The phone's 4 KiB page size does not prove physical 16 KiB execution. Normal
  Release contains the expected shared assets/catalogue and neither private CA,
  test tooling nor DEM data; private staging alone contains its scoped fixture
  catalogue and CA. Permissions match the retained staging APK. Final artifact
  hashes appear above. All seven GitHub checks for implementation revision
  `82e2cc2233a3b3cc4908650b2a2ad41ea702443e` passed (Python, Android, elevation
  browser and social workflows, including push/PR runs). Subsequent report-only
  revisions do not change the tested APK/source bytes. PR: [draft #95](https://github.com/victorgabillon/sugarglider/pull/95).

## Reproduction and operational gates

Use Python 3.13 and `uv sync --frozen --group dem`. The offline build host also
needs libarchive `bsdtar`; the app and normal Android builds do not. Supply a
fresh private output directory for every command; no immutable output is reused:

```sh
uv run python -m sugarglider.offline_regions.terrain_pipeline acquire \
  --pins offline-regions/sources/ign-rge-alti-5m-four-tiles.json \
  --output "$TASK_PRIVATE/originals"
uv run python -m sugarglider.offline_regions.terrain_pipeline prepare \
  --pins offline-regions/sources/ign-rge-alti-5m-four-tiles.json \
  --source "$TASK_PRIVATE/originals" --output "$TASK_PRIVATE/prepared"
uv run python -m sugarglider.offline_regions.terrain_pipeline convert \
  --pins offline-regions/sources/ign-rge-alti-5m-four-tiles.json \
  --source "$TASK_PRIVATE/prepared" --output "$TASK_PRIVATE/skadi" \
  --bounds 1.445097 48.38 2.25 49.1
uv run python -m sugarglider.offline_regions.terrain_pipeline rebuild \
  --previous-region "$PREVIOUS_VERIFIED_REGION" --pbf "$PINNED_OSM_PBF" \
  --elevation-pins "$TASK_PRIVATE/skadi/elevation-inputs.json" \
  --output "$TASK_PRIVATE/new-region"
```

The pinned PBF is SHA-256
`2ac2b0d9c7ca8374af078a6f564c342a08a2634a110c1f18bae1cbd1cda5d849`;
the existing verified PBF/spec must match before rebuilding. The image is
`ghcr.io/valhalla/valhalla:3.9.1@sha256:18cb42988e03c70dc4bc4ca095a259ec4db5e5df928be65956fc1c64c280b47a`.
Build containers use `--network none`; downloaded originals, derived data and
all historical immutable regions remain retained privately.

IGN's published dataset identifies Licence Ouverte 2.0. Reuse requires accurate
source/update attribution and avoiding misleading presentation or endorsement;
the historical licence landing URL in the source contract currently redirects
to the general data portal. The chart instead links to the verified current
[official Licence Ouverte 2.0 text](https://www.data.gouv.fr/pages/legal/licences/etalab-2.0);
the source ledger preserves the provider's historical metadata URL. Retain the
dataset and actual terms evidence when preparing notices. This is evidence of a source licence, not operator
approval of an enriched combined OSM/DEM graph. Review the applicable licence
text, source vintages, attribution, ODbL database/source obligations, derivative
graph treatment and downstream notices before publication. No rights conclusion
is inferred from download success or the software's licence. Historical Mapzen
remains unresolved; it is never used to fill IGN gaps or authorize publication.

The public catalogue is still the existing deployment. A coordinated public V2
launch requires compatible five-component public manifests, complete immutable
artifact verification, corresponding app/runtime, legal/operator approval and
release acceptance. This private IGN69 component intentionally cannot pass the
current Copernicus-specific public approval gate. Neither the public catalogue,
Play, production signing nor installed production app was changed.

## Current assessments

1. **IGN technical suitability: GO for the private pilot and code review.**
   Explicit ground-model/IGN69 contracts, real rebuilt graph and physical
   native/profile comparison are established.
2. **Elevation accuracy: comparative evidence only.** Ground semantics and
   cross-source shape agreement are useful; no surveyed accuracy claim.
3. **Full Yvelines: conversion coverage GO within the specified bounds.**
   The full graph, repeat conversion and independent five-component/catalogue
   verification pass. Full-region phone acceptance remains pending; this is
   not a blanket end-to-end acceptance of the new Yvelines bundle.
4. **Distribution/legal readiness: NO-GO.** No operator approval or IGN public
   publication evidence is supplied; the existing strict gate remains closed.
5. **Public release: NO-GO.** Private data/catalogue, outstanding acceptance
   and unattributed UI traffic remain explicit gates. No merge or release.

