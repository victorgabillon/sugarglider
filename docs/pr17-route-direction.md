# PR17 route direction and graph-valid reversal

PR17 makes the order of travel explicit without adding navigation claims. Every
`PlanCandidate` publishes immutable `kind`, `topology`, and `traversal` metadata. A
traversal contains one start anchor, an end anchor only for open routes, and ordered
deliberate interior visits with semantic and actual routed coordinates, route progress,
constraint strength, and final outcome. Dropped stops, incidental nearby POIs, and
temporary search points are excluded.

## Direction analysis

Open routes are `start_to_end`; their returned geometry order is authoritative. Loop
orientation uses the shared local metric projection and deterministic signed area. A
simple, sufficiently closed loop with coherent non-degenerate area is `clockwise` or
`counterclockwise`. Important self-crossing, more than 50 m of closure error, small or
cancelling area, or otherwise degenerate geometry is `complex_loop`. Map arrows remain
authoritative for all classifications.

The browser renders one MapLibre line-symbol layer for the selected generated
candidate. Its small local canvas arrow follows map rotation and line order, uses
zoom-sensitive spacing, and is never duplicated into one DOM marker per coordinate.
The setting defaults on and survives candidate and planning-mode changes. It is not
shown for a local GPX or when no generated candidate is selected. These arrows show
track traversal only; they are not instructions or guarantees about legality, safety,
opening, or current conditions.

## Reverse API and transformed intent

`POST /v2/plans/reverse` has a strict schema-version-1 body containing
`source_request`, `candidate`, and a `candidate_count` from one to three (default one).
The response identifies the source candidate and returns both `transformed_request`
and an ordinary canonical `PlanResult`.

The server validates candidate kind, topology, public and route profile, signature,
endpoints, geometry, direction, traversal anchors, exact constraints, and reached or
approximated routed targets. It does not trust posted scores, analysis, ranks, roles,
compromise text, eligibility, or diagnostics. Invalid source data uses a stable safe
422 response; bounded opposite-route exhaustion uses 503. Neither exposes upstream
payloads or tracebacks.

For an open route, start and end swap and ordered interior intent reverses. For a loop,
the exact start stays fixed while interior intent reverses. Fixed Waypoint Route order
is reversed directly; optimized order uses the selected candidate's actual traversal
order. Auto Tour hard waypoints and requested-stop intent reverse. Its loop direction
preference is inverted; `any` becomes the opposite known selected orientation and
stays `any` for a complex loop. IDs, names, strengths, profile, objective, preferences,
seed, and other canonical settings are retained except the explicit reversal and
requested candidate count.

## Bounded graph routing

The reverse planner creates exactly one `PlanningSearchContext`. It uses the PR16
resolver for approach and best-effort constraints and the cached routing gateway for
all complete routes. Cache identity contains public/backend profile, ordered
coordinates, pass-through behavior, reverse operation/variant options, and profile
snap prevention. The typed `reverse` phase has a hard three-call cap; approach probes
retain their separate exact count. Cache and budget diagnostics remain authoritative.

A sparse loop with fewer than three deliberate interior anchors samples stable routed
progress between 12.5% and 87.5%. At most eight sufficiently spaced private shape hints
preserve the broad loop. A bounded fallback reduces or removes them after route
failure. Shape hints cannot weaken exact constraints and never appear in traversal,
stop outcomes, canonical JSON, or GPX.

Every routed result becomes a shared `CandidateDraft`. The original mode scorer,
shared evaluator, validation, analysis, and portfolio rebuild the public candidate.
Exact constraints remain exact and can fail with `exact_waypoint_not_reached`. Soft
stops are resolved and measured again, so reached, approximated, dropped, warnings,
and compromises may differ from the source. A meaningful distance change adds a safe
directional-access warning.

## Browser, JSON, and GPX behavior

The accessible reverse action is available only for a selected generated candidate.
It displays `Reversing route…`, disables competing actions, and retains the source
route if the request fails. Success replaces the result, selects the recommended
candidate, applies the returned transformed canonical request to controls and markers,
and refreshes arrows, outcome summaries, compromises, and visualization caches. No
frontend code reverses geometry locally.

Canonical request export after success therefore preserves swapped endpoints,
reversed constraint intent, strengths, profile, distance objective, and preferences;
internal hints and generated geometry are absent. GPX serializes the already returned
candidate, so trackpoint order follows the displayed reversal, loops retain the same
start/closure, and output remains one track, one segment, no route element, and no
proprietary extensions. Reversing twice restores semantic direction and order but is
not guaranteed to recreate identical geometry because one-way access and snapping can
legitimately select different edges.

Destination clusters and Domaine de Marly special grouping remain PR18 work.
