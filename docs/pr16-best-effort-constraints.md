# PR16 best-effort constraints and explicit compromises

PR16 keeps canonical schema version 1 while making every interior constraint's
meaning explicit. Start and end remain exact. `ExactWaypoint` identifies Auto Tour
hard points, and `RouteWaypoint` identifies each Waypoint Route interior point.
Ordinary `RequestedStop` values default to `approach`; sightseeing imports can opt
into `best_effort` with a bounded maximum distance.

## Constraint semantics

- `exact` requires GraphHopper to snap within the existing 300 m hard threshold. A
  failure rejects publication and returns `exact_waypoint_not_reached` with safe
  identity, distance, threshold, profile, and suggestion fields.
- `approach` uses a mapped approach, a valid user override, or strict profile snap.
  If no safe compatible approach exists, the place is dropped and planning continues.
- `best_effort` uses the same candidates and can retain the nearest bounded
  profile-routeable target. The result is `approximated` when the semantic place
  remains outside its normal 25 m arrival tolerance.

Private, restricted, `access=no`, and locked approaches are never used. Unknown
access is retained only with an explicit warning. GraphHopper establishes profile
reachability, not legality, opening, current condition, or real-world safety.

`planning/constraints/resolver.py` owns local semantic/mapped resolution and bounded
profile probing. Both planning modes use that module. All probes use the request's
existing `CachedRoutingGateway`, `SearchPhase.APPROACH`, cache identity, and strict
budget; there is no resolver cache or route counter.

## Outcomes and compromises

Published candidates separate `reached_stops`, `approximated_stops`, and
`dropped_stops`. `PlanCompromise` records a stable code and severity, constraint
identity, semantic/routed coordinates, distance, tolerance, configured maximum,
reason, public profile, and suggestion. Exact failure is an API error rather than a
compromise.

The shared evaluator validates geometry, endpoints, exact waypoints, reached and
approximated routed targets, enriches analysis once, attaches distance warnings,
scores, and determines eligibility. Ranking keeps graph/exact/safety validity first,
then requested coverage, fewer/smaller approximations, fewer high-priority drops,
distance semantics, repetition/backtracking, quality/nature, and stable identity.

Flexible plans never reject solely for target or tolerance and `maximum_m: null`
means no hard maximum. Balanced plans rank target/tolerance but only reject an
explicit maximum. Strict plans require an explicit maximum and keep both tolerance
and maximum hard.

## Browser, JSON, and GPX

The browser displays a prominent reached/approximated/dropped/target summary.
Approximation cards show semantic and routed markers, an amber connector, actual
distance, normal tolerance, reason, and access/profile warnings. Exact failures offer
explicit conversion, move, and remove actions. Approximation actions can make exact,
accept the routed fallback, or remove the stop. Every edit invalidates candidates and
requires a new generation request; no automatic weakened retry exists.

Canonical JSON preserves strength, bounds, identity, profile, and approach override.
The strict Marly fixture remains an exact 41 km regression; the adjacent
`all-pois-best-effort-generation-request.json` fixture makes its scenic constraints
bounded best effort. GPX still contains exactly one track and one segment, no route or
extensions. Reached and approximated routed targets may be ordinary waypoints;
approximations are named truthfully and all targets are revalidated at export.

Direction arrows, route reversal, destination clusters, Domaine-specific grouping,
shared outings, live location, and mobile applications remain later work.
