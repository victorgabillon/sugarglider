# PR35 local Auto Tour core

PR35 adds a debug-only, loop-only local Auto Tour core in the shared web layer.
It orchestrates repeated calls to PR34's generic native `local_route` primitive;
Android continues to own Valhalla execution and the shared
`native_bridge_transport` remains the only WebView message transport. Normal
server-backed Generate and Auto Tour behavior is unchanged.
GraphHopper remains the reference backend.

## Strict request and deterministic search

The request contains exactly `start`, `target_distance_m`, `tolerance_m`,
`candidate_count`, `seed`, `profile`, and `direction_preference`. The start must
be a finite WGS84 coordinate outside the polar projection limit. Target distance
is 2–60 km, tolerance is 0.1–15 km and at most half the target, candidate count
is 1–3, seed is an unsigned 32-bit integer, direction is `any`, `clockwise`, or
`counterclockwise`, and profile is one of the six PR34 public identities. Unknown
fields and aliases are rejected.

The seed deterministically orders regular triangle, asymmetric-triangle, and
diamond families over eight headings and the permitted traversal directions.
Their control points are geometric proposals only. Every candidate returned to
the caller is the geometry from a successful Valhalla route through the ordered
controls and back to the exact requested start; a skeleton line is never
returned as route geometry.

Each skeleton is routed once. When its graph distance is outside tolerance, the
control offsets may receive one scale correction clamped to 0.70–1.30, followed
by at most one reroute. There is no convergence loop. One request owns a strict
maximum of **24 local-route calls**. Exhaustion returns the best valid candidates
already found, together with the call count, rejection counts, and
`budget_exhausted`; it never expands the budget or invents a route.

## Hard validity

A routed attempt is retained only when:

- the native result is a success and preserves the requested public profile;
- a non-empty regional pack identity is present and a corrected reroute keeps
  the same pack;
- snapped-point count equals ordered requested-point count;
- both routed start snaps are within the existing 25 m hard endpoint tolerance;
- each generated control snap is within the server Auto Tour's 300 m maximum;
- geometry contains only finite bounded WGS84 positions;
- the graph-derived first/last geometry closes within 25 m;
- distance is below the explicit request-derived hard ceiling, capped at 120 km.

Failure rejects that attempt with one explicit reason. No straight segment,
cross-pack join, point replacement, or backend/network retry is allowed.

## Geometry-only analysis and ranking

The browser uses the same local equirectangular projection radius as the Python
analysis. It derives closure gap, signed area, signed-area compactness, angular
monotonicity, eight-sector balance, maximum radius, gross immediate-reversal
share, and routed direction. Crossing count and outbound/return proximity are
bounded **sampled geometric approximations** (at most 256 and 96 samples), not
graph-edge facts. A shared JSON golden fixture checks closure, non-crossing
compactness, angular coherence, crossings, and outbound/return proximity against
the existing Python loop-geometry analyzer.

All graph-valid candidates use one deterministic lexicographic order:

1. within target tolerance;
2. no severe sampled out-and-back indication;
3. non-degenerate geometry;
4. fewer sampled crossings;
5. requested direction agreement;
6. lower geometry-only penalty;
7. lower target-distance error;
8. deterministic candidate ID.

Hard validity therefore always precedes soft preferences. Geometry is resampled
to a bounded canonical signature for deterministic candidate IDs and a
direction-insensitive mean-distance diversity check. A near-duplicate may be
replaced by a better-ranked representative, but it cannot occupy another
portfolio slot. Fewer than the requested candidates are returned when the
bounded search cannot demonstrate sufficient geometric diversity.

## Result and unavailable evidence

The structured result contains request identity and seed, profile, recommended
pack, target and tolerance, ranked candidates, recommended ID, graph geometry,
distance, duration, ordered requested and snapped points, construction/skeleton
identity, target error, available geometry metrics, route-call accounting,
rejection counts, latency, budget status, and warnings. It exposes no filesystem
path.

Exact edge repetition remains unavailable. Edge/OSM way identity, exact
immediate backtracking, surface, road/use class, path access, hiking/MTB
difficulty, nature scoring, POI insertion, isochrones, GraphHopper `round_trip`,
alternative-route parity, corridor penalties, and `trace_attributes` are neither
inferred nor populated. Sampled proximity is not presented in an exact
repetition field. Equal or different geometry is not a GraphHopper quality or
profile-parity result.

Point-to-point local Auto Tour is not implemented. The strict model has no end
coordinate and never applies loop semantics to a point-to-point request. No
development pack is rebuilt or changed by PR35.

## Debug UI and lifecycle

The existing debug Android local-routing panel adds a separate “Local Auto Tour
experiment” surface with profile, target, tolerance, seed, candidate count,
direction, a fixed 12 km Marly fixture, and first-planner-point generation. It
draws every retained graph route and emphasizes the recommendation. Diagnostics
state the profile, pack, errors, construction IDs, sampled metrics, route calls,
latency, and unavailable exact repetition.

One generation is active at a time. Duplicate starts share its in-flight
promise, native route calls remain sequential, invalidation owns a monotonic
epoch, and a stale completion cannot render. There is no background service.

## Physical acceptance

Physical acceptance: **PASS on Fairphone 6**.

PR35 does not change Android/Kotlin routing, the native bridge, or routing-pack
contents. The unchanged PR34 v2 Marly and Paris packs remained installed. For
the PR35 acceptance, FastAPI and GraphHopper were stopped, `adb reverse` was
removed, and the debug app was relaunched from the cached v19 shell. The phone
still had Internet access for tethering, so this is specifically a
backend-isolated PR35 acceptance rather than a new radio-off full-offline claim.
The underlying native routing and pack layer had already passed airplane-mode,
Wi-Fi-off physical acceptance in PR34.

The fixed Marly `hike` Auto Tour with seed 35 retained two graph-routed loops,
recommended `local-auto-b4fd1cae`, used pack `marly-dev-v1`, and consumed 6/24
route calls. The first run took 10933 ms. Repeating the same seed produced the
same recommendation and identical retained candidate summaries in 2256 ms.
Seed 36 produced a different recommendation, `local-auto-7982d8e3`, including
a 12.48 km loop for the 12 km target, using 7/24 route calls in 2302 ms.

The fixed Marly `trail_run` run also retained two candidates. Its recommendation,
`local-auto-8ea898f8`, was 12.15 km for the 12 km target and used 8/24 route
calls in 2395 ms.

The fixed Marly smoke start is pedestrian-oriented. Bicycle profiles exercised
against that same fixed start were rejected explicitly, predominantly with
`hard_start_snap_too_far`; the hard start constraint was not weakened to make
the fixture pass. Bicycle acceptance therefore used the normal planner path
instead: a real hard start at `48.9210, 2.0870`, supplied through the existing
planner controls, followed by the normal “Generate local Auto Tour from first
planner point” action. `gravel_bike` retained two candidates on
`marly-dev-v1`; the recommendation `local-auto-07ea94cb` was 11.66 km for the
12 km target and the run consumed 15/24 route calls in 12507 ms.

No separate Paris pack-switch run was repeated for PR35 because this PR changes
neither routing-pack selection nor native pack lifecycle; those behaviors were
already physically exercised in PR33 and PR34. PR35 acceptance instead targets
the new bounded Auto Tour orchestration, deterministic generation, hard
validation, profile propagation, candidate ranking, and operation without a
reachable Sugarglider backend.
