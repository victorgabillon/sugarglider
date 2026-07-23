# PR20 bounded spur-closure repair

PR20 turns suitable PR19 out-and-back evidence into optional, graph-valid planning
candidates. The shared `planning/refinement` package is used by both Auto Tour and
Waypoint Route. Originals always remain available: failure to find an alternative
exit is not a planning error.

## Search and reconstruction

The repair lane considers at most two source candidates, two supported spurs per
source, eight rejoins per spur, three connector alternatives per rejoin, and sixteen
connector attempts per source candidate. Rejoins are generated deterministically
from the first position after the spur, downstream distance samples at 250 m, 500 m,
1 km, 2 km, and 4 km, and existing downstream routing or deliberate anchors. Nearby
points are deduplicated. Sampling stops at the next mandatory anchor, never passes an
exact endpoint, and does not treat a loop's duplicated start as an ordinary rejoin.

Each connector is routed with the selected public profile through the request's
existing cached gateway and the typed `spur_repair` phase. Its GraphHopper edge IDs
are compared with the source's inbound excursion corridor. The first 100 m of shared
travel near the turnaround is tolerated; after that, a connector is rejected when
charged inbound overlap exceeds 30% of the inbound corridor. Coordinate separation
alone is never acceptance evidence.

A connector is not published by itself. The implementation routes the complete
ordered prefix and suffix as graph-valid two-point legs, inserts the selected routed
connector, and uses the existing strict routed-segment composer. The resulting path
therefore carries authoritative distance, geometry, snapped endpoints, edge identity,
and path details. Exact endpoints, exact waypoints, and deliberate mandatory anchors
remain in source traversal order. A rejoin that would bypass such an anchor is not
attempted.

## Evaluation, acceptance, and diagnostics

Mode adapters rebuild their normal draft from the complete path. Requested stop
outcomes and Auto Tour POI visits are measured again; no final source outcomes or
analysis are copied. The ordinary shared evaluator then recalculates traversal,
nature, profile quality, repetition, immediate backtracking, spurs, safety, scoring,
and portfolio roles.

A repair must stay within an explicit maximum, preserve hard validity, avoid a new
severe profile incompatibility, and not increase total repetition. It must reduce
spur repetition or immediate backtracking by at least 150 m. Flexible distance miss
remains soft; balanced and strict requests retain their established evaluator and
portfolio rules. Nature, scenic, historic, and water utility comes only from the
existing generic evaluation and strict arrival semantics.

Candidate details expose source candidate and targeted-spur IDs, rejoin source and
progress, connector distance, charged overlap distance/share, before/after spur
distance, repetition/backtracking improvement, bounded attempt count, and whether a
target-like spur remains. Raw edge IDs and backend payloads are never public. The
browser gives repaired candidates a concise **Route refinement** explanation and
keeps PR19 cards truthful for any excursion still present.

Every canonical request also exposes a safe `search_diagnostics.details.spur_repair`
summary, including sources and spurs considered, rejoins generated, connector
requests and returned paths, overlap and reconstruction outcomes, exact/profile/
maximum/improvement rejection counts, accepted drafts, submission to and exclusion
by the shared portfolio, published candidates, and budget exhaustion. These are
aggregate counters only: rejected geometry, edge IDs, backend payloads, tracebacks,
and host paths remain private. The summary exists even when no repair is accepted.

The dedicated phase permits at most 48 uncached route requests per planning request.
Only the shared gateway reserves that budget, so cache accounting remains
`lookup = hit + miss`, `entry = successful + failed`, and `backend call = miss`.
Exhaustion adds `spur_repair_budget_exhausted`, retains originals, and does not turn
an otherwise successful request into an HTTP error.

The focused best-effort Marly diagnostic request considered two sources and four
spurs, generated nineteen rejoins, and made seventeen connector requests. Those
requests returned thirty paths. Twenty-seven paths exceeded the established inbound
overlap limit; all three remaining paths reconstructed successfully, one increased
total repetition, and two became accepted drafts. Both accepted drafts entered the
ordinary shared candidate pool (also visible in the retained Stage 2 planner
counter), but the shared three-candidate portfolio preferred the existing candidates.
No repair threshold or ranking rule was weakened.

## Preserved behavior and limitations

Rejoin points are private routing hints. They are not requested stops, traversal
anchors, canonical JSON, or GPX waypoints. GPX remains one track and one segment with
no route element or proprietary repair extension. Reversal reroutes the repaired
candidate's final traversal and freshly calculates route truth; targeted-spur repair
metrics are not copied into the reversed candidate.

Not every detected spur has a profile-compatible alternative exit. A repaired route
can be longer and can still contain smaller or structurally different spurs. Mapped
access, path details, nature, and POIs can be incomplete or stale and are not safety
or current-condition guarantees. PR21 will address bounded soft-stop relocation and
limited 2-opt search. PR22 will add destination clusters.
