# PR36 regional offline maps

PR36 adds explicitly installed regional vector basemaps to the shared web layer.
The same manifest parser, store, PMTiles source, selection policy, MapLibre style,
and management UI run in desktop browsers and the Android WebView. There is no
Android map implementation and no user-agent branch. Map packs and PR32–35 routing
packs are independent: either may exist without the other and their IDs need not
match.

## Storage and rendering architecture

`navigator.storage.getDirectory()` (OPFS) was selected because it provides
origin-private persistence and `File.slice()` byte-range reads through standard web
APIs. The startup capability probe creates a directory and file, writes known bytes,
closes it, reopens it, reads a slice, verifies the bytes, and removes the file. A
failed probe produces `map_pack_storage_unavailable`; it does not select a hidden
native implementation.

Installed data has one completion-first layout:

```text
<OPFS>/sugarglider-map-packs/<pack_id>/
  manifest.json
  basemap.pmtiles
```

Installation streams the bounded archive into OPFS, validates its PMTiles v3 header
and vector-layer metadata, then writes `manifest.json` last. A directory without the
manifest is an ignored partial install. Cancellation, download failure, and stale
operations cannot activate a pack. Existing completed packs are never silently
replaced; removal is a separate confirmed action. Browser persistence is requested
only during explicit installation and remains best effort.

The shared `offlineMapSnapshot()` diagnostic reports the active pack and current
bounded-source read count/bytes when a pack is open. It is observational only and is
available for later physical latency/read measurements.

The vendored PMTiles 4.5.0 public `Source`/`PMTiles`/`Protocol` APIs connect bounded
OPFS `File.slice()` reads to MapLibre GL JS 4.7.1. The local no-label style comes from
the vendored `@protomaps/basemaps` 5.7.2 `light` flavor and renders earth/land,
landcover, land use, water, buildings, roads, and paths present in that schema. It
has no remote style, glyph, sprite, font, icon, or token dependency. Existing route,
planner-point, Auto Tour, location, and outing overlays remain above the replaceable
basemap source. Local-pack attribution from the manifest remains on MapLibre's
visible attribution control.

Both vendored projects are BSD-3-Clause. Exact npm archive, source revision,
integrity, workspace-file hashes, and license hashes are recorded beside the files
in `static/vendor/pmtiles-4.5.0/README.md` and
`static/vendor/protomaps-basemaps-5.7.2/README.md`. Map data is derived from the
user-supplied regional OpenStreetMap PBF plus the open supporting sources downloaded
by the pinned Protomaps/Planetiler build. OpenStreetMap and the derived
osmdata.openstreetmap.de land/water polygons are ODbL 1.0; ESA WorldCover
landcover is CC BY 4.0; Natural Earth is public domain. The development templates
keep all of those sources visible in their attribution rather than relying on a
network-loaded license notice.

## Manifest and deterministic selection

Manifest schema v1 accepts exactly these fields: `schema_version`, `pack_id`,
`display_name`, `bounds`, `min_zoom`, `max_zoom`, `format`, `tile_type`,
`archive_filename`, `byte_size`, `attribution`, `data_source`, and `build_id`.
The schema requires version 1, safe identifiers, finite ordered Web-Mercator bounds,
a bounded 0–22 zoom range, PMTiles v3 MVT, the fixed `basemap.pmtiles` filename, a
positive size no greater than 2 GiB, and non-empty attribution. Unknown fields,
path traversal, URL-like filenames, invalid archive headers, mismatched sizes, and
missing required vector layers are rejected.

A pack covers the current map center when that coordinate is inside its inclusive
bounds. Of all covering packs, the one with the smallest longitude/latitude bounds
area wins; equal areas use lexicographic `pack_id`. PR36 never stitches packs. A
region switch removes the prior local layers and source before adding the selected
one. Offline with no covering valid pack retains the neutral background and reports
`no_covering_map_pack`; it never requests the configured raster source. Online with
no local coverage retains the existing attributed raster behavior.

The OPFS scan completes before map construction. A synchronous bootstrap preflight
uses that same selector against `config.initial_center`. When it finds a covering
pack, the initial MapLibre style contains only the neutral background and cannot
start an online raster request; the local PMTiles source is then attached on map
load. If opening that selected pack fails, the failure remains explicit and the
online raster is added only when connectivity is available. Offline failure remains
on the neutral background.

## Installation and network security

The compact shared **Offline maps** panel reports OPFS support, installed packs,
size/bounds, active identity, progress, cancellation, removal, and explicit failure.
Production installs require HTTPS. HTTP is accepted only when both the application
and pack host are localhost, loopback, link-local, or private-LAN debug origins.
Credentials, query strings, fragments, redirects, encoded responses, and
`javascript:`, `data:`, `file:`, or `content:` sources are rejected. Requests omit
credentials and referrers and bypass the HTTP cache. There is no location-triggered,
background, or automatic download.

The PWA shell is generation v21. It caches the small first-party PMTiles runtime,
style helper, and map modules, but never a `.pmtiles` archive. Explicit installer
requests use `cache: no-store`, which the worker ignores, so arbitrary manifest URLs
also stay outside the shell cache. Third-party raster/vector tile requests and APIs
remain excluded. Android `allowFileAccess = false`, `allowContentAccess = false`,
and `MIXED_CONTENT_NEVER_ALLOW` are unchanged.

## Development pack build

Generated data lives under ignored `data/map-packs/`. The build takes an explicit
local regional `.osm.pbf`; it does not fetch or cache raster tiles:

```sh
make map-pack REGION=marly PBF_INPUT=/absolute/path/to/marly.osm.pbf
make map-pack REGION=paris PBF_INPUT=/absolute/path/to/paris.osm.pbf
```

