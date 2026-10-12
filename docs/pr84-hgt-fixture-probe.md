# PR84 — Local Skadi HGT validation and sampling prototype

**Status:** build-time/read-only experiment. There is no distributed terrain
artifact, regional schema change, Android implementation, elevation UI, ascent
calculation or elevation-aware routing in this PR.

## Motivation and unchanged boundaries

[PR83's elevation assessment](pr83-elevation-feasibility.md) found that the
published region and pinned Android Valhalla configuration do not provide a
verified elevation surface or expose the mobile `height` operation. Before
introducing new data into an immutable regional product, we need a deterministic
and independently testable primitive for accepting or rejecting **explicit,
locally supplied elevation bytes**.

The existing map/routing/Places/Nature manifests, route coordinate contract,
native Valhalla configuration, GPX output, signed code-8 AAB, public Yvelines
build and Play tracks remain unchanged. This probe does **not** fetch DEM data
and is not a production Android sampler.

## Explicit input and read-only CLI

```sh
# Use a separately acquired, vetted local HGT file. This command does not
# download a tile. Source SHA-256 must be checked independently.
sha256sum /absolute/private/path/N48E001.hgt.gz

uv run python -m sugarglider.offline_regions.elevation_hgt_probe \
    --tile /absolute/private/path/N48E001.hgt.gz \
    --sha256 <64-lowercase-hexadecimal-SHA256> \
    --latitude 48.5 --longitude 1.5

uv run pytest -q tests/unit/test_pr84_elevation_hgt_probe.py
```

- Rejects unsafe/noncanonical Skadi names and tile corners outside the
  latitude [-90, 90) and longitude [-180, 180) grid.
- Requires an explicit SHA-256 of the **compressed source bytes** and rejects
  mismatches **before decompression**.
- Caps compressed input to one HGT grid plus a conservative margin, and caps
  gzip decompression at **25,934,403 bytes**. A valid grid has exactly
  **3601 × 3601 × 2 = 25,934,402 bytes**, big-endian signed int16. Gzip
  integrity errors and truncated/oversized files are failures.
- Scans pixels to report valid, void (`-32768`), and otherwise out-of-range
  heights (outside [-16384, 16384]); reports min/max of valid data only.
- Optionally bilinearly samples a latitude/longitude **belonging to that tile**
  using Valhalla 3.6.3's north-to-south row orientation, discarding invalid
  corners and normalizing the surviving weights. Missing data, another tile,
  invalid or nonfinite coordinates yield JSON `null`, never invented 0 m.
- Outputs JSON **to stdout only**; does not write any files, mutate any build,
  contact a network service, or read signing/keystore data.

The entire uncompressed grid is held in memory to simplify this isolated
prototype. Its memory/performance behavior is **not** acceptable evidence for
a final on-device cache or regional distribution format. The point scan is
linear in the number of grid pixels, rather than a production-time-per-point
operation. It processes **one** pinned file, not a directory with implicit
downloads, a patchwork of DEM sources or a user-selected global elevation map.

## Repeatable synthetic acceptance

`tests/unit/test_pr84_elevation_hgt_probe.py` manufactures gzip-compressed
3601 × 3601 signed-int16 tiles in temporary directories. No third-party
terrain bytes are committed or downloaded. The suite checks:

- Strict canonical tile filenames and negative-coordinate naming.
- Raw decoded length and pixel statistics.
- Constant-altitude bilinear samples and an exact north–south gradient.
- Distinguishing void (`-32768`) from out-of-range heights.
- Rejecting wrong expected SHA-256, short/oversized grids and corrupt gzip.
- Exact integer-degree tile boundaries and the no-neighbor-sampling rule.
- Deterministic CLI reporting without any new filesystem outputs.

This establishes HGT **format parsing and algorithm tests**, not measured
terrain quality, source coverage, Android memory, or redistribution rights.

## Gates before extending regional products

1. **Independent real input:** acquire a small tile outside Git; document
   official source, terms, license/attribution, exact source bytes/hash, vertical
   datum, acquisition date and provenance. Determine whether terrain derived
   from multiple upstream DEMs can legally be redistributed.
2. **Real-data integrity:** check the actual gzip/size/hash, no-data ratio,
   source grid orientation and plausible altitude samples. Independently
   compare several elevations at surveyed/known points, including voids,
   ridges, cliffs, flat terrain and regional boundaries.
3. **Resource study:** measure compressed download size, decoded cache,
   install/update peak storage, actual Android memory and cold/warm sampling
   on the Fairphone 6. Choose a streaming/chunked or cached representation
   based on measurements, rather than copying this Python probe into Android.
4. **Schema/migration:** only after those gates, consider a versioned optional
   elevation product with exact component identity, checksums, provenance,
   strict v1 compatibility, atomic install and explicit missing-data semantics.
5. **UI + D+ correctness:** sample selected *routed* geometry and stabilize
   an ascent/descent filtering policy before elevation-aware optimization.
   Do not alter existing route or GPX contracts silently.

No DEM source, derived data, Android binary, region catalog or Play Console
configuration is changed or published by this PR.
