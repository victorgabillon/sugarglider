# PR38 Local Waypoint Route core

PR38 introduces a debug-only planning core in the shared web layer, above PR34's
`local_route` v2 primitive. It does not duplicate the existing “Route ordered
planner points locally” diagnostic: it interprets canonical Waypoint Route intent,
constructs topology-aware orders, validates hard constraints, ranks graph-routed
candidates, and returns an immutable local result.

The existing `createLocalRoutingBridge()` and `native_bridge_transport.js` remain
the only path to Android Valhalla. PR33/34 still select one compatible regional
routing pack for **all** requested points. PR38 neither selects packs itself nor
changes Android/Kotlin, the native protocol, or pack formats. No packs are rebuilt.
Marly/Paris routing packs remain independent of PR36/37's PMTiles basemaps.

Normal server-backed Generate, Waypoint Route, and Auto Tour remain unchanged.
Release local routing stays disabled. This is **not** the production planner
switchover: there is no backend/network fallback, no cross-pack stitching, no
straight-line fallback or fabricated connector, and no GraphHopper parity claim.

## Supported canonical subset

The core accepts schema-version-1 `WaypointPlanRequest` objects with:

- `kind = waypoint_route`; a name; `loop` or `point_to_point` topology; named or
  unnamed finite WGS84 coordinates; one of the six public profile IDs;
- an exact start, plus a distinct exact end for point-to-point; loops omit end
  or set it to null and require at least one interior waypoint;
- up to **14 interior waypoints**, each with a unique identity and coordinate,
  a name, and `constraint_strength = exact` (the canonical default). Interiors
  cannot duplicate endpoints. Their original one-based indices are retained;
- `waypoint_order = fixed` or `optimize`, candidate count 1–5, and an integer seed
  representable exactly by JavaScript (`Number.isSafeInteger`, signed);
- a distance objective: target 1–200 km, tolerance 0.1–10 km, and the canonical
  priority/maximum bounds. Flexible tolerance is soft and requires null maximum
  in this first local subset. Balanced tolerance is soft, with an optional hard
  maximum. Strict tolerance and its required explicit maximum are hard; the
  maximum must contain the complete target tolerance;
- preferences explicitly set to `nature = off`, `path_selection = shortest`,
  and `loop_geometry = off`.

Unknown request/nested fields, invalid coordinates, duplicate identities,
unsupported profiles/aliases, and excess points fail explicitly. Canonical Python
supports 30 waypoints; PR38 does not: its two endpoint entries consume two of the
primitive's 16 point slots, including the repeated start in a loop.

`approach`, `best_effort`, non-null `approach_override`, and best-effort distance
bounds are rejected with stable local validation codes. They are never treated as
exact, silently approximated, or dropped. An exact waypoint's canonical access
search radius is validated/preserved but does not trigger approach discovery.
Nature preference, low-overlap path selection, and loop-geometry preference are
also explicitly rejected, not reported as honored. Flexible requests with an
explicit maximum are rejected as an unsupported local distance contract.

`shortest` here selects one native route per ordering proposal, without alternative
leg/detour exploration. It does not establish a globally shortest graph path:
experimental Valhalla costing is not equivalent to GraphHopper custom models.

## Fixed and bounded optimized ordering

Fixed order makes exactly one native call:

- point-to-point: start → interiors in input order → end;
- loop: start → interiors in input order → start.

Optimized order always proposes the original fixed control first, then a
nearest-neighbor interior order, reversed nearest/control orders, one best
geometric segment reversal, and seed-shuffled bounded segment reversals. Endpoints
never move. With 14 interiors, there are at most 91 reversal proposals to inspect;
at most 16 distinct orders enter routing. This is a bounded heuristic, not
factorial enumeration, exact TSP, or a claim of Python/server ordering parity.
Geometric distances are used only to propose orders, never as returned routes.

