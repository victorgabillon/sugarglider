# PR21 edge-aware global tour optimization

PR21 uses one request-scoped optimizer for route-shape work in Auto Tour and
optimized Waypoint Route. It replaces the former sequence of spur closure followed
by soft-stop relocation and local 2-opt. Those operations are now neighborhoods in
one complete-tour search:

```text
source candidates
    -> semantic optimization states
    -> bounded operators + lazy GraphHopper path options
    -> edge-aware objective + Pareto archive
    -> shared candidate evaluator
    -> shared portfolio
```

Pairwise shortest-path ordering is insufficient because a locally shortest leg can
reuse a long corridor already traversed in the opposite direction. A route such as
`B -> C -> D -> C -> B -> E` can require a different approach, order, or downstream
path option to become `B -> C -> D -> X -> E`. The objective therefore measures the
complete selected route, not isolated straight-line distances between stops.

## GraphHopper remains the path oracle

Sugarglider does not import a road graph or reproduce profile access rules.
GraphHopper supplies every authoritative path option through the request's shared
typed, cached routing gateway. The optimizer never creates straight segments,
reverses public geometry, or splices arbitrary coordinates.

The request-local lazy path pool starts with routed legs from the ordinary source
candidates. On a missing directed anchor pair, it requests at most three ordered
GraphHopper alternatives with the selected public profile. Successful and failed
queries use the existing request cache; the pool adds a small negative cache to
avoid repeating an unavailable pair. Retention keeps the source option, the shortest
option, and a physically low-overlap option instead of trimming exclusively by
distance. It does not precompute an all-pairs matrix.

The packaged GraphHopper 11.0 configuration has no CH preparations and one LM
preparation for each public profile. Its POST route endpoint supports request custom
models, GeoJSON custom areas, alternative routing, path details, pass-through, and
internal via points. Corridor penalties only reduce priority relative to the
prepared profile, so they remain compatible with the LM baseline. This capability
is explicit at the typed backend boundary; an unverified backend reports avoidance
as unsupported and uses only the guide-point fallback.

## Semantic state and exact boundaries

An immutable `TourOptimizationState` stores semantic anchor identity, selected
approach, order, one selected `PathOption` per leg, exact-window membership,
requested/discovered coverage, canonical edge use, typed objective components, a
complete routed path, and a stable signature. Geometry vertices are never treated
as stops.

Start, end, and exact waypoints cannot move. Movable anchors cannot cross an exact
window. Fixed-order Waypoint requests retain fixed semantic order, while their graph
path options may still improve. Alternate approaches keep the same stop identity and
respect access and semantic-distance bounds. A one-routing-point loop remains one
exact start at progress `0.0`; it creates no fake endpoint, move, or routing call.

## Canonical edge identity and objective

Route analysis and optimization share PR19's normalized geometry-edge projection.
Each canonical traversal carries the physical edge ID, direction, and normalized
distance contribution. The complete state derives:

- unique edge use;
- same-direction reuse;
- opposite-direction reuse;
- total repeated travel;
- immediate return travel;
- aggregate spur evidence.

Internal scoring can combine unchanged preprojected leg contributions. Complete
recomputation uses the same canonical representation, with micrometre rounding only
to suppress insignificant projection-boundary drift.

The typed lexicographic objective is ordered as follows:

1. complete graph validity, exact constraints, strict/explicit maxima, and severe
   profile validity;
2. requested-place coverage;
3. opposite-direction physical-edge reuse;
4. detected spur repetition;
5. total and same-direction repetition;
6. immediate backtracking;
7. profile and nature quality;
8. target error and route distance.

Distance is intentionally secondary for flexible and balanced requests. Strict
distance semantics remain hard. Publication additionally requires at least 500 m of
measured structural improvement and limits extra distance to
`min(5% of source distance, 2,000 m)`. Fully evaluated requested coverage, exact
identity, access, profile safety, and total-repetition non-regression remain gates.

## Bounded ALNS search

The search uses deterministic-seed simulated annealing so it can leave a local
optimum while never accepting an infeasible state. Weighted operator selection
rewards accepted and best-improving moves. A retained best state and deterministic
Pareto archive cover requested coverage, opposite-direction reuse, total repetition,
backtracking, profile/nature quality, and distance.

Before stochastic selection, the optimizer deterministically ranks at most three
substantial edge-supported PR19 spurs for each of at most two source states. It
samples up to eight genuinely downstream route positions, stops at the next semantic
boundary, rejects connectors that materially reuse the inbound physical edges, and
builds a compound semantic-leg option:

```text
semantic left -> source prefix -> turnaround
              -> GraphHopper connector -> internal rejoin
              -> preserved source suffix -> semantic right
```

The old return interval is absent. Turnaround and rejoin positions remain private
routing structure and never become request anchors, traversal anchors, or GPX
waypoints. Promising seeds rerun PR19 detection and must improve the specifically
matched target by at least 500 m; unrelated repetition changes do not count.

