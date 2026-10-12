# PR83 — Offline elevation feasibility and architecture

**Status: feasibility decision + deterministic coverage probe, not an elevation feature.**
No Android capability, route calculation, GPX contract, public region, release,
signing configuration, or existing on-disk schema is changed by this PR. In
particular, elevation gain/loss and profiles are **not yet available**.

## Existing boundaries verified against code 8

1. `scripts/build_pr33_valhalla_pack.sh` pins
   `ghcr.io/valhalla/valhalla:3.6.3` and explicitly configures
   `--additional-data-elevation ""`. Its artifact is a normalized
   `valhalla_tiles.tar` plus routing manifest v2.
2. `NativeRouteEngineFactory.kt` pins Android
   `valhalla-mobile 0.5.1 / Valhalla 3.6.3`, configures
   `AdditionalData(elevation = "")`, and requests a 2-D polyline6 route.
   `NativeRouteResult.Success` carries 2-D coordinates, distance and time,
   **not** heights. Current route candidates must not invent them.
3. Upstream `Rallista/valhalla-mobile` **tag 0.5.1** only exposes
   `ValhallaActor.route`. Later **tag 0.6.4** exposes
   `Valhalla.height(HeightRequest)` and `heightRaw`, but also changes the
   native actor lifetime and API dependencies; compatibility with this app has
   not been physically or CI validated. The tag retains Valhalla 3.6.3.
4. `offline_regions/models.py` and `validation.py` enforce a **four**
   component, manifest-schema-1 layout (map, routing, Places, Nature).
   `region_product.js` and `region_versions.js` atomically publish
   one complete, verified immutable regional build. Existing public build IDs
   and their files are not mutable.
5. All route-point acquisition methods reduce to name and lat/lon. Height
   should describe the **actual selected routed geometry**, never alter
   coordinates or become a hidden requirement for routing. Runtime routing
   stays local; no network elevation service fallback is permissible.

These constraints make "just enable height" insufficient. The Valhalla graph
tar and a sampled DEM are separate data products. Neither the existing code-8
bundle nor the current Yvelines region is proven to contain sampled elevations.

## Data candidates, evidence, and rights gate

| Candidate | Advantages | Caveats and unresolved work |
| --- | --- | --- |
| **Tilezen/Mapzen Skadi** (`*.hgt.gz`) | Valhalla 3.6.3's Skadi reader and upstream `valhalla_build_elevation` already expect its one-degree tile layout; global data are served through AWS Open Data. Simplest first prototype. | Mixed upstream DEM sources and resolutions; gaps/voids; compressed size and quality unmeasured; attribution and rights of underlying contributors must be reviewed before any redistribution. |
| **Copernicus GLO-30** | Potentially useful 30 m-class source, particularly in Europe. | Copernicus describes a **digital surface model** (including vegetation/buildings), not automatically a trail-ground profile. Its GLO-30 *view service* became access-restricted in July/August 2026; entitlement, download mechanism, derivative rights and required attribution need a separate review. Not a drop-in Skadi HGT. |
| **National elevation data (e.g. French IGN)** | May yield better local terrain representation. | Coverage, resolution, transformations, datum, legal terms, volume and a compatible regional conversion pipeline are not established. |

**First experiment candidate:** Skadi tiles, not a commitment to ship them.
Neither access to a public URL nor an open-source converter constitutes a
redistribution license. Record original dataset/URL, source version or download
date, source SHA-256, exact transformation, coverage/no-data statistics,
attribution, and the final published bytes' SHA-256. Fail closed when a
required source tile, license approval or integrity check is missing.

Sources consulted:

