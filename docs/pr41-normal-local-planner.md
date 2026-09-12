# PR41 — normal local planner integration

Work continues on `feat/pr41-normal-local-planner`, based on the reviewed local
GPX/document-save preparation at `dad310c` (GitHub draft PR #43). The full PR41
release/device gates remain open. Normal Generate now uses canonical local result
publication when the Android bridge is present; the host evidence and remaining
production boundaries are recorded below.

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

## Normal Generate integration — 2026-09-12

Normal Generate selects `local_planner.js` whenever the Android bridge exists.
Local availability comes from installed native capabilities, using generated public
profile labels; the server profile catalog is not queried. Both modes return the
same immutable canonical objects used by normal candidate selection, the map,
saved/shared snapshots and GPX. Cancel invalidates publication immediately but
keeps the active request until any native call drains, including across modes.
Native route calls require an explicit public profile. Capability failure, missing
region, uncovered points and unsupported intent are explicit; none selects an API
fallback or weakens the source request.

Native lines use the normal candidate map layer and canonical direction arrows.
There is no remote visualization request or inferred edge coloring. Repetition,
backtracking, surface, road class and excursion displays respect their supplied
coverage/availability. Nature totals remain in route details; detailed native
nature map coloring is unavailable. Required-marker visit ordering preserves
original indices and names through optimized native sequences. The local core and
the temporary regional installation panel share one regional worker/client.

Shell v32 contains the normal planner and the three existing licensed Open Sans
glyph chunks used for required-point labels. The service worker now applies its
explicit shell-file allowlist to runtime static cache access as well as precache;
no routing data, raster tiles or arbitrary static paths are admitted. The font
coverage limits remain those documented in the packaged font README.

Current supported local subset remains explicit:

- Waypoint Route: fixed or bounded optimized order, exact interior points,
  Shortest, nature off and loop-geometry preference off. Existing strict and
  balanced maximum-distance gates remain hard.
- Auto Tour: loops with a fixed start, installed indexed scenic/verified-water
  preferences and local nature. Required interior points, imported requested soft
  stops, open Auto Tours and custom excursion allowances currently fail explicitly.
  Missing low-overlap/full loop-geometry analysis is an immutable optional-preference
  compromise, never a fabricated score or weaker exact retry.
- Native route reversal and map-wide local POI discovery are not yet connected.
  Reversal is disabled with an explanation, avoiding a server routing dependency.
  Auto Tour still queries installed local POIs through the shared regional worker.

Validation for this integration:

- `make check`: **1,028 passed / 16 existing integration tests deselected**;
  Ruff and strict mypy pass (244 files). Earlier PR35/38 architecture assertions
  were updated from their historical server-only Generate boundary to the new
  explicit native selection. The disabled release-factory gate is still checked.
- **282 scenarios across fourteen browser harnesses pass**. Eighteen normal-core
  cases include both modes across six profiles, missing region/capability/profile,
  outside coverage, unsupported intent, strict maximum, original required-point
  indices/names, cancellation, native drain and cross-mode single flight.
- **Fifty complete browser results** pass Python canonical and unchanged neutral
  snapshot validation; **59 candidate GPX files** match Python's XML fields.
- `/tmp/sugarglider-pr41-normal-ui.py` uses the real application page and a disclosed
  synthetic native bridge. It loads the shell, stops the static server, reloads
  offline, imports canonical plan JSON and clicks normal Generate/Download for
  Waypoint Route and Auto Tour with `hike` and `city_bike`. All four pass canonical
  validation, exact MapLibre line comparison, direction arrows, unknown metrics,
  prepared GPX transfer and explicit outside-region failure. There are **zero API
  requests during generation/export**. One first-render glyph fetch is fulfilled
  from the active shell cache; the other three cases make no page fetch.
- UI counts: Waypoint 1 native call / 1 candidate per profile; Auto Tour 5 calls /
  2 candidates per profile. GPX sizes: 565/576/651/662 bytes respectively. These are
  synthetic host fixtures, not graph or physical-device measurements.
- Evidence: `/tmp/sugarglider-pr41-normal-{check,browser,ui}.log`,
  `/tmp/sugarglider-pr41-normal-ui.json` and the exported canonical fixture results.

Next: physical normal-UI and document-save checks, bundled first launch,
release routing and the complete required Fairphone matrix. Regional installer
and useful-region device acceptance continue under PR42; public hosting/signing
and final Play gates remain explicit in the V1 ledger.

## Fairphone normal-planner preparation — 2026-09-12

USB authorization was resolved and the existing debug installation was upgraded
with `adb install -r`, preserving its data. APK SHA-256 is
`20341a5f4b382ee90807b07203e19c24ec31b11838b65218eef0ed7c1329408b`
(the unchanged native source at `dad310c`). The shared page uses shell v34 on
Fairphone 6 / Android API 36 / WebView 151. **This is debug preparation evidence,
not the required release-equivalent PR41 acceptance.** The configured localhost
origin and prior development-region installation still require setup.

A temporary static-only server supplied the new shell. That process and its USB
reverse connection were removed before each accepted run. The actual Import JSON
and normal Generate controls invoked real native Valhalla; routing was not mocked.
Non-pausing diagnostic logpoints observed call counts and the actual MapLibre
candidate sources without substituting results. All logpoints were removed.

| Normal Generate case | Time | Native calls | Candidates | Recommended distance | Vertices |
| --- | ---: | ---: | ---: | ---: | ---: |
| Waypoint Route / hike | 304 ms | 1 | 1 | 4,226 m | 270 |
| Waypoint Route / city bike | 314 ms | 1 | 1 | 4,249 m | 259 |
| Auto Tour / hike | 2,254 ms | 12 | 2 | 14,378 m | 783 |
| Auto Tour / city bike | 2,021 ms | 14 | 2 | 14,397 m | 518 |

All four use `marly-dev-v1`, pass the unchanged Python canonical/submitted-candidate
validator, and display the exact candidate line, direction arrows and visible
Marly offline-map attribution. Missing graph details remain unknown. Both tours
consume installed local nature data (scores 11.6632 and 43.9662); the no-POI
control remains exposed. Repeats preserve all candidate IDs/order, recommended
geometry hashes, distances, nature scores and native call counts. Zero API
requests occurred during generation. Page request events for cached worker/glyph
assets are reported separately; this is not a claim of zero HTTP-shaped events or
of disabled Internet connectivity.

The original cycling test used hiking endpoints and correctly failed: its start
snapped **34.7999 m** away, beyond the unchanged **25 m** hard limit. The failure
retains one call and no weakened retry. Public diagnostics now preserve bounded
rejected-attempt evidence, and the normal error shows the named point, measured
distance and limit. The separate successful cycling fixture explicitly uses
native bicycle graph coordinates: start 48.871420, 2.096040; checkpoint 48.884970,
2.096471; end 48.898605, 2.096757. No product constraint or source request was
silently changed. A separate outside-coverage fixture returns
`no_covering_routing_pack`, one native call, no API call and no retry.

Normal Download on the cycling tour passed Android document-picker cancellation
and saving, including a filename changed in the picker. Cancellation leaves the
selected candidate intact and re-enables Download. The saved GPX is **22,717 bytes**,
518 trackpoints, one track/segment, no route or extensions, and exactly matches
Python's canonical XML fields. SHA-256:
`2e8b12321ced15e0b04bac0c2b8011fdace6c8de5da59f10200fe5bf1b7db1c6`.
The candidate is unchanged and export makes zero native route calls. The final
success message is “GPX file saved.” because Android may rename the suggested
filename without returning that name to the web page. The first automation tap
did not activate Save; keyboard focus/Enter completed the real picker, and the
full Save test was repeated successfully.

Current automated evidence: `make check` passes **1,028 tests / 16 existing
integration deselections**, Ruff and strict mypy (244 files). **283 browser
scenarios** pass; the new case asserts measured exact-endpoint rejection and no
weakened retry. The actual-page synthetic native integration passes again after
the final shell/message change. All five GitHub checks passed `fe80ea7`; this
follow-up requires its own CI.

Reports and small drivers are under `/tmp/sugarglider-pr41-phone-*`; automated logs
are `/tmp/sugarglider-pr41-snap-browser.log` and
`/tmp/sugarglider-pr41-phone-followup-{check,ui}.log`. Generated GPX stays outside
Git. Owned ADB forwarding/reverse connections and static servers were removed.
The original stay-awake setting remains `0`; hotspot/radios were unchanged, no
location sharing was started, and no app data was cleared.
