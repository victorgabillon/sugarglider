# Sugarglider UI 2.0 design language

1. **Map first, task alongside.** The map is the stable spatial context. Plan and Routes are explicit destinations, not successive kilometres of page scroll. Keep route/active edit > START/waypoint/selected place > ordinary places.
2. **One primary action per context.** Map: place START or open Plan. Plan: Generate. Routes: choose a candidate, then GPX. File utilities belong in Tools. Keep disabled reasons and cancellation available.
3. **One shared product, two spatial layouts.** Desktop: bounded 22–24rem task rail beside a large map. Phone: full map with an explicitly opened, scrollable task panel and persistent Map / Plan / Routes navigation. No gesture-only affordances; no competing nested page/panel scroll.
4. **Warm and credible.** Retain forest green, warm paper surfaces, a restrained yellow primary accent and the existing serif wordmark. Use system sans for operational text; no new remote font or artwork. Existing mascot appears in brand, required markers and deliberate selected-place artwork only.
5. **Hierarchy before ornament.** Useful titles, consistent control sizes, restrained borders, one level of elevation. Avoid three equal dashboard columns. Metrics only when a route exists or the user asks for Routes.
6. **Plain language, honest facts.** Say Start, Plan, Routes, Download. Do not invent duration or elevation. Missing nature/coverage remains explicit. Build IDs and structural routing diagnostics belong behind technical details in later work.
7. **Predictable interaction.** Panels retain their form state. Choosing a view never changes route intent or selected coordinates. Set on map opens map context. Route generation completion makes results discoverable without rerouting. Native bridge and persistent stores remain unchanged.
8. **Accessible by default.** Named semantic buttons, explicit pressed/current states, visible focus, Escape dismissal, 44px phone controls, text wrapping, safe areas and reduced-motion support. Panel closure returns focus to its trigger. No formal WCAG claim without full audit.
9. **Small motion, small cost.** No new image assets/framework; no continuous map-move layout work. Observe the map container size and resize MapLibre only when its actual dimensions change. Transitions must not block input.
10. **Release in batches.** Five focused UI PRs, each reviewed and validated; one later release task. Ordinary PRs never bump application versions, sign AABs, upload Play artifacts or publish regions.

## Initial token proposal

- Type: system sans body 0.875–1rem; section 1–1.25rem; meta 0.75–0.8125rem; wordmark Georgia 1.3–1.5rem.
- Spacing: 4, 8, 12, 16, 24, 32px.
- Radius: 8px controls; 12px panels; 16px sheets.
- Surface: paper / elevated paper / map overlay; subtle one-pixel borders.
- State: forest primary/selected; yellow high-emphasis action; blue focus; named success/warning/error tokens, always accompanied by text/icon.
- Controls: 40px desktop minimum, 44–48px touch; visible hover, pressed, focus, disabled and loading states.

# UI 2.0 — five independently reviewable PRs

Baseline: origin/main e2aa39db5a386ff178ae85a28949794bd104be75, tree 650ee5a4e27bc2014f740b0d1483b1750ed0871f.

## UI-1 — Shared map-first workspace and foundations (implement now)

Highest value: make the map persistent and give both layouts explicit Plan / Routes navigation; stop dedicating desktop space to empty route details and phone space to oversized header utilities.

Files: index.html (semantic workspace/navigation/results grouping, file tools), styles.css (tokens, bounded responsive shell, controls), new app_shell.js (presentation-only view/focus/resize coordination), app.js (explicit map-edit and generation-result navigation hooks), service-worker.js + android/shell-assets.txt (cache/packaging), focused browser harness and product design documentation.

Acceptance: all five target widths; no horizontal overflow; map remains visible while configuring; Plan/Routes/Map keyboard and touch actions; return to Map without losing form/route state; desktop map dominates width; existing START/Generate/POI/waypoint/GPX flows pass; no social functionality exposed in Android. Existing map art/route rules unchanged. Before/after real-state evidence, browser scenarios, make check, JVM/lint/debug build. No release artifact/version change.

## UI-2 — Planning experience + mode unification + Auto Tour primary flow