The two templates cover the approximate development bounds
`[2.00, 48.80, 2.16, 48.94]` and `[2.25, 48.80, 2.42, 48.92]`. The script pins
Protomaps Basemaps source revision
`3ea8293a28131c3dc63f1bb20827bdb8a76df06f` with archive SHA-256
`7b8e71f18627754af756923f6613a9008b5f1ff82377fff4e617157d053fc807`
and container
`maven:3.9.13-eclipse-temurin-21-alpine@sha256:194053d8f204a39710e564b49ba4d22188159fd29f073b8da1715aac61503132`.
The container supplies Java 21, Maven, and the Planetiler-based builder. The final
manifest records the archive header, byte size, pinned builder revision, and prefixes
of both the input-PBF and final-archive SHA-256 values. That output identity therefore
changes if a downloaded supporting dataset changes. An existing output is refused and
must be removed explicitly before rebuilding.

Serve each generated `manifest.json` and adjacent `basemap.pmtiles` from an HTTPS
host with CORS enabled, or a permitted local/private debug HTTP host, then paste the
manifest URL into the shared panel. Development distribution is intentionally not a
production catalog.

## Acceptance status

- **Desktop Chrome storage/harness: PASS.** Chrome 152.0.7977.64 completed the real
  OPFS create/write/close/reopen/slice/read/delete probe and all 17 deterministic
  PR36 browser scenarios. The scenarios also cover the official PMTiles source,
  strict manifests, exact bounded reads and EOF, install/reload/remove, partial and
  cancelled installs, URL policy, offline/online fallback, attribution, selection,
  startup raster suppression, failed-local-open fallback, region cleanup, overlay
  preservation, and absence of remote style assets.
- **Desktop Chrome real Marly archive and restart: PASS.** The installed
  `marly-map-dev-v1` archive is 11,614,476 bytes with SHA-256
  `da1eb88daf572190c01359d1679db49191b25f4c47f016ce7704429334dfaff9`.
  It survived a full Chrome-process restart with the original pack-download server
  unavailable and reopened from OPFS as `local_pack_active`. The pre-fix run exposed
  16 transient `tile.openstreetmap.org` requests during startup. After the v21
  bootstrap-ordering fix, a fresh Chrome process was started on `about:blank`,
  DevTools Network capture was enabled before navigation, and the application was
  then navigated to the planner. Across 73 captured requests there were zero
  `tile.openstreetmap.org` requests, zero requests to the former pack server, and
  zero HTTP PMTiles archive requests. The local attribution remained visible.
- **Desktop Firefox: PENDING.** The available Snap Firefox headless run did not
  complete and produced no OPFS result; this is not recorded as either a browser
  pass or an OPFS failure.
- **Fairphone 6 / Sugarglider Debug shared OPFS install: PASS.** The same
  `marly-map-dev-v1` archive was installed through the shared PR36 web UI into
  Android WebView OPFS. The WebView reported random-access OPFS support, the stored
  archive was exactly 11,614,476 bytes, no partial or invalid pack was present, and
  the shared PMTiles/MapLibre runtime activated the pack with real bounded reads.
  No Android-native map-storage adapter was required.
- **Fairphone 6 full radio-off physical acceptance: PASS.** With FastAPI and
  GraphHopper stopped, the temporary pack server stopped, all `adb reverse`
  mappings removed, Android airplane mode set to `1`, and Wi-Fi disabled, the debug
  application was force-stopped and freshly relaunched from the cached v21 PWA
  shell. `marly-map-dev-v1` reopened from OPFS as `local_pack_active`; the archive
  remained exactly 11,614,476 bytes and PMTiles diagnostics reported 6 reads /
  333,196 bytes. MapLibre attribution remained present, with zero OSM raster
  requests, zero pack-server requests, zero API requests, and no map error.
  `navigator.onLine` remained `true` in this WebView despite the Android radio
  state, so acceptance is based on the authoritative Android airplane/Wi-Fi state,
  absence of PC/reverse transports, and observed resource requests.
- **PR35 Auto Tour over the PR36 local basemap, full radio-off: PASS.** Without
  restoring connectivity, the fixed Marly `hike` Auto Tour with seed 35 generated
  two retained graph-routed candidates using routing pack `marly-dev-v1` while the
  independent map pack `marly-map-dev-v1` remained active. Generation used 6 of
  the 24 allowed local route calls and reported 978 ms total latency. The retained
  routes were 14.38 km and 14.04 km, both within the configured 2.5 km tolerance
  around the 12 km target, and were passed to the shared MapLibre Auto Tour
  renderer. During that run there were zero OSM raster, backend API, or pack-server
  requests. No separate manual screenshot is recorded.
- **Real Paris archive and regional switch: PENDING.** No physical Paris-pack
  switch result is recorded.

The required Marly physical acceptance is therefore complete: the same open
web-layer map implementation works on desktop Chrome and Android WebView, persists
the regional PMTiles archive in OPFS, survives process/app restart, renders without
remote basemap dependencies, and coexists with fully local PR35 routing. Paris
switching remains a separate follow-up after connectivity restoration.

## Explicit limitations

PR36 does not provide whole-country/world coverage, cross-pack stitching, automatic
downloads, updates, synchronization, eviction policy, hillshade/DEM, satellite
imagery, turn-by-turn navigation, on-device vector-tile generation, POI/nature index
migration, iOS-native code, or a production CDN/catalog. The first local style is
label-free and does not promise preservation of every OSM trail/tag. OPFS may still
be evicted by the browser. PR36 does not change Valhalla, GraphHopper, routing-pack
selection, the six local profiles, PR35 Auto Tour ranking, tracking, saved-route
immutability, or outing/live-position semantics.
