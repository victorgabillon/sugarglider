<p align="center">
  <img src="assets/brand/sugarglider-banner.png" alt="Sugarglider" width="100%" />
</p>

# Sugarglider

Sugarglider generates deterministic walking, trail-running, and cycling plans on real
OpenStreetMap paths through a self-hosted GraphHopper 11 instance. It supports
preference-driven Auto Tours and routes through explicit waypoints. Every published
candidate contains routed geometry, explainable structural and activity-specific
analysis, a score, selected and dropped stops, and bounded-search diagnostics.

This repository deliberately supports one public planning schema: version 1. Pre-PR14
request JSON is not accepted at runtime.

## Setup

Requirements are Python 3.13, `uv`, Docker Compose, and enough disk for the selected
OSM extract and GraphHopper graph.

```sh
uv sync
make check
cp .env.example .env
docker compose up --build
```

The browser and API are then available at `http://localhost:8000`. GraphHopper is an
external process; domain and planning code only use it through the typed routing
adapter.

## Canonical plan API

The planning surface is:

- `POST /v2/plans/generate`
- `POST /v2/plans/gpx`

The GPX operation accepts an already returned `PlanCandidate`. It never reruns search
or routing and emits exactly one GPX track with one segment. Selected stops are GPX
waypoints; dropped stops are never exported.

Liveness, readiness, browser configuration, local-index status/search, and backend
route visualization remain separate:

- `GET /health`
- `GET /ready`
- `GET /v2/routing-profiles`
- `GET /v1/ui/config`
- `GET /v1/nature/status`
- `GET /v1/pois/status`
- `POST /v1/pois/search`
- `POST /v2/plans/visualization`

All canonical public models are immutable and reject unknown fields. Requests use an
explicit discriminator (`auto_tour` or `waypoint_route`) and explicit topology (`loop`
or `point_to_point`). A loop requires `start` and omits `end`; a point-to-point plan
requires distinct `start` and `end` coordinates. Services never infer either endpoint.

### Auto Tour loop

```json
{
  "schema_version": 1,
  "kind": "auto_tour",
  "name": "Marly nature loop",
  "topology": "loop",
  "start": {"lat": 48.867778, "lon": 2.051111, "name": "Saint-Nom station"},
  "end": null,
  "routing_profile": "hike",
  "candidate_count": 3,
  "seed": 42,
  "distance_objective": {
    "target_m": 41000,
    "tolerance_m": 2000,
    "maximum_m": null,
    "priority": "flexible"
  },
  "preferences": {
    "scenic": "prefer",
    "drinking_water": "prefer",
    "nature": "prefer",
    "loop_geometry": "prefer",
    "direction": "any",
    "path_selection": "low_overlap"
  },
  "hard_waypoints": [],
  "requested_stops": [
    {
      "id": "croix-saint-michel",
      "name": "Croix Saint-Michel",
      "semantic_coordinate": {"lat": 48.8715, "lon": 2.043},
      "importance": "must_visit",
      "constraint_strength": "approach",
      "osm_reference": null,
      "access_search_radius_m": 500,
      "maximum_best_effort_distance_m": null,
      "approach_override": null
    }
  ],
  "preferred_discovered_poi_ids": [],
  "free_poi_spur_physical_m": 200
}
```

`access_search_radius_m` finds meaningful public or unknown-access approaches. It is
not an arrival radius. Final arrival tolerance comes from the resolved approach and a
selected stop reports both that approach and its measured route distance.

For point-to-point Auto Tours, set `topology` to `point_to_point` and provide `end`.
The complete checked-in Bastille-to-Marly example is
[`examples/marly/bastille-to-marly-22-places-auto-tour.json`](examples/marly/bastille-to-marly-22-places-auto-tour.json).

### Waypoint route

```json
{
  "schema_version": 1,
  "kind": "waypoint_route",
  "name": "Optimized waypoint loop",
  "topology": "loop",
  "start": {"lat": 48.871389, "lon": 2.096667},
  "end": null,
  "routing_profile": "hike",
  "candidate_count": 3,
  "seed": 42,
  "distance_objective": {
    "target_m": 41000,
    "tolerance_m": 2000,
    "maximum_m": null,
    "priority": "flexible"
  },
  "preferences": {
    "nature": "prefer",
    "loop_geometry": "prefer",
    "path_selection": "low_overlap"
  },
  "waypoints": [
    {
      "id": "machine-de-marly",
      "name": "Machine de Marly",
      "coordinate": {"lat": 48.871454, "lon": 2.124421},
      "constraint_strength": "exact"
    },
    {
      "id": "aqueduc",
      "name": "Aqueduc de Louveciennes",
      "coordinate": {"lat": 48.86156, "lon": 2.10833},
      "constraint_strength": "best_effort",
      "access_search_radius_m": 750,
      "maximum_best_effort_distance_m": 750
    }
  ],
  "waypoint_order": "optimize"
}
```