Study approved 2026-09-29. PR1 #63 merged as 2ea8b47cea1320c928e688278063f8b3a1339e46, tree d06297e68d10fa2b2eac19100fef5e786effc94f. PR2 starts on feat/ui2-planning-flow only after merged-main CI is green. Approved primary wording: **Suggest a route** / **Connect my points**, with explanations of distance-led design and user-chosen points. No stacked branch. The master plan was updated before production implementation.

**Product distinction:** Auto Tour asks Sugarglider to design/discover a route. Waypoint Route asks Sugarglider to connect points chosen by the user. One Plan experience presents these as two understandable choices, with one shared Routes destination. Keep their routing algorithms, capability validation and mode-specific drafts separate.

**Audit before selecting the design:** trace the existing owner and presentation of Start, Activity, region/profile readiness, planning type, Generate, loading/cancellation, validation/errors and results. Compare concise alternatives in the real application at phone and desktop sizes. Record both user questions: “a nice 10 km run” and “from here through three places.” Evaluate discoverability, truthful capability wording, screen use and readability; distinguish expert walkthrough predictions from human usability-test results.

**Shared planning presentation:** one Plan title, explained mode choice, Activity selector, readiness summary/action, active Start presentation, generation/status area and result transition. Reuse current availability and execution paths. Preserve each mode’s points/options when switching; never silently copy, overwrite, weaken or reinterpret exact constraints. Shared presentation does not require shared stored Start objects.

**Auto Tour primary flow:** choose activity → roughly how far → choose Start → Generate. Scenic/water/nature and route-discovery preferences are optional. Keep explicit strict/balanced bounds and unavailable-data warnings discoverable and truthful. Expose existing advanced settings without making the initial path depend on understanding routing internals.

**Waypoint integration in this PR:** the same shared fields and Generate/Routes flow, a concise explanation that selected points are connected, and the existing destination/waypoint editor where applicable. Do not redesign add/select/edit/remove/reorder interactions yet. Both modes may use Loop; supported desktop Auto Tour can also have an end. Android Auto Tour is loop-only. Preserve these real capability differences rather than claiming destination or distance fields belong exclusively to one algorithm.

**Files:** index.html planning form; app.js presentation, shared renderStatus and existing mode-switch hooks; a small pure presentation module only if needed; styles.css; focused browser scenarios. Reuse planner_profile.js and generationAvailability(). Avoid state.js changes unless a concrete presentation defect requires the smallest correction. No changes to routing engines, request schemas, region schemas/catalog, native bridge or profile persistence. Cache revision/Android allowlist only if shared asset delivery requires it.

**Acceptance:** the two novice tasks identify the intended branch without knowing the established mode names; both branches stay within one Plan workspace and return to Routes; Activity/readiness/Start/Generate have consistent presentation; exact mode round-trip preserves points/options; no silent request rewrite. Fresh Trail run and explicit Hike persistence remain correct; real Start enables Generate and remains visible after entering Plan (viewport-only correction if needed); loading/cancel/error and 360/390/412/1280/1440 layouts work. Compare canonical requests before/after presentation changes, including explicit constraints and Waypoint distance settings. Real-map screenshots, focused browser regressions, make check and Android validation. No application version bump, release signing, Play action or tag.

## UI-3 — Route comparison and export

Based on reviewed UI-2/current main. Files: app.js candidate/metrics rendering, styles.css, index.html results group; format.js only for truthful existing metrics.

Readable ranked candidates, obvious selected route, distance and available quality facts first, detailed diagnostic metrics on demand. Clear GPX action for chosen candidate. Acceptance: selecting never regenerates; geometry/GPX bytes preserve canonical result; empty/error/imported/saved snapshot states work; desktop comparison and phone flow retain map context. No invented elevation/duration.

## UI-4 — Waypoint and contextual map editing

Based on reviewed preceding main. Files: app.js endpoint/point editor, map.js interaction affordances only, state.js presentation transitions if necessary, styles.css/index.html, browser interaction tests.