- [Valhalla 3.6.3 Skadi sampling implementation](https://github.com/valhalla/valhalla/blob/3.6.3/src/skadi/sample.cc):
  3601 x 3601 big-endian signed-int16 HGT, one-degree tiles, no-data handling,
  gzip/LZ4/raw support.
- [Valhalla 3.6.3 build elevation script](https://github.com/valhalla/valhalla/blob/3.6.3/scripts/valhalla_build_elevation):
  Tilezen Skadi source convention and bbox/graph coverage options.
- [Valhalla height API](https://github.com/valhalla/valhalla/blob/3.6.3/docs/docs/api/elevation.md):
  resampled shape, heights, distance and explicit `null` for unavailable data.
- [valhalla-mobile 0.5.1 actor](https://github.com/Rallista/valhalla-mobile/blob/0.5.1/src/wrapper/valhalla_actor.cpp) and
  [0.6.4 Android API](https://github.com/Rallista/valhalla-mobile/blob/0.6.4/android/valhalla/src/main/java/com/valhalla/valhalla/Valhalla.kt).
- [AWS Terrain Tiles](https://registry.opendata.aws/terrain-tiles/),
  [Tilezen/Joerd attribution](https://github.com/tilezen/joerd/blob/master/docs/attribution.md)
  and [source provenance](https://github.com/tilezen/joerd/blob/master/docs/data-sources.md).
- [Copernicus DEM description and obligations](https://dataspace.copernicus.eu/explore-data/data-collections/copernicus-contributing-missions/collections-description/COP-DEM)
  and [August 2026 GLO-30 view service notice](https://dataspace.copernicus.eu/news/2026-8-25-copernicus-dem-30m-view-service-update).

## Reproducible read-only tile coverage probe

The repository now contains
`sugarglider.offline_regions.elevation_feasibility`. It reads an **existing**
strict region spec, lists nominal 1 x 1 degree Skadi tiles, and estimates raw
decoded HGT bytes. It does **not** access the network, fetch tiles, modify a
manifest, touch the user's generated data, or install an Android region.

```sh
uv run python -m sugarglider.offline_regions.elevation_feasibility \
    --region yvelines-ouest-parisien
uv run pytest -q tests/unit/test_pr83_elevation_feasibility.py
```

The Yvelines/west-Paris rectangle `[1.445097, 48.38, 2.25, 49.1]`
nominally requires **four** Skadi 1-degree tiles:

```text
skadi/N48/N48E001.hgt.gz
skadi/N48/N48E002.hgt.gz
skadi/N49/N49E001.hgt.gz
skadi/N49/N49E002.hgt.gz
```

A 3601 x 3601 signed-int16 tile is 25,934,402 **decoded** bytes;
four total **103,737,608 bytes (~98.93 MiB) uncompressed**. These are
arithmetic estimates, **not downloads, measured compression, measured peak
memory, proof of tile availability, or elevation coverage**. Exact integer
north/east rectangle edges do not add an entire neighboring tile; borders
share samples. The probe rejects invalid, non-finite and dateline-crossing
regional bounds through the existing validator. Negative longitude/latitude
tile naming and zero-degree seams have unit tests.

## Recommended staged architecture (not implemented in PR83)

**A. Prepare a trusted terrain artifact at build time.**

- Run a bounded offline reproducibility experiment in a disposable directory,
  using explicitly supplied and SHA-pinned DEM inputs. Prove that an HGT tile
  is present, decodes to exactly the expected dimensions, obeys the big-endian
  convention and has usable non-void coverage inside a chosen test rectangle.
- Measure compressed size, **peak** disk during install/update, memory,
  cold/warm sampling latency and independent altitude error against known
  surveyed points/representative trails. Do not assume that advertised 30 m
  resolution equals vertical accuracy.
- Compare original HGT vs independently chunked/indexed formats. Avoid
  decompressing all nominal tiles into the Android heap. Bound both
  per-request sample count and resident tile cache.

**B. Add an independently verified elevation component to a *new* region
manifest schema, if measured feasibility succeeds.**

- Preserve v1 four-component reader/install behavior for all existing
  immutable regions. Introduce a strict opt-in v2 format with a fifth
  `elevation` component, independently checksummed files, source/datum
  provenance, verified coverage/no-data metadata and explicit bounds.
- New v2 installation stages/verifies *all required components* before
  committing a new build. Unsupported/partially installed elevation must not
  silently mark the region Ready for height features. A v1 region stays fully
  usable for routing with elevation **unavailable**, not zero.
- Never append a fifth file into a published v1 build ID, change the v1
  layouts in place, mutate signed code-8 artifacts, or overwrite retained
  published region paths. Observe the static-host distribution/retention
  budget and test upgrade/cancel/rollback with old installed regions.

**C. Sample heights only after an actual route is selected (first feature).**

- Use the selected **routed** polyline, not straight-line stop segments.
  Sample with explicit bounded spacing and sample count; preserve gaps as
  `null`/unavailable. Keep heights/analysis distinct from canonical
  route coordinates, route generation, GPX and search-point identity.
- Evaluate either a pinned **separately tested** mobile-wrapper upgrade
  (`height` requires verified on-disk elevation directory + correct native
  actor lifecycle) or a bounded read-only height sampler for the new
  component. Do not assume the existing 0.5.1 actor supports `height`.
- Return deterministic metadata: source/component identity, sample spacing,
  complete/partial coverage, and no-data counts. Never silently use a
  remote height API, treat missing elevation as sea level, or interpolate
  across a long missing segment.

**D. Compute and display D+/D− only once the profile is trustworthy.**

- Altitudes and total ascent/descent are different features: high-frequency
  DEM noise can arbitrarily inflate naive sum-of-positive-differences.
  Specify and test one distance-aware smoothing/threshold policy with
  synthetic flat, step, slope, summit, noisy, void and reversed-track cases.
- Show unknown/partial elevation clearly; do not report `D+ = 0` when
  valid data are missing. Validate against independent reference tracks
  across plains and steep terrain. Do not claim survey-grade accuracy.
- Route difficulty/grade optimization belongs **after** stable read-only
  analysis, because ranking candidate routes requires consistently available
  elevation during search, not just analysis of the winner.

## Explicit acceptance gates for follow-up PRs

1. **Rights/provenance:** documented redistribution authorization/attribution
   for every source actually published, source bytes/hash and datum.
2. **Format/migration:** strict v1 compatibility plus reject-on-corrupt v2;
   atomic update/rollback; no overwrite of a retained immutable build.
3. **Storage/performance:** measured gzip/component size, bounded peak
   installed/update disk, no excessive mobile memory, cold/warm latency on
   the Fairphone 6; no premature increase to admission budgets.
4. **Sampling correctness:** fixture tiles including negative coordinates,
   border seam, invalid size, void, out-of-range and intentionally absent
   data; no accidental download in offline mode.
5. **Analysis correctness:** fixed algorithm and elevation-source version
   recorded; deterministic D+/D−; unknown remains unknown; regression
   against independent trail baselines.
6. **Product boundaries:** no change to actual route geometry, explicit
   Generate behavior, authorization model, GPX schema, Play tracks or
   live social feature flags merely to add route elevations.

## Suggested next changes

- **PR84 — terrain prototype:** externally acquired, separately licensed
  fixture (outside Git), validated importer/compact artifact proof, size and
  coverage report; no public region publication.
- **PR85 — regional v2 + on-device sampler:** schema versioning, robust
  installer, native or bounded read-only height access, old-v1 compatibility,
  Android unit tests and physical offline checks.
- **PR86 — elevation profile + D+/D−:** calibrated algorithm, UI, missing
  coverage behavior and reference route comparisons.
- **PR87+ — elevation-aware route search:** only after the preceding
  coverage/accuracy and performance evidence, with explicit planning
  preferences and stable trade-off/ranking semantics.

PR numbers after #83 are provisional scopes, not authorization to publish
new regional data, alter Play release tracks, or change signing.
