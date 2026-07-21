# PR14 working-tree scope

The current working tree is a combined change, not a standalone PR14 refactor. It
contains both:

- the unmerged PR13 meaningful POI arrival/access foundation, including format-2
  approaches, cautious access provenance, selected/dropped decisions, and selected
  GPX arrival validation;
- the PR14 canonical planning API, package cleanup, request migration, browser state,
  and planning architecture work.

The recommended final history is option A: two sequential commits in one pull request,
with the POI arrival/access foundation first and the canonical planning refactor
second. This keeps the dependency relationship reviewable without attempting a risky
reconstruction of the already interleaved working tree. No Git history operation is
part of this correction pass.

The PR description must call out both layers and report acceptance results before and
after canonical publication. In particular, it must not describe a zero-requested-stop
canonical recommendation as preserved behavior when the producer recommended a safe
coverage candidate.

## Final planning boundary

Runtime planning has no adapter module and never imports the removed `generation` or
`tours` packages. Native Waypoint Route code consumes the canonical request directly
and separates controls, ordering, routing, draft construction, scoring, evaluation,
and portfolio publication.

Both route-search modes create a single request-scoped `PlanningSearchContext`. The
context owns the typed phase budget, cached routing gateway, and algorithmic
diagnostics collector. Route, alternative-route, round-trip, and isochrone operations
flow through that gateway. Hits consume no budget; misses reserve once and cache both
success and deterministic failure. Budget rejection before a backend call is exposed
separately and is not a cache miss.

`CandidateDraft` and `CandidateEvaluator` define the canonical pre-publication seam.
The shared portfolio remains the only code assigning public roles and ranks. Routing
profile IDs are included in immutable cache keys now; adding new profiles and routing
options is intentionally deferred to PR15.

## Native Waypoint parity completion

The obsolete Waypoint candidate engine and its private request/result compatibility
models have been deleted. The native implementation is split into controls, proposal
models, bounded ordering, graph-derived detours, gateway routing, low-overlap beam
assembly, draft construction, scoring, and orchestration. The largest Waypoint module
is under 400 physical lines.

Loop detours sample only cached GraphHopper round-trip proposal geometry. Open detours
sample only GraphHopper alternative-leg geometry and reroute the complete endpoint-
fixed sequence; they never cut a closed round trip into an open route. Low-overlap
assembly requests each leg through the shared `alternative_leg` phase and has no
private cache or request counter. Complete routes retain exact-point order and pass
the shared snap, topology, evaluator, and portfolio boundaries.

## Native Auto Tour completion

The 4,260-line Auto Tour candidate monolith and the 892-line mixed engine-model file
have been deleted. Auto Tour is split across focused controls, loop/open orchestration,
skeleton routing, requested and approach search, discovered-POI search, through-route
continuation, repairs, excursions, decisions, internal quality, diagnostics, scoring,
and canonical service modules. The largest module is 660 physical lines.

Every GraphHopper operation flows through the request context's routing gateway.
Approach comparison has its own typed phase, alternative-leg assembly relies on the
gateway cache and budget, and legacy route/cache counters have been removed from
mutable search state. Algorithm state retains only proposal, beam, decision, warning,
and timing facts.

Search routing uses structural analysis. Each retained routed path is carried into a
shared `CandidateDraft`; the shared evaluator performs the one final enriched analysis,
scorer call, safety/arrival validation, and unranked canonical candidate construction.
The shared portfolio is the sole public role/rank authority. The offline migration
command is wheel-installed, while HTTP runtime compatibility remains absent.