Clear active editing target; Add / Move / Remove / supported reorder; distinguish START/END/required vs optional places. Acceptance: map/editor/popup selection agree; order/names/coordinates retained; ordinary/ice-cream selection cannot mutate route; touch/mouse/keyboard equivalent; route hierarchy preserved. No routing redesign.

## UI-5 — Regions, secondary surfaces and consistency

Based on reviewed preceding main. Files: region_screen.js, local_region_panel.js, pwa_view.js, trail_profile.js, index.html/styles.css and focused tests.

Product language for available/installed/update/downloading/ready/failed; hide build diagnostics by disclosure; review Tools/import/profile/storage/error states; accessibility/text-scale/focus and responsive sweep. Audit existing desktop-only saved snapshots without enabling sharing in the private Android release. Acceptance: normal install/update/cancel/rollback unchanged, old region retained until replacement ready, no schema/catalog/native permission changes. All milestone flows at 360/390/412/1280/1440 and safe debug WebView validation.

## Dependencies and release boundary

Each PR starts from then-current main after previous review; no uncontrolled five-PR branch. UI-1 owns the only shell/navigation abstraction. Later PRs change content inside it rather than invent parallel panels. One separate milestone release task chooses a future version/code, signs once and performs one Internal/Play acceptance. Production and Closed testing remain out of scope. No new region format.


## UI-1 implementation contract

The shared shell uses the existing HTML, CSS and ES modules. `app_shell.js` owns only the current workspace, visibility, keyboard focus and map-container resizing. It neither imports planning state nor writes storage. Plan and Routes retain their DOM and scroll position. Phone Map closes both panels; desktop retains one 360px task panel. At or below 840px, an open task panel shares the remaining viewport with the map (60/40); it does not cover the canvas. The dynamic viewport and bottom safe-area inset are respected. Existing outing pages retain their independent layout.

`app.js` opens Map for explicit endpoint/point placement, reveals generation progress in Plan and opens Routes for successful results. File import uses native buttons; Save, import/export, profile, offline regions and storage utilities live in Tools. Android capabilities still determine which of those actions are available. No routing, profile persistence, region, GPX, artwork or native behavior is changed.

The shell cache revision advances independently to v47. The shared shell generator adds the new module to the Android allowlist. Application version remains 1.0.3 / code 5.

### Reproducing the presentation regression tests

From the repository root run `python -m http.server 8765 --bind 127.0.0.1`, then open `http://127.0.0.1:8765/tests/browser/ui2_shell_harness.html` in a modern browser. The page reports its named scenarios and PASS/FAIL. It loads actual application markup/styles in same-origin frames and exercises the presentation controller without a routing service.

Coverage includes 360/390/412/840/841/1280/1440px, a 390×420 keyboard-sized viewport, 200% text, state/scroll retention, navigation semantics, focus when results open, Escape/dialog ownership, file chooser buttons, region-menu reachability, breakpoint changes, outing isolation and bounded resize work. Existing endpoint/profile/local-planner/places/GPX/region/PWA harnesses cover domain behavior. Real Yvelines map and GraphHopper generation are exercised separately in the external before/after capture evidence.

Full repository checks: `make check`; with JDK 17 and an Android SDK, `cd android && ./gradlew --no-daemon testDebugUnitTest lintDebug assembleDebug`. These commands do not produce a signed release bundle or install on the Play device.

### Deliberately deferred

UI-2 now groups the existing controls in one Plan flow. Candidate diagnostics remain in UI-3's scope. Waypoint editing and region terminology retain their current behavior pending UI-4/UI-5. The separate Python boundary-crossing nature-polygon rejection and local GraphHopper isochrone warning are documented in the audit, not changed here. Browser emulation and an Android debug build are not a claim of new Play-delivered acceptance.


## UI-2 implementation contract

PR2 starts from merged PR1/main `2ea8b47cea1320c928e688278063f8b3a1339e46` after all main CI passed. The primary labels are **Suggest a route** and **Connect my points**, each with its approved explanatory sentence. They share Activity, Distance, active Start presentation, readiness and Generate/status. More planning options retains topology/destination, tolerance, strict/balanced/maximum, candidate count, profile/data warnings and discovery preferences. The existing point editor moves before Generate for Connect; advanced anchors remain collapsed for Suggest. Moving its existing DOM does not add a point-editing implementation.

