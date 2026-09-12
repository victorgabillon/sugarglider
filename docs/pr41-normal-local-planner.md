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

Next: shared canonical candidate evaluation and portfolio, normal Generate/map/
selection publication, truthful unknown-detail rendering, bundled first launch,
release routing and the complete required Fairphone matrix. Regional installer
and useful-region device acceptance continue under PR42; public hosting/signing
and final Play gates remain explicit in the V1 ledger.
