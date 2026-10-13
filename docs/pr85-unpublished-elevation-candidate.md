# PR85 — reproducible, unpublished elevation candidate staging

This PR turns the read-only PR83 coverage planner and PR84 single-file HGT
validator into a **separately staged, verification-only** local terrain research
artifact. The candidate is **not** an installable Sugarglider region or a
fifth component in the existing regional schema. It does not affect Android,
Valhalla routing, user data, Play uploads, GPX, or published immutable regions.

## Why this is a preparatory step, not a release

- The currently advertised Yvelines product has map, routing, Places and
  Nature only. Existing `RegionalManifest` schema 1 remains strict.
- Valhalla is built with `--additional-data-elevation ""`; Android still has
  `AdditionalData(elevation = "")` and the pinned `valhalla-mobile 0.5.1`
  only exposes `route`.
- AWS Mapzen/Terrain Tiles are documented in the
  [AWS Open Data Registry](https://registry.opendata.aws/terrain-tiles/).
  Its dataset is an amalgam of terrain sources, with explicit upstream
  [attribution obligations](https://github.com/tilezen/joerd/blob/master/docs/attribution.md).
  Access by URL is *not* a blanket right to redistribute with the app.
- No real terrain tile was available inside the PR author's execution
  environment at PR preparation time. **No measured real-data file sizes,
  elevations or height validation are claimed by this PR.**

## Input contract

The operator supplies local files previously acquired and pinned outside Git.

```text
/data/private/skadi-source/
    skadi/N48/N48E002.hgt.gz

/data/private/skadi-pins.json
```

Example for the `marly` development region, which requires **one** nominal
Skadi tile. Replace the placeholder SHA with the *actual SHA of the exact
compressed source file*, and supply its actual acquisition date.

```json
{
  "dataset": "Mapzen Terrain Tiles / AWS Open Data — source review pending",
  "acquired_on": "2026-10-13",
  "sources": [
    {
      "path": "skadi/N48/N48E002.hgt.gz",
      "sha256": "<actual 64 lowercase hex digits>",
      "source_url": "https://s3.amazonaws.com/elevation-tiles-prod/skadi/N48/N48E002.hgt.gz"
    }
  ]
}
```

The source URL is **recorded only**; the code neither opens it nor downloads
data. The `dataset` string is descriptive provenance, not a license claim.

For `yvelines-ouest-parisien`, the PR83 coverage planner lists the four
nominal required tiles:

```text
skadi/N48/N48E001.hgt.gz
skadi/N48/N48E002.hgt.gz
skadi/N49/N49E001.hgt.gz
skadi/N49/N49E002.hgt.gz
```

The pinned manifest must list **all** of them in that canonical order. Even
a single missing tile fails the candidate build; no partial download,
transparent fallback, silent zero elevation, or change to route generation
is permitted.

## Commands

Run with Python 3.13 and the repository's locked dependencies.

```sh
# Discover exact expected tiles first (no network).
uv run python -m sugarglider.offline_regions.elevation_feasibility \
  --region marly

# Verify the exact separately acquired bytes yourself.
sha256sum /data/private/skadi-source/skadi/N48/N48E002.hgt.gz

# Stage a disposable research candidate, outside Git and published paths.
uv run python -m sugarglider.offline_regions.elevation_candidate build \
  --region marly \
  --input-dir /data/private/skadi-source \
  --pins /data/private/skadi-pins.json \
  --output /data/private/elevation-research-marly

# Revalidate every tile and record against the current region spec.
uv run python -m sugarglider.offline_regions.elevation_candidate verify \
  --region marly \
  --output /data/private/elevation-research-marly
```

For a single input tile, further sample checks are available with PR84:

```sh
uv run python -m sugarglider.offline_regions.elevation_hgt_probe \
  --tile /data/private/skadi-source/skadi/N48/N48E002.hgt.gz \
  --sha256 <actual_sha256> --latitude 48.88 --longitude 2.05
```

## Guarantees and limits

- The input pin document names **exactly** the required spatial tile paths,
  in deterministic order, with a 64-character lowercase SHA-256, HTTPS source
  URL ending in that path, dataset label and ISO date.
- All source files must exist and match their SHA **before** staging.
  Each gzip is size-bounded, decoded to exactly 3601 × 3601 signed big-endian
  int16, scanned for valid/void/out-of-range samples, and reverified after copy.
- The new candidate is first built in an owned temporary sibling directory,
  then independently validated and atomically renamed. Existing output is
  never overwritten. Any failure leaves the input unchanged and does not
  publish a new candidate.
- The deterministic research-only manifest lists original source URLs,
  hashes, compressed/decoded byte sizes, pixel coverage counts and valid
  min/max elevations. It always has
  `"publication_allowed": false`. Validation rejects any attempt to flip this
  value and any missing/extra/corrupted candidate file.
- This is **only a data-integrity and staging proof**. The measured buffer
  is decoded into Python memory per tile, and every tile is scanned on
  validation. No Android memory, transfer latency, performance or vertical
  accuracy was measured. A 1-arc-second output grid is not proof of
  1-arc-second source resolution or high vertical accuracy.

## Next required gates

1. Run the candidate builder on actual acquired and checksum-pinned
   `N48E002.hgt.gz` and then the full Yvelines inventory. Preserve the
   input SHA hashes, candidate manifests, failure logs and per-tile acquisition
   facts **outside** Git.
2. Independently check elevations and no-data statistics at known
   surveyed locations, and compare sources where Mapzen quality or
   datum varies. Quantify coverage, median/error/peak error, and missing
   values before committing to a source.
3. Audit redistribution terms and attribution for **all applicable upstream
   datasets**; the research-only flag cannot be changed by this tool.
4. Measure real compressed sizes, on-device peak storage/update overhead,
   sampling latency and memory on Fairphone 6. Determine a bounded tile cache
   or chunked representation from those measurements.
5. Only then propose a separately reviewed `RegionalManifest` v2 (optional
   independent elevation component) with v1 backwards compatibility, strict
   atomic installation, and an offline Android height sampler. Add D+/D− and
   elevation UI only after coverage and smoothing accuracy are measured.

The next architecture step is therefore **gated by real data and licensing**,
not by another Android release. Keep the working code-8 Play package and
published Yvelines regions unchanged.
