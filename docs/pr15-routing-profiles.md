# PR15 activity-aware routing profiles

PR15 adds six strict public profiles to both native planners. They use the same
request-scoped routing cache, typed budgets, candidate evaluation, portfolio, endpoint
and selected-stop validation, and clean GPX export as PR14.

## Public profiles and backend mapping

| Public ID | Activity | Internal GraphHopper profile | Routing intent |
|---|---|---|---|
| `trail_run` | running | `trail_run` | Runnable paths with steps, poor smoothness, technical hiking terrain, and major roads discouraged |
| `hike` | walking | `hike` | Trails, hiking networks, useful unpaved sections, and mapped nature |
| `city_bike` | cycling | `bike` | Cycleways, cycling networks, and smoother paved connections |
| `gravel_bike` | cycling | `gravel_bike` | Suitable gravel/compacted tracks with useful quiet connectors |
| `mountain_bike` | cycling | `mtb` | Off-road tracks and suitable trails while exposing technicality |
| `road_bike` | cycling | `racingbike` | Paved, smoother road cycling with rough terrain strongly discouraged |

Backend names are internal implementation details. They are not aliases and strict
request validation rejects them. Registry order is deterministic as shown above.
`GET /v2/routing-profiles` returns public labels, descriptions, activity/access kinds,
quality metrics, capabilities, availability, and safe warnings without filesystem paths
or upstream error text. `GET /ready` refreshes GraphHopper `/info` and succeeds only
when all six packaged profiles are advertised. `/health` remains a local liveness check.

## GraphHopper configuration

GraphHopper remains pinned to 11.0 with elevation disabled. Hike, bike, MTB, and racing
bike use their built-in models. Trail run composes the hike model with
`custom_models/trail_run.json`; gravel composes the bike model with
`custom_models/gravel_bike.json`. The overlays only multiply priority by values at or
below one. Each profile has an independent landmark preparation, avoiding unproven
cross-profile preparation reuse.

The trail-running overlay strongly penalizes steps, major roads, very poor smoothness,
high hiking ratings, and sand. The gravel overlay strongly penalizes pedestrian ways,
steps, major roads, very poor smoothness, high MTB ratings, and sand, while allowing
quiet paved connectors. These preferences do not turn missing OSM tags into positive
evidence.

Common, foot, and bicycle encoded values support profile-specific path details. The
adapter discovers available details through `/info`, caches fallback independently per
backend profile, and takes snap preventions from the registry. All production Auto Tour,
Waypoint, alternative-leg, isochrone, POI-approach, repair, and final route operations
pass the public profile explicitly.

## Cache and identity

The graph image records a SHA-256 import fingerprint over the GraphHopper version,
effective config, and custom models. Startup refuses an existing cache with a missing or
different fingerprint. Rebuild safely with:

```sh
make rebuild-graph
```

The target moves a non-empty existing graph to a timestamped directory under
`data/graph-cache-backups` before importing. It never deletes unrelated data.

Planning route-cache keys contain public and backend profile identity, operation,
coordinates, headings, seed, round-trip distance, alternative/isochrone settings,
pass-through, snap prevention, and relevant routing options. Candidate IDs, route
results, plan candidates/results, diagnostics, canonical JSON, and GPX metadata retain
the public profile. Cache accounting remains `lookup = hit + miss`, `entry = success +
failure`, and `backend call = miss`.

## Analysis, scoring, POIs, and GPX

Common analysis keeps authoritative GraphHopper distance, normalized geometry edges,
raw path-detail breakdowns, surface, major-road, repetition, immediate backtracking,
loop geometry, and nature. A discriminated activity union adds walking, running, or
cycling quality. Per-detail coverage and warnings keep missing data visibly unknown;
the browser renders unsupported metrics as “not evaluated.”

Each profile has one immutable quality policy defining deterministic rewards,
penalties, severe incompatibility gates, and metric order. Those components rank only
after graph/point/arrival validity, distance semantics, repetition, and immediate
backtracking; they cannot rescue an invalid candidate.

Requested and discovered POI approaches use the selected profile. Failed candidates
may report `profile_unreachable`, `profile_snap_too_far`, or
`no_profile_compatible_approach`. The local POI index is not proof of bicycle access;
the final GraphHopper route and strict route-to-approach arrival measurement remain
authoritative.

GPX remains exactly one track and one segment with selected approaches as standard
waypoints, dropped stops omitted, and no private extensions. Track name/type may expose
the public activity. Export serializes the returned candidate and never reruns routing.

## Frontend and examples

The accessible activity selector is populated from the catalog, groups running,
walking, and cycling, disables unavailable profiles, preserves selection across planner
modes, and invalidates old candidates when changed. Canonical import selects the exact
profile. Candidate cards and activity-specific diagnostics display it without copying
backend profile semantics into JavaScript. The layout remains the existing responsive
CSS application; no map or framework behavior changed.

Canonical examples for all profiles are in `examples/profiles`. Compare them against a
running canonical API, sequentially, with:

```sh
uv run python scripts/compare_routing_profiles.py
```

## Acceptance and resource measurements

Service-independent validation is quick and network-free:

```sh
make check
docker compose config --quiet
git diff --check
uv build
unzip -l dist/*.whl
```

A fresh graph import and six-profile route-quality experiment can exceed five minutes
and are deliberately separate from unit validation. Run and retain their output with:

```sh
time make rebuild-graph 2>&1 | tee /tmp/sugarglider-pr15-graph-import.log
```

Once `/ready` succeeds, inspect configuration and run live tests sequentially:

```sh
curl -fsS http://localhost:8989/info | python -m json.tool
curl -fsS http://localhost:8000/v2/routing-profiles | python -m json.tool
uv run pytest tests/integration/test_graphhopper_live.py -m integration -x
uv run python scripts/compare_routing_profiles.py
```

Record graph import wall time, `du -sh data/graph-cache`, container peak/steady memory
from `docker stats`, per-profile route and plan latencies, API startup/catalog latency,
and cache diagnostics. The JVM limit remains 4 GiB; increasing memory is not an
acceptance substitute. Marly should compare hike/trail-run/gravel/MTB, while
Bastille-to-Marly should compare all six and preserve the PR14 hiking coverage,
distance, repetition, backtracking, arrival, runtime, route-call, cache, and tampered-GPX
thresholds. At least one controlled or real case must distinguish hike/trail run,
city/road bike, and gravel/MTB.

## Limitations and next step

Profiles are preferences over mapped OSM data. They do not guarantee safety, legality,
current opening, water operation/quality, surface condition, or rideability. Surface,
smoothness, access, and ratings may be absent or stale; road-bike routing is not road
safety certification and MTB routing is not permission or suitability certification.
Profile availability only means the backend loaded a configuration, not that any
particular real-world route exists. Elevation, climbs, popularity, shared participants,
rendezvous, persistence, navigation, live location, and offline maps remain out of
scope. The stable public catalog and individual profile identity provide the intended
foundation for later shared-outing work.
