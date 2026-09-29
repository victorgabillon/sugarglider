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

## UI-2 — Auto Tour primary flow

Based on current main after UI-1 review/merge. Files: index.html planning form, app.js renderStatus/read controls, state.js only where presentation state requires it, planner_profile.js unchanged unless a concrete defect is found, styles.css and browser scenarios.

Order activity → distance → Start guidance → Generate. Move tolerance/candidate count/coordinate entry and advanced preferences behind understandable disclosure; preserve all six profiles, strict/balanced/flexible semantics and explicit failure actions. Simplify loading/cancel/error copy. Acceptance: fresh default Trail run on Android; explicit Hike persists; real START immediately enables Generate; no hidden hard constraints; keyboard and narrow/keyboard-open layouts work.

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

The form still has its existing detailed controls and copy; UI-2 will simplify their hierarchy. Candidate diagnostics remain in UI-3's scope. Waypoint editing and region terminology retain their current behavior pending UI-4/UI-5. The separate Python boundary-crossing nature-polygon rejection and local GraphHopper isochrone warning are documented in the audit, not changed here. Browser emulation and an Android debug build are not a claim of new Play-delivered acceptance.