Connector generation first evaluates ordinary alternatives through complete
reconstruction and targeted PR19 comparison. Overlap viability is only a prefilter:
when no ordinary state improves the matched spur by at least 500 m, the optimizer
preserves the 100 m stem nearest the turnaround and buffers only the remaining
ordered inbound geometry by 25 m. The request sends this simplified,
at-most-80-vertex polygon as a private custom-model area with a `0.02` priority
multiplier. The complete area digest and multiplier are part of the shared
route-cache identity.

If custom avoidance is unsupported, fails, or still reuses too much inbound
corridor, or reconstructs only nonmaterial repairs, a deterministic private fan
tries guides on both sides. It generates 150 m, 300 m, and 600 m lateral offsets at
0.33, 0.50, and 0.67 forward shares before selecting a balanced inner/outer set of
at most four per rejoin. Two-sided rounds allocate at most six guide attempts fairly
across rejoins. Guide snapping, profile compatibility, detour size, and the unchanged
30% physical-edge overlap limit remain hard filters. No later strategy runs after a
reconstructed state reaches the 500 m targeted-improvement threshold.

The sparse ALNS operators are:

- path-option replacement without changing stop order;
- one soft-stop relocation inside its exact window;
- two-soft-stop swap inside a compatible window;
- bounded 2-opt inside one exact window;
- alternate approach for the same semantic stop;
- small two-to-four-stop ruin/recreate inside one compatible interval.

Operators first generate cheap descriptors. The optimizer selects one descriptor
before materializing it, so an ordinary iteration requests paths for at most the
selected changed pair. Unchanged legs reuse immutable path options. Complete public
route analysis and expensive enrichment occur only for targeted structural seeds and
the bounded archive sent to the shared evaluator.

Production hard bounds include eight initial states, three path options per directed
pair, 64 uncached optimizer calls, four permitted concurrent requests (the current
implementation is sequential), 128 negative entries, 500 iterations, 120
no-improvement iterations, a 12-state archive, 24 complete shared evaluations,
1.5 seconds of optimizer CPU time, and 4 seconds total wall time including routing.
These are ceilings, not targets.

If a call, iteration, no-improvement, CPU, or wall limit is reached, search stops
cleanly and returns best-so-far archive states. When nothing improves, the original
portfolio remains publishable. Optional optimization never converts a valid request
into an HTTP 500 or 503.

## Diagnostics, browser, and export

`search_diagnostics.details.global_optimization` reports source and initial states,
path-pool requests/results/cache activity, generated/selected/materialized move
counts, per-operator attempts/acceptances/best improvements, prune categories,
archive/evaluation/publication counts, best measured shape changes, finite
wall/routing/CPU timing, and limit flags. Per-target spur diagnostics may contain
already-public deliberate stop names plus source repetition, real downstream rejoin
and connector counts, inbound-overlap rejections, targeted improvement, evaluation,
archive, publication, and final-reason fields. Raw edge IDs, cache keys, backend
payloads, and rejected geometry are never exposed.

Strategy diagnostics separate ordinary, request-area, and guide generation,
including unsupported capabilities, requests, returned paths, snap/overlap
rejections, overlap-viable connectors, reconstructed states, nonmaterial states,
qualifying states, targeted improvement, and final disposition. Candidate provenance
is stricter than request diagnostics: only final PR19-matched spur improvements of
at least 500 m retain targeted IDs or names.

Qualifying single-spur results retain immutable applied-repair records and their
already routed semantic-leg replacements. A deterministic phase then considers at
most six actions, two per target, and at most twelve compatible pairs/triples. A
composed state contains at most three repairs and must use different semantic legs
with non-overlapping source intervals. Composition makes no routing requests,
rebuilds the complete routed path once, reruns route-wide PR19 analysis, and rejects
hard regressions or loss of any claimed 500 m repair.

The optimizer's analyzed spur value is the complete route-wide PR19 repeated total,
never one target's residual. Cheap ALNS moves may preserve the last analyzed value
as metadata, but it is excluded from cheap lexicographic and annealing comparisons.
Final public target IDs and names continue to come only from full structural
comparison after planner evaluation.

The browser labels published results “Edge-aware optimized route”. For portfolios of
at least three candidates, publication may reserve “Best route-shape alternative”
and “Distinct major-spur alternative” slots while preserving Rank 1 and the only
maximum-coverage candidate. The distinct slot must add a final PR19-matched target
not repaired by the overall slot. Excluded structural summaries are grouped by final
target set and bounded to three safe entries.

Canonical request JSON contains no path pool, operator history, selected internal
state, or rejoin point. GPX export serializes the final shared-evaluated route as one
track and one segment, with no route element or proprietary optimizer extension.

## Limitations

This is a bounded heuristic and does not prove global optimality. Results depend on
GraphHopper profile behavior and mapped OSM connectivity; a visually obvious
connection may not exist in the routed graph. Exact constraints and access gates
remain authoritative. The sparse neighborhoods do not enumerate every stop
permutation or graph path. Destination clusters and area-level coverage remain later
work.
