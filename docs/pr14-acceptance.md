# PR14 acceptance envelope

These thresholds protect semantic behavior while allowing bounded deterministic search
to choose a different graph-valid route after portfolio and cache cleanup.

| Scenario | Required acceptance |
|---|---|
| Marly Auto Tour loop | 22 requested decisions; canonical harmonious coverage no lower than the producer harmonious candidate unless an explicit canonical invariant rejects it |
| Bastille to Marly Auto Tour | 22 requested decisions; canonical harmonious coverage no lower than the producer harmonious candidate unless an explicit canonical invariant rejects it |
| Waypoint loop | every interior waypoint within 300 m of routed geometry; start/end fidelity within 300 m; closed within 300 m |
| Waypoint point-to-point | zero or more interior waypoints, each within 300 m; fixed start/end each within 300 m; open geometry |

For every mode and scenario:

- GraphHopper geometry is the only route geometry;
- exact hard waypoints use the server-controlled 300 m bounded snap threshold;
- inaccessible semantic objectives are requested stops with explicit selected/dropped
  decisions, not weakened hard-waypoint constraints;
- a selected stop is within its resolved approach tolerance;
- every requested stop is selected or dropped exactly once;
- a non-null maximum distance is a hard safety ceiling;
- generated GPX has one track and one segment and no GPX route;
- candidate IDs, ranks, decisions and diagnostics are deterministic for the fixed
  request, seed, settings and graph.

## Local GraphHopper snapshot

Measured on 2026-07-20 against the existing local Île-de-France GraphHopper graph and
POI index:

| Fixture | Lane | Runtime | Distance | Target error | Requested selected/dropped | Backtracking | Repetition | Maximum selected arrival | Endpoint error start/end |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `auto-tour-request.json` | canonical | 2026-07-20 live | 31,082.4 m | 9,917.6 m | 1 / 21 | 0.0 m | 2.6 m | 1.2 m | previously measured 1.6 / 1.6 m |
| `bastille-to-marly-22-places-auto-tour.json` | producer | same producer result | 48,696.2 m | 3,696.2 m | 12 / 10 | 2,761.1 m | 2,761.1 m | 22.2 m | not separately measured |
| `bastille-to-marly-22-places-auto-tour.json` | canonical | 2026-07-20 live | 48,696.2 m | 3,696.2 m | 12 / 10 | 2,761.1 m | 2,761.1 m | 22.2 m | previously measured 2.9 / 1.7 m |

The earlier `0 / 22` open-route publication was traced to canonical code treating the
producer's quality-promotion gate as a safety flag. With actual hard safety used for
eligibility, the canonical harmonious route again selects 12 requested stops. Every
canonical rejection appears verbatim in search warnings.

## Paired cleanup overhead

The old producer and canonical publication path were run sequentially on the same warm
graph. Marly measured 13.026 s versus 14.099 s (`+8.24%`); Bastille-to-Marly measured
16.425 s versus 16.362 s (`-0.38%`). Both are inside the allowed 10% runtime envelope.
Candidate hashes need not match, but publication must not change the recommendation
solely through generic portfolio sorting.

The final local POI benchmark loaded 7,171 features in 0.307 s with 94.9 MiB peak RSS.
Median query latency was 1.352 ms for Marly (393 matches) and 4.385 ms for central
Paris (2,081 matches, bounded to 1,000 returned). Reproduce it with
`uv run python scripts/benchmark_poi_index.py`.

## Native Waypoint live snapshot

Measured on 2026-07-20 against the same local GraphHopper graph after native parity:

| Scenario | Runtime | Backend calls | Cache hits | Proposals | Drafts | Published | Recommended distance/error |
|---|---:|---:|---:|---:|---:|---:|---:|
| Direct Bastille–Marly, no interior points | 0.051 s | 1 | 0 | 0 | 1 | 1 | 23,877.3 m / 122.7 m |
| Open fixed, one interior point | 0.043 s | 1 | 0 | 0 | 1 | 1 | 24,923.4 m / 1,076.6 m |
| Open optimized, two interior points | 0.079 s | 2 | 0 | 1 | 2 | 2 | 25,759.5 m / 240.5 m |
| Optimized Marly loop with target detours | 1.546 s | 28 | 0 | 18 | 19 | 3 | 41,528.1 m / 528.1 m |
| Open low-overlap, one interior point | 1.177 s | 3 | 0 | 8 | 9 | 3 | 25,013.8 m / 986.2 m |

Every measured GPX export contained one track, one segment, and zero GPX routes.
The direct request reported exactly one control budget use, one miss, one successful
entry, and one backend call. Live canonical Waypoint loop and open integration tests
passed. The Bastille–Marly Auto Tour remains at its documented 2,761.1 m backtracking
and repetition snapshot (5.67%).

## Native Auto Tour completion snapshot

Measured after the pass-B module split against the same warm local graph and POI index:

| Fixture | Before | After | Change | Backend calls / cache hits | Distance | Requested selected/dropped | Backtracking / repetition |
|---|---:|---:|---:|---:|---:|---:|---:|
| Marly loop | 14.099 s | 15.502 s | +9.95% | 98 / 517 | 30,275.3 m | 12 / 10 | 1,150.9 / 1,242.0 m |
| Bastille–Marly open | 16.362 s | 17.380 s | +6.22% | 62 / 224 | 48,696.2 m | 12 / 10 | 2,761.1 / 2,761.1 m |
| Direct Waypoint open | 0.051 s | 0.049 s | -3.92% | 1 / 0 | 23,877.3 m | n/a | unchanged |
| Optimized Waypoint loop | 1.546 s | 1.478 s | -4.40% | 28 / 0 | 41,528.1 m | n/a | unchanged |

The Marly recommendation now covers 12 requested stops instead of 1 while remaining
below the accepted 5% backtracking and repetition gates. Bastille–Marly preserves its
12/10 decisions and exact route-quality snapshot. Cache invariants held in both runs:
Marly `615 = 517 + 98`, Bastille–Marly `286 = 224 + 62`; every miss was one backend
call and every cache entry was successful. Pre-backend budget rejection was reported
separately (12 and 2 respectively).

Final enrichment now runs once per shared evaluated candidate—three times for each
published Auto Tour portfolio—instead of on temporary search states. The exact old
nature-call count was not instrumented, so no fabricated numeric baseline is given.

The post-split POI benchmark loaded 7,171 features in 0.300 s with 94.7 MiB peak RSS.
Median Marly and central-Paris queries were 1.583 ms and 5.230 ms respectively. This is
slower than the earlier query sample but remains single-digit milliseconds; the POI
implementation did not change in pass B.

All seven canonical example documents were parsed and executed. Six produced valid
portfolios whose GPX contained one track, one segment, and no route. The strict
`all-pois-generation-request.json` Waypoint example deliberately produced no candidate:
at least one of its 22 mandatory coordinates failed the 300 m backend-snap contract,
and native Waypoint correctly refused to drop or replace it.
