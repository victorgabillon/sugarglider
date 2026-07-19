<p align="center">
  <img
    src="assets/brand/sugarglider-banner.png"
    alt="Sugarglider — trail-running route generation"
    width="100%"
  />
</p>

<p align="center">
  <strong>Generate trail-running routes from required places and a target distance.</strong>
</p>

# Sugarglider

Sugarglider is an open-source trail-running route generator in development. The
long-term product will combine required waypoints, target distance, trail and nature
preferences, popularity signals, access rules, and limits on repeated sections.

The implemented PR1–PR11 scope supports both a start-only, preference-driven Auto
Tour and the established mandatory-waypoint planner. It asks a
self-hosted GraphHopper 11.0 instance to route them along real OpenStreetMap edges,
analyzes the routed edges, and can search for several closed-loop candidates near a
target distance. A local browser interface supports planning, comparison, local GPX
inspection, mapped-nature comparison, synchronized named required-point editing,
bounded scenic and hydration-place discovery, and clean GPX 1.1 export of an
already selected candidate. Its browser interface uses the local Sugarglider
identity and mascot pins without adding a frontend build system.

## Current scope and architecture

```text
browser -> FastAPI -> RouteService ----------> routing backend -> GraphHopper / OSM
                    RouteGenerationService --+       |
                    AutoTourService ----------+       +-> isochrone + routed loops
                       |                              +-> routed path details
                       +-> sampling, ordering, low-overlap beam search
                       +-> graph + loop-geometry + optional nature analysis
                       +-> score, ranking, diversity
                    visualization projection + GPX writer

local OSM PBF -> nature builder -> deterministic polygons -> startup STRtree
              -> POI builder ----> deterministic points ---> startup STRtree
                                                           -> bounded POI API
           |
           +-> packaged HTML/CSS/ES modules -> MapLibre -> configured raster tiles

assets/brand -> deterministic byte-copy sync -> packaged /static/brand assets
```

The public API uses named `lat` and `lon` fields. The adapter converts anchors to
GraphHopper's `[longitude, latitude]` JSON order and preserves that same GeoJSON
order in routed responses. The GPX writer then emits the final routed coordinates as
`lat` and `lon` trackpoint attributes. It never draws, interpolates, or falls back to
straight lines.

The analyzer uses standard-library haversine distances for every geometry edge and
normalizes them to GraphHopper's authoritative route distance. Raw path-detail
breakdowns remain available alongside explainable derived metrics. Generation uses
a fixed, documented PR3 score; ordinary route analysis does not assign a score.
Every complete public route also receives explainable PR9 loop-geometry metrics in
projected metres. When the optional local nature index is available, the same
normalized edges are intersected with OSM polygons and receive a separate,
explainable PR7 nature score. The API never parses the PBF or calls a hosted GIS
service during a request. Temporary low-overlap beam states use only the existing
structural analysis and never run Shapely geometry or nature analysis.

Generation defaults to fixed required-anchor order. An explicit optimized-loop mode
keeps the first point fixed while proposing deterministic visit orders for every
other mandatory point. Generation then closes the sequence, asks GraphHopper for
round-trip detour proposals, samples those proposal geometries at cumulative-distance
positions, and reroutes the complete sequence. Proposal coordinates never become
route lines: only final GraphHopper geometry is returned.

## Prerequisites

