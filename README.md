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

The implemented PR1 and PR2 scope accepts ordered latitude/longitude anchors, asks
a self-hosted GraphHopper 11.0 instance to snap and route them along real
OpenStreetMap edges, analyzes the routed edges using GraphHopper path details, and
exports the geometry as one clean GPX 1.1 track.

## Current scope and architecture

```text
client -> FastAPI -> RouteService -> typed GraphHopper HTTP adapter
                    |       |              |
                    |       +-> analyzer   +-> GraphHopper 11 / OSM graph
                    +-> GPX writer
```

The public API uses named `lat` and `lon` fields. The adapter converts anchors to
GraphHopper's `[longitude, latitude]` JSON order and preserves that same GeoJSON
order in routed responses. The GPX writer then emits the final routed coordinates as
`lat` and `lon` trackpoint attributes. It never draws, interpolates, or falls back to
straight lines.

The analyzer uses standard-library haversine distances for every geometry edge and
normalizes them to GraphHopper's authoritative route distance. Raw path-detail
breakdowns remain available alongside explainable derived metrics. It does not
produce an arbitrary composite quality score.

The current implementation does not optimise anchor order, generate waypoints,
target a requested route length, score popularity, analyze nature areas, enable
elevation, map-match uploaded GPX files, or provide a frontend or database. The
Marly example is only an ordered-anchor routing integration example; it is not the
final desirable 41 km route.

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

## Map data and Docker startup

Download the Geofabrik Île-de-France PBF explicitly:

```sh
make download-osm
```

The script is idempotent, writes through a temporary file, and supports
`FORCE=1` and an `OSM_PBF_URL` override. PBF files and imported graph caches are
ignored by Git.

Start GraphHopper and the API:

```sh
make up
make logs
```

The first GraphHopper startup imports the PBF and creates the hiking graph and
landmark preparation under `data/graph-cache`; this can take several minutes and
substantial memory. Later starts reuse the bind-mounted cache. If the GraphHopper
configuration or PBF changes incompatibly, stop the stack and deliberately clear
the contents of `data/graph-cache` before rebuilding. Compose exposes GraphHopper
at `http://localhost:8989` and the API at `http://localhost:8000`.

## API

- `GET /health` checks only that the FastAPI process is alive.
- `GET /ready` checks GraphHopper `/info` and requires its `hike` profile.
- `POST /v1/routes` returns routed GeoJSON-order coordinates, summary metrics,
  snapped anchors, raw path details, and typed route analysis.
- `POST /v1/routes/gpx` computes the same route and returns a downloadable GPX
  containing exactly one track and one segment.

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
- `detail_breakdowns` reports explicit values and coverage for every returned path
  detail. Explicit null is a bucket; uncovered geometry is not invented as a value.

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

OpenStreetMap and routing engines can be incomplete or out of date. Generated
routes must still be checked against current local closures, land-access rules,
conditions, and on-the-ground signage before use.

## Current limitations and future work

Ordered anchors are mandatory and are visited as provided. Analysis describes the
already-routed result; it does not generate alternatives or decide which route is
best. Elevation is disabled, so GPX trackpoints contain no invented elevations or
timestamps, and GPX files contain no analysis extensions. Nature, popularity,
target-distance optimization, and a deliberately designed route-quality objective
remain future work. Future PRs can build those features while retaining the typed
routing adapter, normalized edge metrics, and single-track GPX boundary.

---

<p align="center">
  <img
    src="assets/brand/sugarglider-flying-map.png"
    alt="Sugarglider exploring a trail map"
    width="360"
  />
</p>
