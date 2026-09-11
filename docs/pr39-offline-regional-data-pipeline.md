# PR39 — Offline Regional Data Build Pipeline

PR39 produces files. PR42 will make the app download/install those files.

## Scope and commands

Option C builds regional vector maps, routing graphs, POI and nature indexes
from **one explicit local OSM PBF**. No bulk third-party raster tiles, tile
server, routing server, runtime CDN logic, download UI, upload or publication
is added. The normal planner, Android capabilities and strict component formats
are unchanged. PWA shell remains **v22**. No Fairphone acceptance is required.

Run from the repository with Python 3.13, `uv` and Docker available:

```sh
make offline-region REGION=marly PBF_INPUT=/absolute/path/source.osm.pbf
make offline-region REGION=paris PBF_INPUT=/absolute/path/source.osm.pbf
make offline-region-verify REGION=marly
```

Equivalent CLI (optional URL is informational provenance, never a download):

```sh
uv run python -m sugarglider.offline_regions build --region marly \
  --pbf /absolute/path/source.osm.pbf --source-url https://example.org/source.osm.pbf
uv run python -m sugarglider.offline_regions verify --region marly
```

Missing input, unsupported region/template configuration and insufficient or
missing source header bounds fail before Docker. `scripts/download_osm.sh`
remains a separate explicit source-download operation; PR39 never downloads
mutable latest OSM input. Successful build/verify prints source SHA-256 and
every component ID, file size, SHA-256 and final directory.

## Region specification and independent formats

`offline-regions/{marly,paris}.json` use strict schema version 1:

```text
schema_version: 1
region_id, display_name
bounds: [west, south, east, north]
map: {pack_id, template}
routing: {pack_id, engine: valhalla, engine_version: 3.6.3,
          access_modes: [foot, bicycle]}
pois: {component_id}
nature: {component_id}
```

The typed schema is `offline_regions/models.py:RegionSpec`. Unknown fields,
non-finite/reversed/out-of-range bounds, invalid IDs, duplicate component IDs,
unsafe paths and symlinks are rejected. Bounds are non-dateline WGS84, limited
to Web Mercator latitude. The spec owns bounds; existing map templates must
match its map ID and all four bounds exactly. The current builder supports
template zooms 0–15 only. Adding a region needs a spec and matching template,
not another shell case.

| Region | Bounds | Map ID | Routing ID | POI / nature IDs |
| --- | --- | --- | --- | --- |
| Marly | `[2.00,48.80,2.16,48.94]` | `marly-map-dev-v1` | `marly-dev-v1` | `marly-pois-dev-v1` / `marly-nature-dev-v1` |
| Paris | `[2.25,48.80,2.42,48.92]` | `paris-map-dev-v1` | `paris-dev-v1` | `paris-pois-dev-v1` / `paris-nature-dev-v1` |

Map remains strict PR36 manifest v1 + PMTiles v3/MVT. Routing remains strict
PR33/34 manifest v2 + normalized Valhalla 3.6.3 tar, foot+bicycle. POI remains
current gzip JSON index v2/classifier 1; nature remains gzip JSON index v1.
Existing classifiers, meaningful POI approaches and polygon handling are reused.
No POI/nature runtime schema is extended with a component ID: those identities
live in the new distribution manifest. No production Île-de-France pack contract
is established.

## Regionalization and coverage

Map uses the existing explicit bounds option. Routing reuses the PR33
graph-way/restriction extractor **only for routing**. It is not a generic
POI/nature extract and is never used as input to those indexes.

POI/nature builders read the original complete source with osmium's existing
location/area assembly. Optional build-only bounds select nodes inside the box
and fully assembled way/polygon/multipolygon geometries intersecting it.
Complete relation members, holes and polygon geometries are preserved, not
clipped. The POI builder retains full-source public paths and access-node
context for its existing meaningful-approach algorithm. Unrelated distant
features are excluded. Intersecting features and their semantic points or
approaches may extend outside the box; this does **not** enlarge declared
coverage. Ordinary builds without bounds keep their prior behavior.

Both bounded builders and pipeline require valid source header bounds covering
the entire requested box. Published index metadata declares that box, not the
larger source bounds or boundary-feature extent. Header coverage is evidence
about the supplied extract, not proof of OSM completeness, access legality,
absence of malformed source objects or correctness of every source geometry.
Existing invalid-feature handling remains; no completeness beyond that evidence
is asserted. Reading complete source context trades build time/memory for
relation correctness; no new extraction dependency is introduced.

## Distribution layout and verification

```text
data/offline-regions/<region-id>/
  manifest.json
  map/manifest.json
  map/basemap.pmtiles
  routing/manifest.json
  routing/valhalla_tiles.tar
  pois/index.json.gz
  nature/index.json.gz
```