Optimization always fixes the start. It reorders only interior waypoints for a
point-to-point plan and fixes both endpoints. It uses bounded deterministic heuristics,
never an exponential exact TSP, and never drops an exact waypoint.

Every interior point has an explicit strength. `exact` preserves the 300 m hard snap
contract and may reject the plan. `approach` routes to a safe mapped/user/profile
approach or drops the place with a reason. `best_effort` additionally accepts a
bounded profile-compatible fallback and reports the remaining semantic distance as
an approximation; it never claims the original place was reached.

## Distance and profiles

`distance_objective` is the only distance objective:

- `target_m` and `tolerance_m` are required;
- `maximum_m: null` means no hard maximum for flexible and balanced plans;
- balanced target/tolerance misses affect ranking but do not reject a route;
- strict plans require a maximum and make both tolerance and maximum hard;
- strict maximums must contain the complete target tolerance.

Every request must select exactly one public routing profile: `hike`, `trail_run`,
`city_bike`, `gravel_bike`, `mountain_bike`, or `road_bike`. Backend names are not API
values and aliases are rejected. The immutable routing registry owns backend mapping,
activity kind, requested path details, snap preventions, public labels, capabilities,
and metric ordering. `GET /v2/routing-profiles` returns that public catalog in stable
order with safe runtime availability; packaged readiness requires all six profiles.

GraphHopper still has elevation disabled, so every profile truthfully reports
`elevation_aware: false`. Profiles are preferences over mapped OSM data, not guarantees
of safety, legality, current opening, surface condition, or rideability. Rebuild the
graph after profile, encoded-value, custom-model, or GraphHopper-version changes:

```sh
make rebuild-graph
```

The old graph is moved to a timestamped backup under `data/graph-cache-backups`; it is
not silently reused or deleted. Six ready-to-send requests are in
[`examples/profiles`](examples/profiles). See
[`docs/pr15-routing-profiles.md`](docs/pr15-routing-profiles.md) for mapping, model
intent, acceptance commands, and resource reporting.

## Results and explainability

`PlanResult` has one shape for both modes: schema version, kind, topology, effective
endpoints, candidates, and search diagnostics. A candidate has a stable ID, rank,
multiple roles, route, score, reached/approximated/dropped stops, compromises, and
diagnostics. Portfolio roles
are `harmonious`, `maximum_requested_coverage`, `smooth_low_detour`, and
`distance_focused`.

Each `PlanCompromise` has a stable code and severity plus the affected identity,
semantic and routed coordinates where relevant, measured distance, normal tolerance,
configured maximum, profile, reason, and suggestion. Flexible distance misses are
warnings. Exact failures remain structured HTTP 422 errors and are never silently
retried with weaker semantics. The browser renders reached (green), approximated
(amber), and dropped outcomes, focuses map connectors, and offers explicit edits that
require regeneration.

The strict Marly regression remains
[`all-pois-generation-request.json`](examples/marly/all-pois-generation-request.json).
Its sightseeing counterpart is
[`all-pois-best-effort-generation-request.json`](examples/marly/all-pois-best-effort-generation-request.json);
it keeps the exact start and flexible 41 km objective while making every scenic
constraint explicit and bounded.

GraphHopper's route distance is authoritative. Geometry-edge distances are normalized
to it before analysis. Unknown path-detail or local-nature coverage stays visibly
unknown. Repetition uses exact edge IDs; immediate backtracking remains a separate
metric. Low-overlap alternatives never substitute straight-line geometry.

The browser asks the backend for the same visualization projection used by route
analysis. It does not duplicate repetition, backtracking, routing, nature, or scoring
semantics in JavaScript. Browser GPX inspection remains local-only and preserves track
segment breaks.

Final candidates also expose deterministic edge-based out-and-back excursion
diagnostics. The browser identifies branch, turnaround, and rejoin context and lists
deliberate stops inside each substantial spur. Detection is descriptive only: it does
not claim an alternative exit exists or change ranking. See
[`docs/pr19-spur-diagnostics.md`](docs/pr19-spur-diagnostics.md).

## Migrating old JSON

Runtime import of older request shapes has been removed. The browser reports:

```text
Unsupported legacy Sugarglider request.
Convert it with scripts/migrate_plan_json.py.
```

Convert offline with:

```sh
uv run python scripts/migrate_plan_json.py old-request.json plan-v1.json
```

Use `--overwrite` only when replacement is intentional. The utility writes stable,
Unicode-preserving JSON, prints each inference, refuses ambiguous topology/endpoints,
and is idempotent for canonical files. Every checked-in example is already canonical.

## Local nature and POI indexes

Nature and POI data are generated from the configured local OSM PBF. Runtime requests
never call Overpass or another hosted GIS service. Build the ignored regional indexes:

```sh
make nature-index
make poi-index
```