The mode IDs, `state.autoTour`, waypoint endpoints/points/options, request schemas, engines, shared activity preference and results remain authoritative. No second planner store is introduced. A form-restoration defect discovered by the required roundtrip test is fixed: a null maximum in the waypoint draft must remain blank instead of falling back to the Auto Tour maximum. Edits in the waypoint form no longer write inactive Auto Tour metadata. This preserves intent instead of changing algorithm behavior.

`app_shell.js` marks actual container dimension changes. Only the Plan resize callback may call the screen-space visibility helper for the active edit point (otherwise selected point or Start). It checks the visible map container, because canvas dimensions can lag MapLibre's resized projection by a frame. Already visible points cause no pan; no coordinate changes, render recentering, map-move listener or camera store is added. Routes and active generation never invoke that correction.

The shared shell cache is v48. `map_viewport.js` is included in the explicit offline allowlist and generated Android assets. Version remains **1.0.3 / code 5**. No engine, region, Play, signing or release change is part of UI2 PR2.

### Planning tests and evidence

The standalone `tests/browser/ui2_planning_harness.html` adds draft/availability/controls/resize regressions to the shell harness. `tests/browser/ui2_request_acceptance.cjs` runs real JSON imports and mode controls against a running application with six routing profiles. Set `PLAYWRIGHT_MODULE` when Playwright is outside Node's normal resolution, `UI2_BASE_URL` to the app, and `UI2_EVIDENCE_DIR` to an external directory. `UI2_PHASE=before` records the baseline failure without requiring the fix; the default after phase requires preserved drafts. No fixture is injected into the planner state in that integration test.

External review evidence: `/home/pompote/oldata/victor/sugarglider-v1-artifacts/ui2-pr2-planning-2026-09-29/`, including paired captures, the canonical-request comparison, exact test totals and an interactive gallery. Captures use real Yvelines maps/places and local GraphHopper routes in isolated browser contexts, not a Play-device update. Novice-task reasoning is an expert heuristic walkthrough, not human usability validation.

Candidate comparison and export hierarchy remain PR3. Full waypoint manipulation/touch/mouse redesign remains PR4. Region-management polish remains PR5.


## UI-3 implementation contract

Baseline: PR2 merge e26ad8105397cddc5a72a0aee4ba9b8201cc7637, tree ca65aac58980ee821481b38305521d8d459511f6. The shared Routes workspace retains returned array order, ranks, IDs and first-candidate default. `route_results.js` only renders those objects; `state.selectedSignature` remains the selection authority. Numbered cards show distance, distance-range status and mapped repeated travel (Unknown when unavailable). A check mark, pressed state and solid line identify selection; alternatives use dashed matching swatches. Selecting never regenerates or fits the camera, preserves keyboard focus and clears an outdated visualization while the selected projection loads.

One selected-route surface places Export GPX before Route details. Normal details retain stop outcomes, traversal and coverage-aware measurements; score, search budget, full IDs and loop/nature calculations are under Technical diagnostics. More route actions retains existing reversal/save capabilities; private Android capabilities are unchanged. GPX still snapshots the selected candidate into the existing local worker and existing Android/browser saver. Status is visible in Routes; save cancellation never changes a route.

Empty Routes distinguishes never generated, zero results, failure, cancellation and invalidated results. `resultsInvalidated` is only a transient notice bit, not a candidate or selection store. Starting a validated new generation clears obsolete candidates; failure/cancellation cannot leave an older result looking current. A completed new result scrolls Routes to its beginning once. Manual workspace switches and candidate selection do not repeatedly recenter the map. Short phone viewports keep a 120px minimum map; all results remain in one task scroller.

PR4 retains waypoint editing; PR5 retains regions/secondary surfaces and the final consistency sweep. Version stays 1.0.3 / code 5. Responsive browser evidence is not a phone installation or a formal WCAG audit.