The new strict `RegionalManifest` schema v1 contains `region_id`,
`display_name`, `bounds`, `source`, `tools`, `components`, and `build_id`.
Exactly four components each contain `component_id` and `files`; each of the
six downloadable files (including both nested manifests) has a fixed safe
relative `path`, `byte_size`, SHA-256 and explicit `format`.
The outer manifest does not hash itself. Source identity contains basename,
byte size, SHA-256, header bounds, `coverage_evidence: osm-header-bounds` and an
optional source URL. It contains no local absolute input path or timestamp.

Validation checks all final bytes/hashes, exact component identity/bounds,
unchanged manifest schemas, PMTiles header/type/zooms/section ranges,
normalized tar members and its `index.bin` tile offsets/IDs/sizes, and
both index documents using their existing models. It rejects missing/extra
files, traversal, absolute paths, symlinks, mismatched source/index metadata,
corruption detectable by these checks and a mismatched content build ID.
This structural validation does not replace engine routing or full MVT decoding.
PMTiles sections may appear in any non-overlapping order, with the root directory
inside the first 16 KiB, as specified by the
[PMTiles v3 format](https://github.com/protomaps/PMTiles/blob/main/spec/v3/spec.md).
The addressed-tile, tile-entry and tile-content counts are informational: each
may be zero when unknown. PR39 does not infer emptiness from those counters.
Valhalla's index layout follows the
[pinned 3.6.3 extract builder](https://raw.githubusercontent.com/valhalla/valhalla/3.6.3/scripts/valhalla_build_extract).

The directory is static-hosting-ready for a later GitHub Release or object-store
copy without rewriting contents. No source PBF is distributed. The components
remain independently installable/updateable/removable, not an opaque combined
archive. Attribution stays in the unchanged map manifest.

## Atomicity and provenance

The pipeline takes an exclusive per-region build-directory lock, creates a
temporary sibling staging directory, targets existing component builders at
new isolated outputs, hashes final bytes, writes and validates the top-level
manifest, then renames the validated directory into place. Publication refuses
an existing output, including symlinks; no replacement option is provided.
Exceptions clean owned staging and release the lock. Concurrent cooperating
builds cannot publish the same region. As with ordinary filesystem tooling,
the output parent is trusted against hostile concurrent filesystem mutation;
an abrupt kill/power loss may leave a staging directory/lock requiring operator
inspection. Existing verified `data/map-packs` and `data/valhalla` packs are
never replaced by PR39; their existing build caches can be reused.
In isolated mode, shell-builder working directories and Planetiler temporary
data live inside the pipeline-owned staging tree, not alongside older packs.

The original map manifest writer is shared as a build-only Python module with
its existing script entry point retained. Both historical shell builders accept
an optional new destination. Routing's isolated mode excludes its temporary PBF;
legacy publication behavior is retained outside PR39.

Provenance records pipeline version 1, Protomaps revision
`3ea8293a28131c3dc63f1bb20827bdb8a76df06f`, its checked source archive SHA-256,
the existing digest-pinned Maven/Temurin image, Valhalla image
`ghcr.io/valhalla/valhalla:3.6.3`, POI classifier/index versions, nature index
version, and actual Python/osmium/Shapely versions. Valhalla is version-tag
pinned, not digest pinned. Python dependencies come from the existing `uv.lock`.

Input SHA-256 is checked before and after building. Deterministic JSON, gzip
mtime 0, existing normalized Valhalla tar, final hashes, and a SHA-256 build ID
of canonical manifest content provide auditable artifact identity. There is no
wall-clock build timestamp; the informational URL is excluded from the build ID.
Identical bytes, source identity and tool provenance
produce identical manifests. This does **not** establish universally bitwise
reproducible PMTiles/Valhalla output across environments. Protomaps `--download`
may fetch build support data and Maven dependencies; support datasets are not
all content pinned. Such build-time access is not an offline-build guarantee.

All generated distribution files, owned temporary builds/locks and caches stay
under ignored `data/` locations; no PBF, PMTiles, graph tar, gzip index or generated
manifest belongs in Git. Source specs, tiny test fixture, code, tests and this
document are source-controlled inputs only.

## Validation and next work

Automated validation: `make check` **PASS**, 980 passed / 16 deselected;
Ruff and strict mypy **PASS**. PR39 has 47 passing focused tests, including five
tile-count cases. The earlier targeted PR32–PR39 run had 95 passing tests,
before those five regressions. No runtime web assets or Android files changed,
so browser harnesses and Android validation were not rerun.

Real Marly build acceptance: **PASS**. The final end-to-end `make offline-region`
command exited 0, followed by a separate successful `make offline-region-verify`.
The final directory has exactly the seven files listed above, no source PBF,
407 POIs and 6,734 nature features. All four components report the Marly bounds
`[2.0,48.8,2.16,48.94]`. Owned staging/lock directories were removed; the older
verified map/routing packs were not replaced. Paris configuration and fixtures
are validated, but no real Paris PR39 pipeline build was run.
The accepted Marly PMTiles header reported counts of `457/457/457` (addressed
tiles / tile entries / tile contents). Allowing unknown counts does not change
this acceptance result or require another real build.

Source: `ile-de-france-latest.osm.pbf`, **335,288,680 bytes**, SHA-256
`2ac2b0d9c7ca8374af078a6f564c342a08a2634a110c1f18bae1cbd1cda5d849`;
header bounds `[1.445097,48.11918,3.560409,49.24271]`. No source URL was supplied.
Recorded Python/osmium/Shapely versions: `3.13.5` / `4.3.1` / `2.1.2`.
Regional build ID:
`9d59b0dc3a0ec70ba28bd909b62adb57bea9dce33e3ec552cf5cea6a3b2eb121`.

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| `map/manifest.json` | 615 | `192e3fe3d408cedd61f44345f50c9fa9bfa8449e6effbad0ebd605ea82cbe752` |
| `map/basemap.pmtiles` | 11,571,642 | `5ba1d7c85d955fb5b40421b8a4654e0dbd0422a07634f6c49342aeadc01100a1` |
| `routing/manifest.json` | 251 | `9dea95eb6192dc85a0a9a17b0a4cc0106e96ec25699671b01bf23c922f5de5a4` |
| `routing/valhalla_tiles.tar` | 11,939,840 | `1135d9596e195e3240fe195318006aaf8fe7dcc982228a45c5509425d9a17ce9` |
| `pois/index.json.gz` | 22,000 | `4019e24246efb213bda55f909a7e6b37d973d7ed3e679a94d029167fd4187176` |
| `nature/index.json.gz` | 1,007,894 | `c00bcc869b586afc62bee8881595e369b9421bcacd273c02dc5f2ce6b6154084` |

Performance limitation: this accepted run took about **44 min 32 s**, including
roughly **27 min** for POIs and **8 min** for nature. Bounded output does not
avoid full-source Python/OSM processing; this is a build-time cost, not phone
runtime performance evidence. The POI metadata records 16 skipped invalid
source objects; that is a source-wide counter, not 16 proven in-region omissions.

An initial attempt exposed an over-strict new PMTiles section-order check.
The check was corrected against the v3 specification and the real archive;
a regression test covers metadata-after-tiles, overlap and out-of-file ranges.
That attempt was interrupted before publication and its owned temporary state
cleaned; the final acceptance uses a fresh end-to-end build with the correction.

Build-time network observations: both Docker images and the checksum-pinned
Protomaps source archive were cached. Existing support files were reused:
`daylight-landcover.gpkg`, `land-polygons-split-3857.zip`,
`water-polygons-split-3857.zip`, `natural_earth_vector.sqlite.zip`,
`pgf-encoding.zip`, `qrank.csv.gz` and `tile_weights.tsv.gz`.
No new source PBF, image or support dataset download was observed. Maven's
resolver recorded metadata refreshes for `org.eclipse.emf.common` and
`org.eclipse.emf.ecore` (Central metadata/SHA-1, plus checks against configured
snapshot/OSGeo repositories), and Central availability checks for GeoTools
33.0 POMs (`gt-shapefile`, `gt-main`, `gt-http`, `gt-epsg-hsql`, `gt-referencing`,
`gt-metadata`, `gt-api`, `net.opengis.ows`, `org.w3.xlink`) and
`jgridshift-core:1.3`. No new dependency JAR download was observed. These are
log/cache observations, not a packet capture or a zero-network claim.
Nonfatal container warnings included Maven/Fontconfig cache permissions and
Planetiler's attempt to delete its mounted temporary-directory root; the
pipeline-owned temporary tree is cleaned after the container exits.
Tests use tiny local OSM XML converted to PBF and injected map/routing builders;
they never need network, Docker, large map data or a phone. They exercise actual
node/way/polygon/multipolygon and hole preservation, distant exclusion,
deterministic gzip/manifests, source coverage, safe paths, compatibility,
corruption, cleanup, overwrite refusal, CLI wiring and v22 isolation.

PR40 can consume the local POI/nature artifacts for Auto Tour v2; PR41 can make
local planning the normal Android planner; PR42 owns client download/install
UX. PR43/44 remain social-server deployment and Play Store hardening. PR39
does not claim any of those runtime capabilities.