The default outputs are:

```text
data/nature/ile-de-france-nature-index.json.gz
data/pois/ile-de-france-poi-index.json.gz
```

They are loaded once during application startup. Missing or invalid indexes disable the
associated preference and remain explicit in status and diagnostics. The map continues
to use configured raster tiles with visible attribution; Sugarglider does not prefetch,
bulk-download, cache, or offer offline tiles.

## Route direction and reversal

Generated candidates carry a canonical traversal record. The selected route displays
repeated map-aligned arrows and an open-route `Start → End` or loop orientation label.
`Complex loop` means that crossings, incomplete closure, or ambiguous signed area make
a clockwise claim misleading; the arrows still show the actual geometry order. The
arrow toggle is visual only, and arrows describe traversal order rather than legal
turn-by-turn navigation.

`POST /v2/plans/reverse` accepts the canonical source request and one published
candidate. The server swaps open endpoints or reverses loop intent, preserves the
public profile and constraint strengths, then reroutes through the shared cached and
budgeted GraphHopper boundary. Exact constraints remain hard. Approach and best-effort
stops are resolved again, so reached, approximated, and dropped outcomes can change.
Sparse loops use a bounded set of private shape hints sampled from routed geometry;
those hints never become public stops or GPX waypoints.

Reversal is not a client-side coordinate-array operation. Directional access and
snapping may produce different roads and distance, and reversing twice is not an exact
geometry undo. Canonical JSON after reversal contains the transformed request; GPX
trackpoints preserve the displayed graph-valid traversal. See
[`docs/pr17-route-direction.md`](docs/pr17-route-direction.md).

## Architecture

Dependency direction is enforced as:

```text
domain / analysis / routing / pois
                |
                v
             planning
                |
                v
          api / gpx / web
```

The canonical planning package owns models, results, typed budgets, shared candidate
drafts, profile-quality policy, final evaluation, portfolio construction, and mode-specific
producers. Each generation request creates one `PlanningSearchContext`; its cached
routing gateway is the only component that reserves route-call budget. Cache
diagnostics separately report lookups, hits, misses, successful/failed entries,
backend calls, and pre-backend budget rejections.

Waypoint Route consumes `WaypointPlanRequest` directly. Its service only orchestrates
endpoint-fixed controls, bounded deterministic ordering proposals, gateway routing,
shared draft evaluation, and portfolio publication. There is no runtime planning
adapter and no request conversion to the deleted generation or tours packages. The
cache identity includes public and resolved backend profile identity plus routing
options, preventing cross-profile reuse.

Target-distance proposals remain graph-derived: loops use routed round-trip geometry,
while point-to-point plans use routed alternative-leg geometry without closing or
cutting the route. Low-overlap refinement composes continuous GraphHopper legs through
the same request cache and typed `alternative_leg` budget. Exact endpoints and
waypoints are checked against backend snaps before shared final evaluation.

Auto Tour is likewise native and modular. Its request-scoped service coordinates
loop/open controls, routed skeletons, requested-stop ordering and subset search,
route-aware approaches, discovered POIs, through-route continuation, excursions,
repairs, and internal search-quality selection in focused modules. No Auto Tour
module calls the backend directly or owns a route cache/call counter. Retained routed
paths cross the shared `CandidateDraft` seam; `CandidateEvaluator` performs final
nature/loop enrichment once, invokes the Auto Tour scorer, validates safety and stop
arrivals, and constructs the unranked canonical candidate. Only the shared portfolio
assigns public roles and ranks.

The focused direction package analyzes final geometry, builds public traversal anchors
inside shared evaluation, validates reverse source payloads, transforms canonical
intent, and performs a bounded reverse search. It owns neither a routing cache nor a
backend call counter; the ordinary planning gateway accounts `approach` and `reverse`
phases and the ordinary evaluator, scorers, and portfolio reconstruct every result.

The offline `sugarglider-migrate-plan` command is included in wheels. It is the only
legacy-request conversion surface; runtime HTTP planning accepts canonical schema
version 1 only. Candidate/result identity, route signatures, diagnostics, and GPX
metadata preserve the selected public profile without exposing backend profile names.

Domain code does not import FastAPI. Routing does not import API code, POIs do not
import planning, and generic analysis does not import planning-service models.

## Validation

Run the service-independent checks:

```sh
uv run ruff format .
uv run ruff check .
uv run mypy src tests
uv run pytest -m "not integration"
docker compose config
git diff --check
```

With Docker services healthy, run live integration tests:

```sh
uv run pytest -m integration
```

Unit tests require no Docker, network, map data, or external service. Generated map
indexes, PBF extracts, GraphHopper caches, GPX files, screenshots, and secrets must not
be committed.

The checked-in behavioral thresholds and latest local GraphHopper measurements are in
[`docs/pr14-acceptance.md`](docs/pr14-acceptance.md).