- Python 3.13
- [`uv`](https://docs.astral.sh/uv/)
- Docker with Docker Compose
- `curl` and several gigabytes of free disk space for the Île-de-France extract and
  imported graph

## Local Python setup and checks

Install the locked Python environment:

```sh
uv sync
```

Run the complete service-independent check suite:

```sh
make check
```

This checks Ruff formatting and lint, strict mypy typing, and all tests except those
marked `integration`. Unit tests use an in-memory HTTP transport and require neither
Docker, internet access, map data, nor GraphHopper.

To run the API directly against a GraphHopper exposed on the host:

```sh
cp .env.example .env
uv run uvicorn sugarglider.api.main:app --reload
```

Then open `http://localhost:8000/`. The same FastAPI process serves both the API and
the packaged browser application; no Node runtime or separate frontend server is
used.

Canonical editable artwork lives in `assets/brand`. Synchronize its explicit asset
manifest into the packaged application after any approved artwork update:

```sh
make brand-assets
```

The synchronization script resolves paths from its own location, rejects missing
or unexpected PNGs, and copies the permitted files byte-for-byte without Pillow,
resizing, or recompression. The runtime copies under
`src/sugarglider/web/static/brand` are generated mirrors and must not be edited.

## Web route planner

The GUI has two independent planning modes. **Auto Tour** is the fresh-session
default: choose one start, a target, optional hard anchors, direction, scenic,
verified-water, nature, loop-shape, distance-priority, and low-overlap preferences.
It builds graph-routed loop skeletons before considering close-enough places.
**Waypoint Route** preserves the existing
mandatory-point request, import, ordering, and generation behavior and its unchanged
defaults. Switching modes preserves each form's points and settings.

Request JSON import follows the active mode. In Auto Tour, the first point becomes
the exact start and the remaining (at most 30) named points become ordered requested
close-enough places, defaulting to a 100 m visit radius and `must_visit` importance;
the browser does not switch modes. Castle, viewpoint, or verified-water metadata may
select the documented 200 m, 125 m, or 50 m radii. In an explicitly selected
Waypoint Route, the same JSON retains its old exact mandatory-coordinate semantics.
When an Auto Tour document also provides explicit `start`, `end`, or `hard_points`,
those coordinates retain exact semantics while every unconsumed legacy `points`
entry is merged with `requested_places`. Explicit requested-place metadata wins;
stable IDs, or otherwise exact normalized coordinate-and-name pairs, provide
deterministic deduplication. The import message reports the exact requested-place
count and discarded-coordinate count, which is normally zero.
Imported requested places immediately appear through their own MapLibre GeoJSON
source as reusable Sugarglider mascot pins with compact `R1`, `R2`, … badges. A
cream, green, or red halo shows pending, satisfied, or missed status; preferred
places receive a secondary ring, and the selected pin is raised above its peers.
Selecting a marker or its keyboard-accessible list row opens a DOM-safe measured-
result popup and displays its actual visit-radius circle. An advanced map toggle can
display every missed-place radius; these circles are proximity thresholds, not
routing-access polygons. Verified drinking water continues to use its separate blue
water mascot sprite.

The Waypoint Route workflow remains:

1. Use **Import request JSON** to load a generation request such as
   `examples/marly/all-pois-generation-request.json`, or enable **Add point on map**
   and click once per mandatory place.
2. Rename, edit, drag, remove, select, or reorder POIs. The first is the fixed loop
   start/end; do not add a closing duplicate. Names imported from JSON—including
   accents—remain attached to their coordinates through editing and export.
3. Choose target and tolerance in kilometres, point ordering, candidate count, and
   natural-shortest or low-overlap path selection. Optionally choose **Prefer
   balanced loops** and **Prefer mapped nature** when the local nature index is
   available, then generate. Distance, backtracking, and repetition remain higher
   priorities than either preference.
4. Select candidate cards or route lines to compare the server-returned ranking.
   Orange dashed sections are repeated edge runs; stronger red dashes are immediate
   stack-shaped out-and-back returns. The backend calculates both overlays using the
   same semantics as route analysis. **Show nature context** adds a wider patterned
   land-cover underlay without hiding those repetition styles.
5. Download the selected candidate. This posts its existing immutable `RouteResult`
   to `/v1/routes/gpx/from-result`; GraphHopper and generation are not called again.

**Import GPX** reads a local GPX 1.1 file entirely in the browser. Tracks, segment
breaks, optional waypoints, and a locally calculated approximate distance are shown
without uploading the file. Imported GPX and generated candidates can coexist on
the map.

### Branded markers, labels, and selection

Required POIs use draggable HTML markers composed from the single locally cached
`sugarglider-map-pin.png`. Every pin retains a visible current visit-order badge;
point 1 also carries an explicit start/end badge. The complete high-resolution PNG
is scaled with its aspect ratio intact. Pins use a compact 40 × 60 px footprint
(48 × 72 px for the start) on larger screens and 36 × 54 px (44 × 66 px
for the start) on phones, while a bottom-anchor offset aligns the painted pin tip
without cropping its transparent canvas. Generated routing points use small orange
diamonds, while imported GPX waypoints use asymmetric blue marks.

Names are shown through a coordinated hybrid system. DOM markers provide dragging,
keyboard focus, safe detail popups, and persistent numeric identity. One MapLibre
GeoJSON source supplies collision-aware symbol labels; ordinary names may hide when
space is tight and appear from zoom 10.5, while the selected name is promoted from
zoom 7, wraps within a bounded width, and remains above collisions. The selected
point is shared by the marker, symbol label, and POI editor, and map-originated
selection scrolls only the internal POI list. Explicit marker, label, POI-row,
Enter, or Space activation opens a detail popup once; dragging, candidate changes,
and nature or display redraws never reopen it. Optimized candidates update marker
and editor badges to their returned visit order without changing the stored request
points. The map legend starts collapsed so it does not cover dense routes.

MapLibre 4.7.1 uses three packaged Open Sans Semibold glyph ranges for Latin,
Latin-extended, and general-punctuation labels, so no runtime glyph service is
introduced. Their exact source revisions, retrieval date, covered chunks, hashes,
missing-range behavior, and Apache 2.0 license are recorded in the
[font provenance](<src/sugarglider/web/static/fonts/Open Sans Semibold/README.md>).
Names using other scripts remain fully recoverable in marker popups and the POI
editor even when the map symbol layer lacks that glyph range.

The interface uses semantic landmarks, visible keyboard focus, a semantic POI list
whose compound list items expose the current point with `aria-current`,
keyboard-selectable POI rows and candidate cards, text-safe DOM APIs for point
names, `aria-live` generation feedback, and reduced-motion handling. At tablet and
phone widths the map moves ahead of the controls, panels stack, candidate cards
scroll horizontally, and the POI editor retains its own bounded vertical scroll.

The basemap requires network access to the configured raster tile service and to
the pinned MapLibre GL JS 4.7.1 CDN distribution. MapLibre GL JS is distributed
under the BSD 3-Clause license. The default tiles are OpenStreetMap tiles and their
visible contributor attribution must not be hidden. This application does not
prefetch, bulk-download, or provide offline tiles.

### Scenic and hydration places

The **Places** disclosure queries only the current map viewport from the local POI
index. Requests wait for map movement to finish, debounce for 250 ms, cancel stale
work, and enforce the server result limit. MapLibre renders clustered GeoJSON
sources rather than a DOM marker per regional feature. Ordinary labels are
collision-aware and begin at useful zoom levels; a separately sourced selected
marker and label remain visible even when nearby features cluster. Inline SVG
artwork is generated locally for distinct scenic, historic, tower, attraction,
unknown-water, and non-potable marker shapes. Verified drinking water alone uses
the packaged blue `sugarglider-water-pin.png`, loaded once as a MapLibre symbol
image; it is not instantiated as one DOM image per regional POI. No icon CDN is
used.

Defaults show primary scenic places and verified drinking water. Unknown-potability
fountains/taps, broad tourist attractions, and restricted access are opt-in.
Private and explicitly non-potable features are available only through the advanced
controls. Selecting a discovered place highlights it and opens a DOM-safe popup; it
does not add, remove, reorder, or move a required route point and has no effect on
generation, ranking, analysis, or GPX output.

In Auto Tour, popups for public/restricted primary scenic places and mapped verified
drinking water offer **Prefer in Auto Tour**. This adds a stable ID to a maximum-eight
soft preference list; it never creates an exact waypoint. Private and explicitly
non-potable POIs cannot be preferred. Selected-place state remains separate from
selected mandatory-point state. Accepted visits use stronger map styling and are
listed in route-progress order with their measured visit distance, insertion status,
detour attribution, and public reward breakdown.

Requested close-enough places are a separate, stronger objective than discovered
OSM POIs. Every candidate reports every requested place in original input order,
its configured importance and radius, the measured final-route distance, whether it
was deliberately routed, and an explicit satisfied or missed reason. They are never
silently discarded for lying outside the discovered-POI corridor.

The offline classifier accepts only these exact OSM combinations:

| Exact tags | Category | Meaning |
| --- | --- | --- |
| `tourism=viewpoint` | `viewpoint` | primary scenic |
| `historic=castle` | `castle` | primary scenic; `ruins=yes` is retained as metadata |
| `historic=ruins` | `ruins` | primary scenic |
| `historic=archaeological_site` | `archaeological_site` | primary scenic |
| `man_made=tower` + `tower:type=observation` | `observation_tower` | primary scenic |
| `tourism=attraction` | `tourism_attraction` | broad scenic |
| `amenity=drinking_water` | `drinking_water` | verified in mapped data unless `drinking_water=no` |
| `drinking_water=yes` plus `man_made=water_tap`, `amenity=fountain`, `natural=spring`, `man_made=water_well`, or `amenity=water_point` | `drinking_water` | verified in mapped data |
| `amenity=fountain` with no `drinking_water` tag | `fountain` | potability unknown |
| `man_made=water_tap` with no `drinking_water` tag | `water_tap` | potability unknown |
| a recognized hydration form plus `drinking_water=no` | form-specific hydration category | explicitly non-potable and hidden by default |

Generic `tourism=yes`, `historic=yes`, and `building=historic` are not selected.
If one OSM object matches several classes, it emits one marker identified by OSM
type and ID, retains secondary categories, and uses fixed priority: verified water,
viewpoint, observation tower, castle, archaeological site, ruins, broad attraction,
unknown water, then non-potable water. Distinct objects are never merged only
because their name or coordinate matches.

Access maps `yes`/`public` to public, `no`/`private` to private, and values such as
`customers`, `permissive`, `destination`, `delivery`, and `designated` to
restricted. Missing or unrecognized access stays unknown. Popups expose only a
small sorted tag subset and use careful language: a verified source is mapped in
OpenStreetMap as drinking water; unknown means potability is not specified; and
non-potable means it is mapped as non-potable. None of these claims current water
quality, availability, operation, or legal access.

### Web configuration

| Environment variable | Default | Purpose |
| --- | --- | --- |
| `SUGARGLIDER_MAP_TILE_URL` | `https://tile.openstreetmap.org/{z}/{x}/{y}.png` | Raster XYZ template |
| `SUGARGLIDER_MAP_ATTRIBUTION` | `© OpenStreetMap contributors` | Visible map credit |
| `SUGARGLIDER_MAP_INITIAL_LAT` | `48.87` | Initial center latitude |
| `SUGARGLIDER_MAP_INITIAL_LON` | `2.10` | Initial center longitude |
| `SUGARGLIDER_MAP_INITIAL_ZOOM` | `11.0` | Initial regional zoom (0–22) |
| `SUGARGLIDER_NATURE_INDEX_PATH` | `/data/nature/ile-de-france-nature-index.json.gz` | Local deterministic nature index |
| `SUGARGLIDER_NATURE_WATER_BUFFER_M` | `100` | Mapped-water proximity buffer (0–1000 m) |
| `SUGARGLIDER_NATURE_MISSING_INDEX_WARNING` | `false` | Log a missing default index as warning rather than information |
| `SUGARGLIDER_POI_INDEX_PATH` | `/data/pois/ile-de-france-poi-index.json.gz` | Local scenic/hydration POI index |
| `SUGARGLIDER_POI_MISSING_INDEX_WARNING` | `false` | Choose warning rather than info logging for a missing POI index |
| `SUGARGLIDER_POI_DEFAULT_LIMIT` | `500` | Default viewport result limit |
| `SUGARGLIDER_POI_MAX_LIMIT` | `1000` | Hard public viewport result limit |
| `SUGARGLIDER_AUTO_TOUR_SCENIC_CORRIDOR_RADIUS_M` | `600` | Scenic opportunity corridor (50–2000 m) |
| `SUGARGLIDER_AUTO_TOUR_WATER_CORRIDOR_RADIUS_M` | `350` | Verified-water opportunity corridor (25–1000 m) |
| `SUGARGLIDER_AUTO_TOUR_INCLUDE_BROAD_ATTRACTIONS` | `false` | Permit broad attractions without an explicit preferred ID |

These validated values are exposed to the browser by `GET /v1/ui/config`. Tile
templates and attribution are deployment configuration, not frontend constants.

## Map data and Docker startup

Download the Geofabrik Île-de-France PBF explicitly:

```sh
make download-osm
```

The script is idempotent, writes through a temporary file, and supports
`FORCE=1` and an `OSM_PBF_URL` override. PBF files and imported graph caches are
ignored by Git.

Build the local nature index from that same PBF:

```sh
make nature-index
# Equivalent explicit command:
uv run python -m sugarglider.nature.build \
  --osm-pbf data/osm/ile-de-france-latest.osm.pbf \
  --output data/nature/ile-de-france-nature-index.json.gz
```

The builder streams OSM areas with pyosmium, filters tags before retaining
geometry, repairs straightforward invalid polygon topology with Shapely
`make_valid`, and atomically writes canonical gzip JSON with a zero gzip timestamp.
It reports feature/class counts, skipped invalid features, compressed and
uncompressed sizes, and elapsed time. Generated indexes under `data/nature` are
ignored by Git. The API image contains Shapely but not the build-only `osmium`
package, and the PBF is never copied into that image.

Build the local scenic and hydration POI index from the same PBF:

```sh
make poi-index
# Equivalent explicit command:
uv run python -m sugarglider.pois.build \
  --osm-pbf data/osm/ile-de-france-latest.osm.pbf \
  --output data/pois/ile-de-france-poi-index.json.gz
```

The POI builder streams nodes, located ways, and assembled relation areas. Nodes
retain their coordinate; valid polygonal ways and multipolygon relations use an
interior `representative_point()` with relation holes preserved; non-area ways use
a deterministic midpoint measured in the shared local metric projection. Invalid
geometry is skipped and counted. Features and public tags are sorted, JSON is
canonical, gzip metadata has a zero timestamp, and the output is atomically
replaced. The report includes category/potability/access counts, skipped-invalid
count, sizes, bounds, SHA-256, and elapsed time. Rebuilding identical input produces
byte-identical output without embedding an absolute path or current timestamp.

Generated files under `data/pois` are ignored. Docker mounts that directory
read-only. The runtime image contains no pyosmium and never opens the source PBF.
FastAPI loads and validates the gzip once during lifespan startup, projects its
immutable point tuple once, and constructs one reusable Shapely STRtree. Each
request performs a tree bounding-box query and filters only returned candidates.
A missing or corrupt POI index leaves routing/generation operational and produces a
safe unavailable status and structured empty search response.

Run `make benchmark-pois` after building. It reports load time, process peak RSS,
and warm-up-excluded median and maximum viewport-query latency for Marly and central
Paris without adding flaky timing assertions.

Start GraphHopper and the API:

```sh
make up
make logs
```

The API bind-mounts `data/nature` and `data/pois` read-only. A missing or corrupt
index disables only its corresponding analysis or discovery feature, leaves
ordinary routing and generation available, and is visible through safe status and
deterministic warnings. The first GraphHopper startup imports
the PBF and creates the hiking graph and
landmark preparation under `data/graph-cache`; this can take several minutes and
substantial memory. Later starts reuse the bind-mounted cache. If the GraphHopper
configuration or PBF changes incompatibly, stop the stack and deliberately clear
the contents of `data/graph-cache` before rebuilding. Compose exposes GraphHopper
at `http://localhost:8989` and the API at `http://localhost:8000`.

## API

- `GET /health` checks only that the FastAPI process is alive.
- `GET /ready` checks GraphHopper `/info` and requires its `hike` profile.
- `GET /v1/nature/status` reports safe local-index metadata, configured water
  buffer, and warnings without exposing host directory paths.
- `GET /v1/pois/status` reports safe POI format/source metadata and category,
  potability, and access counts without exposing a host directory path.
- `POST /v1/pois/search` accepts a finite, non-dateline WGS84 bounding box plus
  category, group, potability, access/private, and bounded-limit filters. It returns
  deterministically ordered point features only—never source polygons or the full
  regional index.
- `POST /v1/routes` returns routed GeoJSON-order coordinates, summary metrics,
  snapped anchors, raw path details, and typed route analysis.
- `POST /v1/routes/gpx` computes the same route and returns a downloadable GPX
  containing exactly one track and one segment.
- `POST /v1/routes/generate` returns the required-anchor baseline, ranked candidates,
  and bounded-search diagnostics.
- `POST /v1/tours/generate` runs the separate skeleton-first Auto Tour search and
  returns its no-POI control, ranked complete candidates, POI visits/rejections,
  strict request accounting, and phase timings.
- `POST /v1/routes/generate/gpx` repeats the deterministic search and exports its
  best candidate as the same clean, track-only GPX format.
- `POST /v1/routes/gpx/from-result` exports a posted `RouteResult` without routing or
  generation.
- `POST /v1/routes/visualization` returns contiguous typed GeoJSON sections marked
  normal, repeated, or immediate-backtrack, plus optional server-derived nature
  properties for map rendering. It never returns raw nature polygons.
- `GET /v1/ui/config` returns validated browser map configuration.

### Skeleton-first Auto Tour

Auto Tour asks GraphHopper for one walking isochrone at half the target distance and
constructs deterministic six-vertex ellipse skeletons at eight bearings, three
aspect ratios, and two perimeter scales. The start lies on the ellipse perimeter,
not at its centre, so the initial candidate is already a start-to-start tour rather
than a radial spoke with an invented connector. Ellipse perimeter is solved in local
projected metres; an ellipse is uniformly shrunk until every vertex lies within the
real isochrone. Optional hard anchors (maximum six) are inserted in stable angular
order. Every public line is then a complete GraphHopper route with `pass_through`—an
ellipse is only a routing-point proposal and never exported geometry.

When `/isochrone` is unavailable, each headed GraphHopper round trip remains a raw
no-insertion control and also supplies a deterministic sampled fallback skeleton.
Five to eight ordered anchors are sampled from actual graph-routed geometry using
cumulative progress and sector diversity, kept at least 250 m apart, and routed
again through the normal multipoint API with `pass_through=true`. These sampled
skeletons participate in requested-place routing, discovered-POI insertion, corridor
repair, and alternative-leg repair; fallback mode never disables deliberate POI
routing merely because the isochrone endpoint returned 404.

At most six diverse graph-valid controls continue to POI search, and all distinct
retained base controls remain eligible for the returned candidate pool. The best
global no-insertion control is identified separately, while incidental scenic or
water value on another control can still affect recommendation. A local STRtree
queries a 600 m scenic and 350 m verified-water corridor by default. A POI counts as
visited only when the final routed geometry lies within its exact neighborhood:
viewpoint 150 m, observation tower 120 m, castle 200 m, ruins and archaeological
site 150 m, broad attraction 120 m, and verified drinking water 50 m. Representative
OSM coordinates are approximations and still have to route and snap successfully.

Rewards are public and separate from route quality: verified water 6.0, viewpoint
5.0, observation tower 4.5, castle 4.0, archaeological site and ruins 3.0, and broad
attraction 1.5, plus a 1.0 category-diversity bonus, diminishing returns for repeated
categories, a one-time 2.0 verified-water bonus, and a 3.0 preferred-ID boost.

In default `distance_priority="flexible"`, graph validity and exact hard anchors come
first, followed by feasible must-visit requested places, severe immediate
backtracking and loop-coherence gates, preferred requested places, repetition and
corridor quality, total discovered-POI value, nature/trail quality, and a continuous
distance penalty. A separate bounded requested-place candidate family runs before
discovered-POI insertion, tries deterministic imported, spatial, cheapest-insertion,
and bounded relocate/2-opt orders, and records complete-set attempt, success,
distance, safety, and rejection diagnostics. Flexible treats target distance as a
late preference: an optional user maximum applies when supplied, otherwise the
200 km server safety maximum applies. `balanced` retains
`target + max(2 × tolerance, 25% × target)` and a stronger distance charge;
explicit `strict` preserves tolerance-first selection. Flexible and balanced gates
allow bounded quality trade-offs but never a large immediate out-and-back. Relative
to a family control, flexible caps backtracking at +2 percentage points, repetition
at +8 points, outbound/return proximity at +8 points, loop-geometry penalty at
+0.40, and new crossings at one. Balanced tightens those limits to +1, +2, +4,
+0.20, and zero respectively; strict retains the earlier no-regression gate.

Loop analysis splits a closed route at its farthest progress point and compares
bounded 60 m samples of outbound and return halves outside the endpoint
neighborhoods. The public outbound/return proximity share detects narrow hairpins
even on different OSM edges. Angular monotonicity, largest sector share, and occupied
sector count make mixed one-sided loops visible and prevent a highly mixed route from
winning solely on target error when a coherent alternative exists.

Local repair can evaluate a bounded `A → P → Q → B` corridor continuation when a
singleton visit creates over 300 m of backtracking or high outbound/return
proximity. `Q` may be another requested place or a discovered scenic/verified-water
opportunity. The response explains repeated and immediate-backtracking distance
removed, distance added, requested/POI gains, geometry change, and reason
`corridor_continuation`. Marginal insertion distance becomes unavailable after a
global removal, replacement, corridor, or alternative-leg repair rather than
remaining as a stale final-route claim.

The public per-request bounds are one isochrone, eight GraphHopper round-trip
controls, 24 skeleton complete routes, 24 POI complete routes, 12 local-repair
complete routes, and 24 alternative-leg requests (92 route calls in the configured
default total). Cache hits consume no budget and are reported. Corridor evaluations
are a named subset of the existing 12-call local-repair budget. Missing POI or nature
indexes leave a graph-valid control with explicit warnings and unknown metrics. A
malformed or unsupported isochrone falls back to both raw and sampled headed
GraphHopper routes; timeout and global GraphHopper unavailability still propagate as
structured errors.

Mapped verified water means only that the local OSM extract classifies it as
drinking water. Auto Tour does not guarantee current access, opening, operation,
seasonal availability, water safety, or legal passage. It never calls Overpass or a
hosted POI service at runtime.

### Target-distance generation

Generation supports closed loops only. Supply at least two and at most 30 required
points without manually repeating the start; Sugarglider appends the start without
mutating the caller's list. Every required point remains mandatory. The default
`point_order_mode="fixed"` retains input order. With
`point_order_mode="optimize_loop"`, the first point remains start/end while all
other points become reorderable.
`target_distance_m` accepts 1–200 km, tolerance accepts 0.1–10 km, and one to five
candidates can be requested.

Path selection defaults to `path_selection_mode="shortest"`, which preserves the
PR4 result and ranking. Explicit `path_selection_mode="low_overlap"` first runs the
same standard generation, then refines up to two selected candidates. For every
consecutive pair in a candidate's exact routing-point sequence, GraphHopper returns
up to three graph-valid alternatives. A deterministic beam of at most 12 partial
routes composes those legs and analyzes repeated edge IDs across the complete route.
The separate default alternative-leg request budget is 48; identical leg requests
are cached across refinement sources.

Temporary beam states use structural route analysis only. Nature enrichment runs
for completed standard and refined candidates, as does loop-geometry analysis, so
increasing beam width does not multiply Shapely work that cannot affect beam
pruning.

Low-overlap recommendation still requires target tolerance first. A refined route
may outrank its standard source only when it lowers total repeated-edge share without
increasing immediate backtracking. Qualifying routes then rank by repetition,
backtracking, the existing PR3 score, target error, and stable signature. A route
that trades lower repetition for more obvious out-and-back traversal may still be
returned for comparison, but it is not recommended ahead of its source. One standard
candidate is retained as the public control. This optimization changes path
selection for an already chosen point order; it does not reorder mandatory POIs.

Nature preference defaults to `nature_preference="off"`. Omitting it or explicitly
using `off` preserves the pre-PR7 ranking. With `prefer`, target tolerance and
natural-loop validity remain hard constraints. Within tolerance, immediate
backtracking and total repeated-edge share are compared before the optional nature
score; the existing PR3 score, target error, and signature remain tie-breakers.
Outside tolerance, distance-error pressure remains first. An unknown nature score
stays null and sorts after known scores only at the nature comparison position—it
is never converted to zero. If nature was requested but unavailable, the existing
result is retained with `nature_index_unavailable`. If no eligible candidate raises
the score, the original recommendation is retained with
`nature_no_candidate_improvement`.

Nature-aware ranking runs over all successfully analyzed drafts before diversity
and candidate-count truncation. It does not generate geometry, alter signatures,
increase the full-route evaluation budget, or add GraphHopper calls. Low-overlap
source selection keeps the existing PR5 source and, when capacity permits, also
includes the strongest eligible nature source. A refined candidate still cannot
replace its source unless repetition falls without increasing immediate
backtracking; a nature score can never bypass that gate.

Loop-shape preference defaults to `loop_geometry_preference="off"`. Omitting it or
explicitly using `off` preserves PR8 proposal sampling, descriptor order,
GraphHopper calls, full-route evaluations, candidate signatures, and recommendation
for a deterministic graph and request. Geometry metrics remain additive in public
route analysis even in off mode. With `prefer`, the ordinary ranking keeps target
tolerance, outside-tolerance distance pressure, immediate backtracking, and total
repetition ahead of loop geometry. Low-overlap ranking retains its existing order
of tolerance, outside-distance pressure, repetition, and backtracking before loop
geometry. Nature follows geometry in both modes; the fixed PR3 score and stable
signature remain later tie-breakers. Missing geometry is null and sorts after known
geometry at that comparison position, never as numeric zero.

Preference promotion is control-gated. Prefer first completes the exact legacy
Off search and keeps its recommendation as the control. A candidate with a better
higher-priority tuple may replace that control even when its shape penalty is
worse; a candidate with a worse tuple cannot replace it. When the tuple is equal,
promotion requires a strictly lower exact public shape penalty. Otherwise the
control remains with `loop_geometry_no_candidate_improvement`. Nature ranking then
starts from that effective geometry decision and cannot worsen its ordering. For
low-overlap results, PR5's gate is applied first: a refined candidate must reduce
repetition without increasing immediate backtracking. Neither geometry nor nature
can rescue a candidate that fails that gate. The explicit primary control source
is refined before geometry and nature sources can use the remaining bounded leg
capacity.

Optimized mode evaluates at most 16 unique order proposals: original order,
clockwise and counter-clockwise angular sweeps, nearest-neighbour cycles, angular
cuts, and bounded 2-opt refinements. This is a deterministic geometric heuristic,
not exact TSP. At most three routed orders continue into detour generation, and all
order and detour evaluations share one full-route budget. Retention always protects
the best below-target order so it can be lengthened, even when longer mandatory
routes rank better as final candidates.

The detour search is deliberately small and deterministic for a fixed graph,
request, seed, and settings. It tries factors `0.60`, `0.80`, `1.00`, `1.20`, and
`1.45` at distinct required anchors and performs at most one refinement for a few
close candidates. Off mode keeps the existing cumulative 25/50/75% samples and
descriptor ordering exactly. Prefer runs that identical primary lane with the same
default 48 complete-route evaluations, proposal calls, refinements, caches,
signatures, and control recommendation. Successful primary round-trip proposal
geometry is retained in a deterministic cache.

After the primary lane, Prefer has a separate default allowance of 12 complete-
route evaluations. It revisits cached proposals in bounded angular descriptor
order, samples each at `1/12` through `11/12`, assigns positions to eight global
sectors, and greedily selects at most three points by new-sector coverage, circular
sector separation, radius, then stable earliest fraction. Only balanced forward
and reverse sequences are evaluated in this extra lane; another legacy sequence is
not. A missing cache entry is skipped without another GraphHopper round-trip call.
All optional points lie on routed proposal geometry; no radial or straight-line
WGS84 waypoint is invented.

`SearchSummary.base_search_budget` exposes the unchanged primary allowance.
`loop_geometry_extra_evaluation_budget`, `loop_geometry_extra_evaluated_count`,
`loop_geometry_extra_successful_count`, and
`loop_geometry_extra_rejected_count` expose the additive lane. Consequently the
default public `search_budget` is 48 in Off mode and 60 in Prefer mode, while
`evaluated_candidate_count` never exceeds that total. Proposal backend calls and
derived sequences remain separately accounted because one cached proposal can
derive multiple sequences. Full routes use `pass_through=true`; optional points
whose snapped positions move more than 300 m are rejected. GraphHopper round-trip
distance is approximate, and inserted proposal points are subsequently rerouted
through the entire required sequence, so the requested distance is not guaranteed.

Search statuses mean:

- `within_tolerance`: at least one returned candidate meets the requested tolerance;
- `best_effort`: candidates exist, but none meets it;
- `infeasible`: every successfully routed mandatory order exceeds target plus
  tolerance. The JSON result still contains the original fixed-order baseline.

Order counters exclude that fixed baseline. Every attempted non-baseline order is
classified exactly once as either a successful distinct source or a rejected
routing, snapped-waypoint, or duplicate-signature result.

Within-tolerance candidates always rank before candidates outside tolerance. Among
within-tolerance routes, ranking minimizes immediate backtracking, then total
repetition, the PR3 total score, absolute target error, and stable signature.
Outside tolerance, distance error retains strong pressure. The fixed PR3 score is:

```text
10.00 × distance error ratio
+ 3.00 × repeated-distance share
+ 2.00 × major-road share
+ 1.00 × paved share
+ 0.25 × unknown-surface share
- 1.50 × trail-like share
- 0.75 × official-hiking-network share
```

The response exposes every weighted component. Reward fields are positive
magnitudes subtracted from `total`. Target distance is the primary objective;
unknown surface has only a small uncertainty penalty and is not treated as paved or
as automatically poor trail. Stable SHA-256 signatures deduplicate candidates,
using edge runs when coverage is high and six-decimal geometry otherwise. A simple
edge-ID-set Jaccard filter prefers distinct routes and reports when low coverage or
candidate count requires relaxed diversity.

Every candidate exposes `required_point_order`, retaining original request indices
and coordinates. It includes the fixed start once and excludes automatic closure.
It also exposes immutable `routing_points`, containing the exact required and
generated points in construction order without the automatic closing duplicate,
and a `construction` value: `direct_order`, `round_trip_detour`,
`sector_balanced_detour`, or `alternative_leg_beam`. For optimized requests,
`baseline` is deliberately the original fixed-order route.

### Optional endpoints and route topology

Waypoint Route and Auto Tour accept optional `start`, `end`, and
`route_topology` (`auto`, `loop`, or `point_to_point`). Explicit endpoints are hard
constraints. Automatic topology remains a loop unless a distinct explicit end is
present, so legacy points-only Waypoint requests and start-only Auto Tours retain
their closed-loop behavior. `close_loop` remains a deprecated Waypoint input:
omitted topology derives its old meaning, while contradictory new/legacy fields
are rejected.

For Waypoint Route, `points` are ordered interior mandatory waypoints whenever
explicit endpoints are present. With no explicit start, the first point is consumed
as the inferred start; an open route can similarly consume the last distinct point
as its inferred end. `optimize_path` keeps both endpoints fixed and reorders only
interior waypoints. Open routing passes the actual `start → interiors → end`
sequence to GraphHopper and never generates a loop and cuts it.

Auto Tour resolves an omitted start from the lowest-index requested place and then
the first hard point. An explicitly selected point-to-point topology resolves an
omitted end from the highest-index distinct requested place and then the last
distinct hard point. Consumed places remain visible in public accounting as
endpoint-satisfied. Open Auto Tour retains the direct routed control, bounded
alternative routes, and endpoint-fixed hard-point routes; POI and requested-place
insertions can change only the interior sequence. Its response reports direct
distance, detour ratio, reverse destination progress, monotonicity, and lateral
deviation instead of applying loop-direction or closure diagnostics.

Both generation responses expose resolved topology, effective endpoints, endpoint
sources, snapped coordinates, snap distances, and safe endpoint warnings. Endpoint
snaps beyond the configured maximum are rejected. Selected-candidate GPX remains
one track and one segment: loop geometry stays closed, while point-to-point GPX ends
at the hard destination without re-appending the start.

The deterministic 45 km Flexible acceptance example consumes Gare de Marly-le-Roi
as the hard END from the unchanged original 23-place list, leaving exactly 22
requested places between Bastille and Marly. Import
`examples/marly/bastille-to-marly-22-places-auto-tour.json` in the browser so its
mixed endpoint/legacy-point schema is normalized before API submission.

Low-overlap optimization uses exact GraphHopper edge IDs. It cannot recognize nearby
parallel corridors as overlap, does not guarantee zero repetition, and cannot avoid
retracing forced by dead-end POIs. Dynamic history-dependent Java edge penalties,
custom GraphHopper plugins, and exact simple-cycle solving remain future work.

`SearchSummary.low_overlap_requested` distinguishes a search that did not run from
one that found perfect zero overlap. The pre/refined repetition and backtracking
shares are therefore `null` in shortest mode or when no standard source exists,
rather than using a misleading zero.

Generate the Marly 41 km example as JSON:

```sh
curl --fail --header 'Content-Type: application/json' \
  --data-binary @examples/marly/generation-request.json \
  http://localhost:8000/v1/routes/generate
```

Export its best candidate:

```sh
curl --fail --header 'Content-Type: application/json' \
  --data-binary @examples/marly/generation-request.json \
  --output /tmp/sugarglider-marly-41km.gpx \
  http://localhost:8000/v1/routes/generate/gpx
```

Or run the full readiness, JSON report, GPX export, and XML validation workflow:

```sh
make generate
# Custom JSON and GPX destinations:
./scripts/generate_marly.sh ./marly-generation.json ./marly-41km.gpx
```

Generate and validate the 23-POI optimized Marly loop:

```sh
make generate-all-pois
# Custom destinations:
./scripts/generate_marly_all_pois.sh ./all-pois.json ./all-pois.gpx
```

This workflow calls the same generation settings once with nature preference off
and once with it on, prints the index status and each candidate's graph/nature
metrics, reports whether the recommendation changed, and exports the already
returned prefer-mode `RouteResult`. It handles an unavailable index without
crashing. To isolate analysis performance for a saved response:

```sh
uv run python scripts/benchmark_nature_analysis.py ./all-pois.json
```

Compare PR9 loop-shape off/prefer generation with identical Marly request fields
and bounded budgets:

```sh
uv run python scripts/compare_marly_loop_geometry.py
```

The report includes each recommendation and best returned geometry candidate,
control and preferred signatures, exact higher-priority comparison, base/extra
accounting, complete shape/nature metrics, warnings, and runtime. It exits nonzero
if Prefer violates the control contract or its bounded accounting. It writes
response JSON and validated selected-candidate GPX only under `/tmp`; GPX export
posts the already returned `RouteResult` and does not rerun generation. To benchmark
isolated loop analysis after one excluded warm-up run, either route the existing
direct Marly example through the live API or supply saved response JSON:

```sh
uv run python scripts/benchmark_loop_geometry.py
uv run python scripts/benchmark_loop_geometry.py /tmp/sugarglider-marly-loop-off.json
```

### Local mapped-nature analysis

The deterministic index retains these exact OSM area classifications:

| Primary class | Accepted tags |
| --- | --- |
| Woodland | `natural=wood`, `landuse=forest` |
| Open natural | `natural=grassland/heath/scrub/fell/wetland/beach`, `landuse=meadow/grass` |
| Agriculture | `landuse=farmland/orchard/vineyard/plant_nursery` |
| Water | `natural=water`, `waterway=riverbank`, `landuse=reservoir/basin` |
| Urban/developed | `landuse=residential/commercial/retail/industrial/construction/brownfield/landfill/railway/garages`, `amenity=parking` |

Conflicting primary tags resolve in the fixed priority **urban → water → woodland
→ open natural → agriculture**. This conservative order prevents a lower-priority
natural tag from hiding explicitly developed or water land cover. `leisure=park`,
`leisure=nature_reserve`, `boundary=national_park`, and
`boundary=protected_area` form an independent park/protected overlay; protection
does not imply public access. Other `leisure=*` areas are not assumed natural.

Index polygons remain WGS84. At startup they are projected once to metres with a
fixed-reference-latitude regional equirectangular projection. This is suitable for
an extract such as Île-de-France, not a global equal-area projection; overly tall
indexes are rejected. Each normalized route geometry edge queries an STRtree and
uses exact line/polygon intersection fractions. Those fractions multiply the
authoritative GraphHopper-normalized edge distance. Midpoints, degree-as-metre
distances, and straight-line route fallbacks are never used.

Water proximity keeps an STRtree over original, unbuffered water polygons. Each
route makes one distance-bounded tree query, then buffers and unions only the
nearby candidates; the analyzer does not build or retain a buffered copy of every
regional water polygon at startup.

Woodland, open natural, agriculture, water crossing, urban, and unknown land cover
partition the complete route distance. Missing mapping and distance outside the
index remain visibly unknown. Park/protected and “within 100 m of mapped water”
(using the configured value) are independent overlays and can overlap any primary
class. Water proximity does not claim a water view.

The separate nature score starts at 50 and exposes every signed component:

```text
+ 50 × 1.00 × woodland share
+ 50 × 0.85 × open-natural share
+ 50 × 0.30 × agriculture share
+ 50 × 0.20 × park/protected share
+ 50 × 0.15 × near-water share
- 50 × 1.00 × urban share
- 50 × 0.10 × unknown share
```

The result is capped to 0–100. It expresses mapped environmental context, not
beauty, biodiversity, accessibility, public access, safety, or current conditions.

Generation makes several local GraphHopper calls and is intended for interactive
requests measured in seconds, not a high-throughput endpoint. The GPX endpoint
repeats the search rather than persisting the JSON endpoint's result.

### Route-analysis metrics

Every share is relative to the complete GraphHopper route distance:

- `paved`, `unpaved`, and `unknown_surface` partition the whole route. Unknown
  includes absent surface coverage, explicit nulls, missing/other values, and future
  unrecognized values.
- `trail_like` measures edges whose road class is track, path, footway, bridleway,
  steps, or pedestrian.
- `official_hiking_network` measures edges explicitly tagged with international,
  national, regional, or local foot-network membership.
- `major_road` measures travel on motorway, trunk, primary, secondary, or tertiary
  classified edges. It is not traffic measurement and does not measure proximity to
  a nearby road.
- `car_accessible` requires an explicit `car_access=true`; missing access data is
  not assumed true.
- `repetition` counts distinct GraphHopper edge IDs used in multiple traversal runs
  and measures only later runs as repeated distance. Its coverage and warnings must
  be considered because repetition cannot be inferred when `edge_id` is absent.
- `immediate_backtrack` is narrower than total repetition. It counts only the
  returning half of direction-reversed edge stacks such as `A → B → A`, retaining
  up to 64 outward geometry-edge traversals. Longer spurs deterministically count
  only their innermost 64 returning edges. `backtrack_edge_id_coverage` and warnings
  expose uncertainty.
- `detail_breakdowns` reports explicit values and coverage for every returned path
  detail. Explicit null is a bucket; uncovered geometry is not invented as a value.

#### Explainable loop geometry

Loop geometry uses the route's first position as its start and the same normalized,
GraphHopper-authoritative edges as route analysis. A single deterministic local
equirectangular projection supplies metre coordinates to loop and nature analysis;
nature alone retains the regional extract-span validation. The public metrics are:

- `closed`: projected start/end gap at most the named 25 m closure tolerance.
  Non-closed routes report `loop_geometry_route_not_closed`, zero enclosed area,
  and zero compactness while preserving the other meaningful measurements.
- `enclosed_area_m2`: for a closed route, the sum of distinct positive faces after
  noding and polygonizing the routed line network. Repeated sections do not multiply
  area, and figure-eight lobes remain separate faces. A route whose final position
  is within the 25 m closure tolerance uses a synthetic start connection for this
  area calculation only; it does not alter route geometry, distance, repetition,
  corridor analysis, or GPX. Degenerate geometry yields zero with a warning rather
  than relying on a raw polygon from route coordinates.
- `convex_hull_area_m2`: projected line convex-hull area, or zero for a line/point.
- `compactness = clamp(4π × enclosed area / authoritative route distance², 0, 1)`.
  A circle approaches 1 and a square approximately 0.785; long stems and repeated
  laps reduce it.
- `sector_distance_shares`: authoritative edge distances assigned by midpoint
  bearing to exactly eight equal sectors around the start. An edge midpoint at the
  start uses its direction deterministically. Positive-distance shares sum to one.
  `sector_balance = -Σ(p log p) / log(8)` is normalized Shannon entropy: one-sided
  concentration approaches 0 and even angular coverage approaches 1.
- `mean_radius_m`: authoritative-distance-weighted projected midpoint radius, and
  `max_radius_m`: maximum projected position radius. Maximum radius is explanatory
  and is not independently minimized.
- `elongation`: minor/major axis ratio of the minimum rotated rectangle of the
  route hull. Approximately equal width approaches 1; a thin corridor approaches
  0; degenerate lines and points are zero.
- `self_crossing_count`: unique interior point crossings of non-adjacent routed
  edges. Adjacent edges (including first/last in a closed route), shared vertices,
  and collinear overlap are excluded; crossing points are deterministically
  deduplicated within 0.10 m.
- `near_parallel`: authoritative route distance within 40 m of a non-local section
  that is parallel or anti-parallel within 30 degrees and separated by at least
  250 m along the cyclic route axis. One shared STRtree finds nearby edges; unioned
  neighbor buffers prevent double counting. A perpendicular crossing and ordinary
  adjacent bends do not qualify.

The separate shape penalty is lower-is-better and does not alter PR3
`CandidateScore.total`:

```text
0.25 × min(self-crossing count, 8)
+ 3.00 × near-parallel share
+ 1.25 × (1 - compactness)
+ 0.75 × (1 - sector balance)
+ 0.25 × (1 - elongation)
```

The API exposes every exact input, weight, component, and the component sum. This is
not a beauty, scenic-value, safety, accessibility, legality, or trail-condition
score. Dense urban/path networks, OSM completeness, GraphHopper simplification, and
source geometry resolution can affect self-crossing and corridor detection.

For example, the JSON response includes this shape (values are illustrative):

```json
{
  "analysis": {
    "route_distance_m": 22515.9,
    "geometry_distance_m": 22480.1,
    "distance_scale_factor": 1.00159,
    "paved": {"distance_m": 7000.0, "share": 0.31},
    "unpaved": {"distance_m": 13000.0, "share": 0.58},
    "unknown_surface": {"distance_m": 2515.9, "share": 0.11},
    "trail_like": {"distance_m": 15000.0, "share": 0.67},
    "official_hiking_network": {"distance_m": 9000.0, "share": 0.40},
    "major_road": {"distance_m": 500.0, "share": 0.02},
    "car_accessible": {"distance_m": 6000.0, "share": 0.27},
    "repetition": {
      "edge_id_coverage": {"distance_m": 22000.0, "share": 0.977},
      "available": true,
      "unique_edge_count": 180,
      "traversed_edge_run_count": 187,
      "repeated_edge_count": 5,
      "repeated_distance": {"distance_m": 650.0, "share": 0.029}
    },
    "warnings": ["edge_id_coverage_incomplete"]
  }
}
```

Percentages depend on the completeness and accuracy of OSM tags exposed through
GraphHopper. Missing coverage is retained in breakdown coverage, unknown-surface
distance, and deterministic warnings rather than guessed.

Route the Marly request as JSON:

```sh
curl --fail --header 'Content-Type: application/json' \
  --data-binary @examples/marly/request.json \
  http://localhost:8000/v1/routes
```

Export it as GPX:

```sh
curl --fail --header 'Content-Type: application/json' \
  --data-binary @examples/marly/request.json \
  --output /tmp/marly.gpx \
  http://localhost:8000/v1/routes/gpx
```

Or run the smoke check, which verifies readiness and validates the resulting XML
shape:

```sh
make smoke
# Custom destination:
./scripts/smoke_marly.sh ./marly.gpx
```

Generate a saved JSON response and print a compact Marly analysis report:

```sh
make report
# Custom destination:
./scripts/report_marly.sh ./marly-analysis.json
```

The reporting script uses Python rather than `jq` and prints all derived percentages,
repeated-edge distance, edge-ID coverage, and warnings.

After the stack is healthy, opt into the live integration test with:

```sh
RUN_GRAPHHOPPER_INTEGRATION=1 \
GRAPHHOPPER_URL=http://localhost:8989 \
uv run pytest -m integration
```

Stop the services with `make down`.

## Data attribution and safety

Routing uses © [OpenStreetMap contributors](https://www.openstreetmap.org/copyright)
data distributed by [Geofabrik](https://download.geofabrik.de/) under the Open Data
Commons Open Database License (ODbL). This is attribution, not a legal
interpretation; downstream redistributors remain responsible for their obligations.
The generated index is derived from the configured OSM extract and therefore needs
the same OSM attribution and ODbL consideration when redistributed.

Shapely is a runtime dependency under the BSD 3-Clause license. pyosmium (`osmium`)
is used only by development/index-build environments under the BSD 2-Clause
license. Neither adds a runtime remote service dependency.

OpenStreetMap and routing engines can be incomplete or out of date. Generated
routes must still be checked against current local closures, land-access rules,
conditions, and on-the-ground signage before use.

## Current limitations and future work

All anchors remain mandatory. Fixed mode visits them as supplied; optimized mode
keeps the start fixed and uses bounded deterministic ordering rather than a globally
optimal solver. Exact POIs on dead-end paths can force unavoidable retracing. The
score is an explainable starting heuristic rather than a scientifically validated
measure of quality, and edge-ID diversity is set-based rather than distance-weighted.
Elevation is disabled, so GPX trackpoints contain no invented elevations or
timestamps, and GPX files contain no analysis extensions.

Nature analysis is limited to selected mapped OSM polygons. It does not infer
scenic quality, satellite land cover, biodiversity, viewpoints,
elevation, popularity, accessibility, water visibility, uploaded activities,
current closures, or real-world trail conditions. There is no geocoding,
persistence, account system, elevation profile, or offline map. OSM tags and access
data may be absent or stale. Every generated route still requires visual inspection
and validation against local access rules, signage, closures, and conditions on the
ground.

Place discovery and soft Auto Tour collection are limited to the exact selected OSM
tags in the configured extract.
Names, access, opening hours, seasonal status, potability tags, and the existence or
operation of a fountain/tap can be missing, incorrect, or stale. The point chosen
for a polygon is a deterministic display position, not an entrance or routable
access point. An Auto Tour insertion routes the representative coordinate through
GraphHopper but accepts the POI only when final geometry enters its category-specific
neighborhood; this still does not prove a usable entrance or current access.

### Manual browser-test checklist

- [ ] Open `/`; confirm the map and visible attribution load.
- [ ] Confirm Auto Tour is the fresh-session default and Waypoint Route remains
      available with its former defaults and imported 23-point request behavior.
- [ ] Set the station start by map click and coordinate inputs; add up to six hard
      anchors and confirm the separate limits.
- [ ] In each planning mode, set and clear Hard start/Hard end independently; switch
      modes and confirm neither mode overwrites the other's endpoint markers.
- [ ] Generate Automatic, Loop, and Point-to-point requests; confirm open routes end
      at the END pin, show progress metrics, and never show loop direction as route
      quality.
- [ ] Import `examples/marly/bastille-to-marly-auto-tour.json`; confirm the START and
      END pins appear immediately and repeated imports do not duplicate markers.
- [ ] Confirm Auto Tour defaults prefer low overlap, balanced loops, mapped nature,
      scenic places, and verified water.
- [ ] Confirm the branded header, local favicon, and initial mascot guidance.
- [ ] Import the 23-POI Marly JSON; confirm exactly 23 mascot pins numbered 1–23.
- [ ] Confirm full accented names remain available while ordinary labels avoid
      collisions and the selected label stays visible.
- [ ] Select through a marker, map label, POI row, and keyboard; confirm synchronized
      state and internal-list scrolling.
- [ ] Reorder POIs and confirm every displayed visit-order number updates.
- [ ] Drag a marker and confirm its coordinate inputs update.
- [ ] Generate candidates in shortest and low-overlap modes.
- [ ] Select cards and map lines; compare metrics with generation JSON.
- [ ] Confirm repeated and immediate-backtrack styles are distinct.
- [ ] Confirm nature availability and the Off/Prefer control are visible.
- [ ] Confirm Loop shape defaults to Off, survives import/copy, and Prefer retains
      every mandatory point while showing exact non-null geometry metrics.
- [ ] Generate the Marly request and confirm null nature metrics never render as zero.
- [ ] Confirm null loop-geometry metrics say “not evaluated,” never numeric zero.
- [ ] Toggle the nature underlay and confirm repetition/backtracking stay above it.
- [ ] Confirm browser network requests contain no raw nature-polygon download.
- [ ] Confirm Places defaults to primary scenic and verified water; unknown, broad,
      restricted, private, and non-potable options remain off.
- [ ] Pan between Marly and Paris; confirm one bounded request after movement,
      clusters, individual markers, collision-aware labels, and truncation status.
- [ ] Inspect viewpoint, verified-water, unknown-water, restricted/private, and
      non-potable popups; confirm careful mapped-data wording and safe text display.
- [ ] Confirm only eligible public/restricted scenic and verified-water popups show
      “Prefer in Auto Tour”; private/non-potable popups do not.
- [ ] Generate the Marly Auto Tour; compare the retained no-POI control, accepted
      itinerary, reward breakdown, rejection reasons, and strict budget accounting.
- [ ] Confirm visited POIs are stronger than nearby POIs and the verified-water
      mascot pin remains visible when selected.
- [ ] Select and filter a place; confirm its highlight survives a returned viewport
      refresh and clears without changing any required route point.
- [ ] Import a multi-segment GPX; confirm no line joins segment breaks.
- [ ] Download selected GPX and confirm no second generation request occurs.
- [ ] Confirm the downloaded GPX has one track/segment and no nature extensions.
- [ ] Check the downloaded track in gpx.studio.
- [ ] Check 1440, 1024, 768, and 390 px layouts, keyboard navigation, image aspect
      ratios, and the browser console.
---

<p align="center">
  <img
    src="assets/brand/sugarglider-flying-map.png"
    alt="Sugarglider exploring a trail map"
    width="360"
  />
</p>
