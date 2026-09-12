# PR41 — normal local planner integration

Work continues on `feat/pr41-normal-local-planner`, based on the reviewed local
GPX/document-save preparation at `dad310c` (GitHub draft PR #43). The full PR41
release/UI/device gates remain open. Normal Generate is not yet connected to
local canonical result publication.

## One request context

Both local mode searches now create exactly one `local_planning_context.js`
instance per request. Its gateway owns the native routing adapter, explicit
public profile, route-call reservations and request cache. The Waypoint Route
limit remains 16; Auto Tour remains 24 total with at most six POI calls. The
control lane still completes before the POI lane. Public phase usage comes from
the context; diagnostics do not reconstruct backend/cache facts from candidates.

Identical concurrent requests share one pending operation. Completed native
successes, returned failures and thrown failures are cached for that request.
Routing inputs and cached replies are immutable snapshots. A new planning
request gets a fresh cache, including when the profile/coordinates are identical.
Budget rejection happens before backend invocation and is counted separately
from cache lookup/miss facts. A cached hit reserves no additional call.

The context emits the existing canonical `PlanSearchDiagnostics` shape.
During an outstanding operation, entry count describes completed entries; its
lookup, hit/miss, completed-entry and backend-call identities still hold. Mode
searches expose these diagnostics for the upcoming shared candidate evaluator
and portfolio. Existing debug display fields remain available during integration.
Auto Tour's active request identity is now checked: an identical request joins
its pending search, while a different request fails explicitly until it drains.

The existing deterministic proposal/routing behavior and quality gates are
retained. No route geometry, profile alias, hosted fallback or invented graph
fact was added. Shell v30 includes the context and changed mode modules.

## Validation — 2026-09-12

- `make check`: 1,026 passed / 16 existing integration tests deselected; Ruff and
  strict mypy pass (242 files). Architecture checks now enforce reservation and
  backend invocation in the shared gateway instead of in individual searches.
- `/tmp/sugarglider-pr41-document-browser.py`: 223 scenarios across twelve real
  browser harnesses pass, including nine new context/ownership cases. Coverage
  includes all six profiles, pending deduplication, immutable inputs/replies,
  cached errors, phase/total limits, separate budget rejection, invalid inputs,
  clone-failure accounting, request isolation and active Auto Tour identity.
- Sixteen actual browser diagnostic snapshots validate through Python's
  `PlanSearchDiagnostics`, including snapshots with an operation still pending.
- Evidence: `/tmp/sugarglider-pr41-context-{check,browser}.log` and
  `/tmp/sugarglider-pr41-context-diagnostics.json`.
- Native source is unchanged from `dad310c`; no new physical acceptance is claimed.

## Canonical candidate publication — 2026-09-12

The shared evaluator now publishes native drafts as the existing `RouteResult`
and unranked `PlanCandidate` contracts. The shared portfolio alone assigns public
roles and ranks, preserves mode ordering, deduplicates canonical signatures and
retains Auto Tour's exact no-POI control. Unknown edge repetition cannot earn a
smooth-route role or authorize a POI detour recommendation. A failed control
publication cannot turn its detour into a recommendation.

All six public profiles use generated registry metadata and Python-generated
missing-detail analysis templates. Native route distance remains authoritative;
geometry distance is measured from the returned line. Path details, repetition,
backtracking, activity attributes and unavailable nature remain explicitly
unknown. Signatures use Python-compatible six-decimal rounding, including ties
and negative zero. Full routed geometry determines canonical traversal direction
and ordered deliberate anchors; the line itself is unchanged.

Auto Tour retains full indexed approach provenance and explicit per-candidate
POI outcomes. Publication independently checks the final line, meaningful approach
and strict arrival tolerance. Canonical stops use validated routed coordinates;
an absent OSM ID remains an explicit diagnostic outcome without an invented
coordinate. Nature publication preserves the existing normalized partition,
independent overlays, weights and measured score, with regional identity and
operation budgets in diagnostics. It does not rerun polygon analysis.

`local_plan_client.js` runs publication in a bounded module worker. Single-flight
ownership, page invalidation, stale responses, worker failure and a 60-second
timeout remain explicit; there is no inline or server fallback. Source requests,
gateway cache facts and phase usage remain immutable. Shell v31 includes the new
modules and the shared decimal formatter used by local GPX export.

Current validation supersedes the earlier totals above:

- `make check`: **1,028 passed / 16 existing integration tests deselected**;
  Ruff and strict mypy pass (244 files).
- **264 scenarios across thirteen real browser harnesses pass**, including
  40 canonical-publication scenarios and the existing regional-data cases.
- **Thirty-seven complete browser `PlanResult` values** pass the unchanged
  Python models and neutral submitted-candidate validator. Thirty Waypoint
  fixtures cover five shapes across six profiles; seven Auto Tour results cover
  all profiles, including two deliberately reached POI alternatives with nature.
  No validator tolerance was relaxed.
- All **39 published native candidates** also export GPX with XML fields exactly
  matching Python's canonical writer, including selected POI waypoints.
- The normal offline saved-route Download still passes with its static server
  stopped: zero export fetches, unchanged snapshot, 882-byte GPX matching Python,
  SHA-256 `fb1f53eb20d7ba7ce28ee705a5fb20c9292fe57c3d9ef453a9f3a90ad9939ba5`.
- Evidence: `/tmp/sugarglider-pr41-publisher-{check,browser,ui}.log` and
  `/tmp/sugarglider-{pr41_local_candidates,pr40_local_regional_data}-published-plans.json`.
  These are host/synthetic validations, not new device acceptance.

Normal Generate is still the next integration step. Explicit requested soft stops
and unsupported mode options must not be silently discarded while it is connected.

Next: normal Generate/map/selection publication, truthful unknown-detail rendering, bundled first launch,
release routing and the complete required Fairphone matrix. Regional installer
and useful-region device acceptance continue under PR42; public hosting/signing
and final Play gates remain explicit in the V1 ledger.