One request owns at most **16 local-route calls** (below PR35's 24-call ceiling).
Every attempted call, including a throw or explicit native failure, consumes one
slot before invocation. Calls are sequential; an order is never retried or weakened.
Regional unavailable/no-covering/incompatible and busy failures terminate search.
Nonterminal failures may leave other orders to evaluate under the same budget.

## Hard validation and ranking

Only successful, strictly parsed `local_route` replies from `valhalla-mobile` may
produce candidates. Validation requires:

- the exact requested public profile and a non-empty regional pack identity;
  all successful replies in one generation must keep the same pack;
- the primitive's finite WGS84 geometry with 2–20,000 vertices, positive distance
  no greater than the explicit **200 km** local result ceiling, and valid optional
  duration. This ceiling is a local resource limit, separate from soft tolerance;
- snapped-point count equal to the requested sequence, with geometry boundaries
  exactly matching the first/last native snaps;
- requested start, point-to-point end, and loop return-to-start snaps within
  **25 m**, following PR35's stricter **local** hard-endpoint contract;
- every exact interior snap within **300 m**, matching
  `planning/validation.py`'s `EXACT_WAYPOINT_FIDELITY_M`. The Python canonical
  endpoint constant remains 300 m and is not changed by this local contract;
- every native snap present as a geometry vertex in requested visit order.
  This follows PR34's continuous leg-joining contract: snaps are actual leg
  boundary vertices. Missing geometry evidence is rejected, never reconstructed;
- non-degenerate geometry; graph-derived loop boundary gap at most **25 m**,
  checked independently of each endpoint snap using a separate closure constant;
  point-to-point geometry must not collapse to a closed route. No synthetic
  closing segment is appended, and the actual loop gap is reported;
- the request's hard maximum and, for strict priority, target tolerance.

Exact failures retain waypoint identity, measured displacement, threshold, profile,
and a suggestion in bounded rejection details. A successful `reached` exact outcome
means the applicable 25 m endpoint or 300 m interior contract passed, not exact GPS
coincidence, a mapped POI arrival, legality, accessibility, or a real-world safety
guarantee.

Graph-valid candidates rank lexicographically by tolerance status, absolute
target-distance error, route distance, then deterministic candidate ID. Soft
tolerance misses remain visible warnings. IDs exclude native request IDs and
timings; identical intent and successful native responses produce identical results.

Byte-identical geometry is deduplicated after ranking; a loop's exact reversal
counts as the same geometry. This is only exact geometric distinctness, not an
edge/corridor-diversity or alternative-route guarantee. Fewer than requested
candidates are returned when the bounded search cannot supply distinct valid ones.

## Result, UI, and lifecycle

The deeply immutable local result contains the canonical request snapshot and
identity, topology, seed/profile, requested identities, actual waypoint order and
original indices, pack/engine identity, retained graph geometry, distance/duration,
requested/snapped points, exact outcomes, closure gap, construction/order identity,
target error/tolerance, candidate IDs/ranks, and the recommendation.

Diagnostics expose route-call count/budget, proposed/unattempted orders, rejection
counts and details, and `budget_exhausted` (all call slots consumed). Empty results
have an explicit status/code. Edge repetition, path/surface/access attributes,
nature score and POI quality remain unavailable, not invented.

The separate “Local Waypoint Route experiment” action lives inside the existing
debug Android Local routing experiment. It reads the **ordinary planner controls**
through `readLocalWaypointRouteRequest()` and `waypointPlanRequestSnapshot()`,
including the ordinary profile selector, not the older raw local-routing profile
selector. The getter reads controls without writing them and shares the pure
options reader and waypoint serialization with the existing server path. It does
not call `updateOptionsFromControls()` or `currentPlanRequest()`, assign `state.plan`,
or change points, cached intent, server results, selection, or Generate lifecycle.
The server path keeps its existing synchronization and canonicalization behavior.
Unsupported intent is preserved for explicit rejection, including open-route shape
preferences and non-null exact-point bounds. In debug Android only, native-only
profiles can appear in that ordinary selector labeled “local experiment only” when server profiles are
unavailable. This does not change backend availability or enable server Generate.

Retained candidates use a dedicated `local-waypoint-route-experiment-` MapLibre
prefix and shared local candidate drawing helpers. Clearing/rendering this
experiment does not remove server routes, Auto Tour layers, basemaps, or other
overlays. General planner clearing still clears the new experimental layers.

Duplicate starts share the current promise. A different or invalidated generation
cannot restart until the in-flight native promise drains. Monotonic generation and
UI epochs plus current-intent checks prevent stale completions from rendering or
launching further proposals. Editing/clearing the planner and pagehide invalidate
the experiment. Shared busy controls prevent overlap with other local debug actions.
There is no background service or automatic retry after an uncertain native outcome.

The offline shell precaches the new shared module. Its generation changes exactly
once from v21 to **v22**; release/native protocol behavior remains unchanged.

## Roadmap and validation

PR39's future offline places/access data may enable meaningful approach and
best-effort resolution; PR38 does not anticipate it with weak approximations.
PR40 remains a subsequent local-planning capability/evaluation step, not an
implemented parity claim. PR41 is the planned production-planner integration;
this debug result is groundwork, not a fabricated server `PlanResult` or an
automatic migration of normal planning to local execution.

Deterministic browser tests use fake local-route replies, with no device, Valhalla,
real packs, Docker, or routing backend. They exercise the canonical subset, exact
constraints, topology, order proposals, ranking, budget/failures, lifecycle, regional
identity, no fallback, and debug-only profile/UI integration. Python architecture
tests tie the local endpoint/closure limits to PR35 and interior/point/distance
limits to existing canonical/native contracts. Independent boundary regressions
cover start, point-to-point end, loop return and closure at 24.9/25.1 m, plus exact
interiors at 299.9/300.1 m. The closure fixture keeps both individual snaps within
25 m. Tests use the actual exported UI getter for rejected and supported requests,
checking all shared state identities/contents and control values remain unchanged.

## Fairphone physical acceptance

Fairphone 6 backend-isolated physical acceptance: PASS

The Fairphone 6 ran Sugarglider Debug
(`io.github.victorgabillon.sugarglider.debug`), kept awake/unlocked with Sugarglider
visible. PWA shell v22 was verified: the current PR38 code was loaded, the service
worker controlled the page, and loaded code and shell-cache copies matched the
workspace. Existing Marly and Paris packs were reused, not rebuilt or replaced.

During the actual local runs, FastAPI and GraphHopper were stopped and `adb reverse`
mappings were absent; the app reopened from its cached shell. Radios were preserved.
The hotspot remained enabled because it provides Internet to the development computer.

The ordinary planner controls and the new Local Waypoint Route debug action were
used, with exact waypoints, nature/loop geometry off, shortest path selection,
12 km target, 2 km tolerance, flexible priority, no maximum, three candidates and
seed 0, except for the deliberately unsupported preference below.

| Observed scenario | Result |
| --- | --- |
| Fixed local Waypoint Route | PASS; 7.677 km; exactly 1 native `local_route` call. |
| Optimized local Waypoint Route | PASS; 2 / 16 native calls; identical repeat preserved candidate IDs, order and recommendation. |
| `hike` loop | PASS; graph-derived closure gap 0 m. |
| `gravel_bike` loop | PASS; graph-derived closure gap 0 m. |
| Marly → Paris → Marly | PASS; native pack identities `marly-dev-v1` → `paris-dev-v1` → `marly-dev-v1`. |
| Cross-pack request | Explicit `no_covering_routing_pack`; no stitching or fallback. |
| Unsupported `low_overlap` preference | Explicit `unsupported_preference`; zero native route calls; normal planner state preserved. |

Endpoint and loop-return snaps and graph-derived closure satisfied the <=25 m
requirements; exact interior waypoint snaps satisfied the <=300 m requirement.
No hard constraint was weakened. Zero Sugarglider backend routing/generation
requests were observed during local Waypoint Route generation.

No production defect was demonstrated. This acceptance shows that PR38 local
Waypoint Route generation does not require the Sugarglider routing/generation
backend in the exercised cases.

This was not a radios-off acceptance, zero-network acceptance,
production/release acceptance, or GraphHopper parity demonstration.
