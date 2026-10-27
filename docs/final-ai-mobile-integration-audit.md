# Final AI mobile integration audit

Audit date: 27 October 2026. This is the current integration record; older
preparation reports describe their own historical builds. Screenshots, APKs,
full route/editor backups and detailed machine receipts remain outside Git under
`/home/pompote/sugarglider-ai-mobile-2026-10-26/final-integration-audit`.

## Git integration

- Verified merged baseline: `18b7dd726615b97293de00983c43985f268dfa64` (PR #110).
- Verified initial GUI head: `625ef8b3a75e15b89eb7751e2e9eff01403dbfc2`:
  14 commits ahead, zero behind; baseline is its merge base.
- PR #110 source: `26c6dbe325333c48e2b7d5f126c165314f9a19ea`. It is already
  contained in the GUI branch. It was neither cherry-picked nor merged again.
- Consolidated implementation: `212a497f87f4f6b27675f7e73ec83c7f88a1e09a`.
- Verified artifact/code head: `cda0572`. Later commits synchronize strict cache
  fingerprints, record the audit and keep test placements clear of mapped POIs.
  Application/native/brand trees match the implementation commit.
- Final GUI branch head before the code merge: `cda0572647752bf480cbb182d3fe46d354d87497`; 18 commits ahead of the
  verified baseline and zero behind before merging.
- [Final GUI PR #111](https://github.com/victorgabillon/sugarglider/pull/111) is merged.
- Audited `main` code-merge SHA: `422e43715ba2530e452171efb94cc42db989fbd5`.
- Merged tree: `e625149ebd8bab6c23569414b5ca8691dd2b7b0c`, exactly equal to the
  reviewed GUI head's tree. The merge parents are the verified main baseline and
  final GUI head; forest and GUI ancestry are both retained.
- Reconciled main source base: `36c023aa30318443aac1ba9bc6025448ceb82980`,
  after the parallel session merged [PR #114](https://github.com/victorgabillon/sugarglider/pull/114).
  Its private Puy-l’Évêque coverage configuration and bounded terrain conversion
  changes are retained. They do not change bundled web, Android or brand trees;
  those trees still exactly match reviewed GUI source and installed cda0572.
  The broader Python `src` tree includes PR #114 and is not claimed identical to
  the APK's build source. No new regional pack was installed or published here.
- [Documentation PR #112](https://github.com/victorgabillon/sugarglider/pull/112)
  changes only this report relative to that main source base. The report's final
  merge revision is identified by its Git history; its merge and CI receipts are
  retained outside Git to avoid a self-referential commit hash.
- The installed device matches the consolidated cda0572 artifact after separate
  explicit approval and fresh preservation checks. This records acceptance of
  PR #111's GUI, not physical acceptance of later parallel changes.

The audit inspected **54 registered worktrees**, 51 existing and three stale
registrations, **70 local branches**, all 152 local/remote refs, untracked files,
one stash and in-progress-operation markers. No merge, rebase or cherry-pick was
pending. Directory timestamps were not treated as evidence of newer code.

| Relevant checkout/ref | Audited head | Finding |
|---|---|---|
| Local `main` | `1b8e800` | Stale by 204 commits relative to the initial remote main; never used as the integration baseline. |
| `feat/ai-mobile-experience` | `625ef8b` initially | Own clean GUI checkout; contains the merged forest work. |
| `feat/ai-adventure-integration` | `26c6dbe` | Clean forest checkout; contained in the GUI branch, left untouched. |
| `perf/cold-regional-loading` | `737547b` | Four unique commit IDs, but its entire tree equals merged PR #107 commit `0b29439`; no missing implementation. |
| `feat/flexible-endpoints` | `39e2845` | Already merged by equivalent patch. |
| `fix/endpoint-adjustment-viewport` | `63ddf96` | Already merged by equivalent patch. |
| `integration/nature-region-preference` | `2cfee9f` | Ancestor of the GUI branch. |
| `audit/v2-integration-2026-10-23-1v50hef5` | `fb7d5b5` | Historical merge-only commit; no unmatched implementation patch. |
| `feat/v2-bound-data-notices` | `5257bdc` | Equivalent committed changes already integrated. |
| `feat/pr21-soft-stop-local-optimization` | `0f4ce60` | Included by `69193e7` with subsequent spur-splice fixes; not missing work. |
| Remote `feat/pr9-loop-geometry` | `9b02344` | Entire tree equals merged `0aa93c3`. |
| Remote `feature/pr86-valhalla-mobile-064` | `76114b0` | Superseded by merged `7ef84b8`, including corrected native profile/response handling and regression tests. |
| `feat/pr44-release-audit` | `2ab30b8` | Historical release work superseded by `e58acdd` and later release/native hardening; signing isolation, renderer recovery and bridge/path checks remain implemented. |
| Root Places checkout | `c89a21d` | Two pre-existing empty untracked files, `Continue,` and `native`, retained. |
| PR96 baseline research checkout | `95b17a9` | Five pre-existing tracked/untracked forensic instrumentation changes retained in place; not treated as a finished product feature. |

The remaining uncontained local branch commits are squash-equivalent historical
brand, PR32–36 and release-code changes. No completed AI, forest or mobile feature
was found missing from the consolidated implementation. No worktree, stash,
untracked file or private evidence was deleted. Full ref, worktree and commit-graph
inventories are retained in the external audit receipts.

During final receipt preparation, the original checkout independently moved onto
`fix/named-start-mobile-toolbar` for [PR #115](https://github.com/victorgabillon/sugarglider/pull/115).
That is active follow-on work on named adventure starts and compact toolbars,
opened after the GUI code merge; it is not missing completed baseline work.
At reconciliation it remains open. Its checkout, branch, edits and processes were
left untouched. It is outside the installed cda0572 acceptance boundary and remains
owned by its parallel session. All other existing worktree heads/statuses and the
stash match their initial audit, including the untouched forest checkout. No new
worktree was created for this audit; the report branch uses the existing GUI checkout.

## Feature completeness

“Device” means physical Fairphone evidence, not synthetic browser replies.
`main before` means the verified PR #110 baseline; the final source contains all
rows. Current installed APK evidence is for **cda0572**. Prior physical editing,
offline generation and export evidence from the unchanged 625ef8b lineage is
identified separately; those expensive checks were not unnecessarily repeated.

| Feature | Main before | Final source / implementation evidence | Tested | Device / remaining acceptance |
|---|---|---|---|---|
| Account connection and secure native authentication | Yes | `ChatGptConnection`, `ChatGptAccounts`, fixed-endpoint `ChatGptHttp` | Native auth/HTTP/ledger tests | Same connected account confirmed; no credentials extracted. |
| Editable text and Android microphone | Yes | `adventure_dialog.js`, `adventure_speech.js`, `AdventureSpeechInput` | Browser/native speech and permission tests | Text/keyboard and microphone controls tested; no recording in this audit. |
| Structured proposals, local grounding and optional places | Yes | `adventure_controller.js`, `adventure_proposal.js`, `adventure_grounding.js` | Real local-worker/synthetic-model acceptance | Existing saved output inspected; final live forest request remains separately authorized work. |
| Historical research and sourced anecdotes | Yes | Reached-place story phase and citation handling in controller/results | Contract, provenance and controller regressions | Prior saved adventure retained; historical truth is not established by a source label. |
| Candidate comparison and bounded refinement | Yes | Assessment comparator, controller's one revision and shared planner session | Forest/tradeoff/budget/determinism harnesses | Three saved alternatives inspected; no new live inference. |
| Exact adventure recovery and GPX | Yes | `adventure_snapshot*`, `local_gpx_export.js` | Exact restart/selection/bytes, no rerouting | Real native export and original GPX preservation tested. |
| Early Nature on complete native routes | Yes | `local_planner.js` cached `analyzeNature` on complete validated paths | Forest search tests | Present in installed APK; final combined live acceptance pending. |
| Bounded local woodland hints | Yes | `local_region_data.js` / worker `queryWoodlandPoints` | Bounded operation/unknown-data tests | Present; no runtime hosted GIS dependency. |
| Strong woodland and forest/history retention | Yes | `strongWoodlandPreference`, `compareWoodlandTradeoff`, family retention | Shape/tolerance/unknown/tradeoff regressions | New GUI preserves translated labels and saved results. |
| Route-family diagnostics and 16-call budget | Yes | Shared context: total 16, initial 8, refinement 8; bounded deterministic search | Budget/cancellation/cache/determinism tests | No routing or inference performed merely by locale/GUI operations. |
| Mandatory waypoints, distance and endpoint snap constraints | Yes | Immutable hard-intent check and existing native resolvers | Routing/endpoint acceptance and domain tests | Physical editing/offline route test completed on installed lineage. |
| Official purple icon and shared Map/Plan dialog | No | Canonical supplied PNG, runtime synchronized; icon-only Map action | Asset and full-app accessibility checks | Visible immediately; one tap opens the existing dialog. |
| Minimal header, Tools and Map display | No | `app_shell.js`, intact settings DOM, touch-only navigation removal | Narrow/landscape/200%/desktop harnesses | Tested on Fairphone; Tools has 32.005 px normal / 31.677 px doubled-text bottom clearance. |
| Contextual editor and collapsed route bar | No | `route_dock.js`, existing editing authorities | Gestures, keyboard, edit/history, candidate and GPX checks | Real editing, dragging, local search and offline generation completed. |
| Compact legal attribution and marker clearance | No | Real control/painted-pin rectangles, five-second acknowledgement | Source changes, expanded credits, keyboard and insets | Auto-collapse measured 5,011 ms; explicit expansion and dock separation tested. |
| French default, English option and persistence | No | `i18n.js`, `translations.js`, existing PWA store, typed native UI locale | Full canonical request/result/form/camera/GPX invariants | French/English controls and persistence across font-driven Activity recreation verified; original French preference restored. |
| Distinct SG AI Test / TEST launcher | No | Variant label and XML overlay, production bitmap untouched | Manifest/resource/asset checks | Physical launcher badge and actual packaged identity verified. |
| Native Privacy multiline actions | No | `PrivacyDetailsDialog.kt`, full disclosure and explicit link retained | Android 36 native-layout tests: French/English, font 1×/2×, 320/372 portrait and 800 landscape | Verified on cda0572 in French and English at normal and Android font scale 2.0; full policy and Close labels visible in all four screenshots. |
| Locale-independent POI wire values | Main correct | Canonical `unknown` restored in queries and eligibility; no translation of data enums | French real-worker query and unknown-access map-action regressions fail before/pass after | French query succeeds on the real phone, including 72 unknown-potability entries; toggling filters preserves exact route/result/GPX. |

### Correctness and security review

The full GUI diff was reviewed, including shared app/map/result files, locale
bindings, bridge handlers, asset allowlists and changed test assertions. **148
protected source files** match merged PR #110 main byte for byte, including all
seven woodland runtime files, native routing and account implementation, Python
planning/domain/routing and selected-candidate GPX serialization. Shared forest
result changes localize presentation; they retain shape gates and family/tradeoff
meaning. No source routing algorithm, exact constraint, profile cache key, budget,
GPX track/segment contract or auth store was replaced.

The native auth store remains Android Keystore encrypted in no-backup storage;
WebView receives no token. Exact-origin, main-frame, nonce, ledger, visibility and
current-channel ownership checks remain. HTTP uses fixed official endpoints,
disables redirects, and adds no custom trust or cookie flow. New language/Privacy
operations do not expand native command authority. Language switching and snapshot
recovery retain canonical geometry and make no generation/inference call.

Two reproducible integration defects were corrected: Android's standard Privacy
button panel clipped long action labels, and translation accidentally changed
canonical POI `unknown` values to French text. Native layout and real-worker/map
regressions demonstrate both failures before the fix and passing behavior after it.
The existing Tools safe-area correction remains fixed. No further layout or
routing rewrite was introduced. Cache generation advances to v121 for changed
shared application assets.

## Fairphone state and preservation

- Device: Fairphone 6, Android 16 / API 36, serial `014728cc`.
- Installed package: `io.github.victorgabillon.sugarglider.v2staging`, **SG AI Test**,
  version `1.2.0-v2-staging`, code **8**, UID **10308**, revision **cda0572**.
- Installed APK SHA-256:
  `f19a1a255d131870a7a8f475cde54068ba313ae6c49507fcd427bf60b2e8a7ce`.
- Development/staging signer SHA-256:
  `e84155df3a2c7ea48723876b1fe8e0e602cb600f8374d6539b9fea9aa42cfbd7`.
- Initial read-only ADB verified the matching 625ef8b installation, which was
  retained until separate approval naming cda0572 and confirming the phone was
  free. Fresh signer/package/full-state/account/region/GPX checks passed. The
  625ef8b rollback APK was retained, and normal `adb install -r --no-streaming`
  replaced staging only. Installed cda0572 bytes, UID, packaged revision and
  native regional hashes were verified. No uninstall or data clear occurred.
- Initial foreground was ChatGPT. The empty staging draft was captured separately.
  After the user's explicit phone-free/restoration answers, the original
  **23,172 m** route, selected candidate, point index **0**, all **22 editor fields**,
  raw form values, speech draft and original camera were restored from full state.
  The same full state was backed up again before replacement and restored after
  native font tests. Candidate, result, source request, GPX and editor values match
  the protected snapshot; transient elevation operation/timing IDs are normalized.
  This was not a GPX-only reconstruction and did not reroute.
- Original GPX SHA-256:
  `52b5d326937e532bb4e4a3f66ce625774674d85b3c15ed97320332cfcb5ca6f0`.
  All **40 existing Download GPX files** remain unchanged.
- All **30 native regional files** and **23 OPFS files / 197,582,220 bytes** match
  protected receipts. The same two committed regions, region preference and exact
  saved adventure remain. No region was downloaded, published, replaced or removed.
- Ordinary connected-account UI and sanitized native status confirm the same
  connected identity and plan usage. No OAuth credentials were read/exported;
  no inference or recording was made. Production's four APK splits are unchanged.
- Physical cda0572 checks: one-tap AI dialog with the supplied artwork, connected
  account and accessible text/microphone; French POI filtering; Tools clearance
  32.005 CSS px; native Privacy in French/English at system font scales 1.0 and 2.0.
  Policy/Close button heights are 144/144 physical px normally and 244/153 px at
  scale 2.0, with both buttons wholly inside the dialog.
- Original system font scale **1.0**, rotation settings and French preference are
  restored. Device handoff: French Map, original route/selection/camera, collapsed
  editor. Native bridge restored and only this audit's debugger forward removed.

### Actual Fairphone screenshots

Private 1116 × 2484 PNGs are in the external audit root's `fairphone/` directory:

| Scene | File |
|---|---|
| Final French Map and original route | `cda-final-original-map.png` |
| Connected AI dialog | `cda-final-ai-dialog.png` |
| Native Privacy, French normal | `cda-privacy-fr-1.png` |
| Native Privacy, English normal | `cda-privacy-en-1.png` |
| Native Privacy, French font scale 2.0 | `cda-privacy-fr-2.png` |
| Native Privacy, English font scale 2.0 | `cda-privacy-en-2.png` |

The full physical receipt is `fairphone-cda0572-acceptance.json` outside Git; full
editor/route backups remain private. No screenshot or generated GPX is committed.

### Exact remaining package inventory

All IDs below use prefix `io.github.victorgabillon.sugarglider`.

| Suffix | Version (code) | Role / action |
|---|---|---|
| empty | `1.2.0` (8) | Production; retain unchanged. |
| `.v2staging` | `1.2.0-v2-staging` (8) | Canonical SG AI Test; retain data and current installation. |
| `.debug` | `1.2.0-debug` (8) | Retain; unique local data not reviewed/authorized for deletion. |
| `.v2debug` | `1.2.0-v2-research` (8) | Retain under the same data rule. |
| `.placesrealdata` | `1.0.2-places-real-data` (4) | Retain; data may be unique. |
| `.debug.test` | null (0) | Non-launcher instrumentation helper; retain. |
| `.v2debug.test` | null (0) | Non-launcher instrumentation helper; retain. |
| `.v2staging.test` | null (0) | Non-launcher instrumentation helper; retain. |
| `.v2auditb1.test` | null (0) | Non-launcher instrumentation helper; retain. |
| `.v2auditb2.test` | null (0) | Non-launcher instrumentation helper; retain. |
| `.v2auditf1.test` | null (0) | Non-launcher instrumentation helper; retain. |
| `.v2auditf2.test` | null (0) | Non-launcher instrumentation helper; retain. |
| `.v2auditn1.test` | null (0) | Non-launcher instrumentation helper; retain. |
| `.v2auditn2.test` | null (0) | Non-launcher instrumentation helper; retain. |
| `.v2auditn3.test` | null (0) | Non-launcher instrumentation helper; retain. |
| `.v2auditp1.test` | null (0) | Non-launcher instrumentation helper; retain. |

The eight application packages `.v2auditb1`, `.v2auditb2`, `.v2auditf1`,
`.v2auditf2`, `.v2auditn1`, `.v2auditn2`, `.v2auditn3`, `.v2auditp1` remain absent.
Their previously authorized cleanup is complete. No cleanup was repeated. Future
removal of retained apps needs package-specific data review and authorization;
helpers do not cause launcher clutter. Three stale worktree registrations and
historical branches likewise require no cleanup to finish this integration.

## Final validation and consolidated artifact

The consolidated GUI's local, GitHub PR and post-code-merge checks passed. The
exact remote receipts are in the merge record below. Local results for cda0572
and its implementation lineage:

| Check | Result |
|---|---|
| Ruff formatting/lint | Pass |
| Strict mypy | 303 source files; pass |
| Python | 1,612 passed, 16 service integration tests deselected; nine existing NumPy warnings |
| Browser harnesses | 62 passed, no page errors |
| Self-contained acceptance drivers | 18 passed (17 standalone drivers plus the full-app driver) |
| Full-app viewports | 372×760 French, 412×844 English, 320×720 French, 800×372 French, 1280×844 English; all pass |
| Android JVM | Debug 296, Release 291, Staging 291; 878 total, zero failure/error/skip |
| Android lint/assembly | Debug, Release and Staging all pass |
| Native Privacy regression | Five tests, including 12 language/font/viewport layout combinations and Close without a policy link; fail before/pass after |
| POI locale regression | French worker query and unknown-access map action fail before/pass after; English/private-access controls retained |
| Shell identity | v121 fingerprint expectations and complete allowlists pass |
| APK/ELF | All three APK ZIP/page-alignment/native-byte checks pass; staging ELF LOAD alignment ≥16 KiB |

After incorporating main's independent PR #114 into the documentation branch,
a fresh `make check` also passed: Ruff checked 320 formatted files, strict mypy
checked **304 files**, and Python reported **1,627 passed, 16 deselected**, with
the same nine NumPy warnings. This later count includes PR #114's additional
Python tests; it does not replace the exact cda0572 validation counts above.
Its log is `make-check-main-reconciled.log` in the external audit root.

The comprehensive native/application checks ran on the implementation commit.
740bd2b synchronizes two strict cache fingerprints; final Python, full-app and
staging identity checks also pass on cda0572. Browser CI additionally exposed a
landscape test tap that selected a now-visible drinking-water marker instead of
empty map. The fixture now uses unoccupied corners and explicitly checks Start/stop
acquisition; all five viewports pass without screenshot delays. Assertions retain
their original route/GPX guarantees.
Robolectric resolves its pinned Android image through Gradle; test execution is
explicitly offline and needs no Docker, map data, account or external service.
Android CI now includes staging tests/lint/assembly and 16 KiB checks alongside
Debug and Release, using disposable public CI inputs rather than private regions.

The **six legacy service-dependent drivers remain unrun**, not passed:
`automatic_intent_acceptance.cjs`, `itinerary_draft_acceptance.cjs`,
`location_search_acceptance.cjs`, `route_dock_acceptance.cjs`,
`ui2_request_acceptance.cjs`, `ui2_waypoint_acceptance.cjs`. Their separate
six-profile routing/map-service fixture is unavailable. The 16 separately marked
Python integration tests remain deselected; nine existing NumPy warnings remain.
`map_editing_controls.cjs`, `map_minimalism_checks.cjs` and
`pr97_form_acceptance.cjs` are support modules exercised by their parent drivers,
not additional standalone passes. The former 19-driver aggregate counted the
form helper separately; this audit corrects the total to 18 genuine drivers.

The supplied source PNG, optimized/runtime PNG, production mascot and launcher
artwork retain their verified hashes. The consolidated staging artifact passed exact bundled bytes/allowlist, build
identity, certificate continuity, ZIP integrity, APK page alignment and ELF LOAD
alignment checks. Its receipt is separate from the installed-device identity.

- Prepared APK: `artifacts/sugarglider-SG-AI-Test-cda0572.apk` under the external
  `/home/pompote/sugarglider-ai-mobile-2026-10-26` artifact root; **installed after explicit approval**.
- APK SHA-256: `f19a1a255d131870a7a8f475cde54068ba313ae6c49507fcd427bf60b2e8a7ce`.
- Size: 26,893,257 bytes; same staging package, version/code and signer as the
  installed app. All 156 declared bundled web files match exact source/input bytes.
- Native library SHA-256:
  `09b6d312b19caa5410561b804213641f5f8a772d1b3db570cc17bac8a55fb878`.
- Supplied original PNG SHA-256:
  `3af185b15de9cd2b8112a3f4e717720e1b805972d34be141fcae28088045e0a5`.
- Optimized and byte-identical runtime PNG SHA-256:
  `5a0202fe8e016dadb15aada780b4fb6b6ae1514ac26d9ffba6640046528613b2`.

## GitHub merge record

PR #111 merged only after all seven head checks completed successfully: three
push workflows and four PR workflows. Reviews/threads had no unresolved blocker.
The four push workflows on the actual merged main SHA also completed successfully.
The browser workflow used a full unchanged retry after slow Ubuntu package-mirror
downloads during tooling setup; no test was skipped.
The local main ref was fast-forwarded from its stale historical head. Main requires
pull requests, so the completed receipt follows through a documentation-only PR.

| Post-merge workflow | Exact run | Result |
|---|---|---|
| Python checks | [40483591684](https://github.com/victorgabillon/sugarglider/actions/runs/40483591684) | success |
| Android checks | [40483591608](https://github.com/victorgabillon/sugarglider/actions/runs/40483591608) | success |
| Elevation browser regressions | [40483591530](https://github.com/victorgabillon/sugarglider/actions/runs/40483591530) | success |
| Social deployment | [40483591582](https://github.com/victorgabillon/sugarglider/actions/runs/40483591582) | success |

Full head-check receipts, both code-merge parents, exact code-merge tree,
web/native/brand tree equivalence through main `36c023a`, source and device
receipts are retained in the external audit root. The documentation branch
incorporates PR #114 before merging and preserves its changes. PR #112's final
head and post-merge receipts are recorded separately outside Git; documentation
changes trigger three workflows because Social deployment excludes this path.
The owned source worktree is clean at handoff. No source rewrite or duplicate
forest merge was used to reach this state.

## Outstanding acceptance and limits

- A final live ChatGPT forest-adventure request requires separate account-inference
  authorization. No live request was initiated for this audit or CI.
- The existing manual draft is volatile across cold WebView/process recreation;
  full-state backups remain necessary. Exact adventure recovery is separate and
  remains implemented/tested.
- Native Privacy at font scale 2.0 is now physically verified on cda0572 in
  portrait. Landscape and broad map/CSS 200% coverage remain browser/native-layout
  regressions. The earlier doubled-CSS Parcours label wraps but remains operable.

No Google Play upload, production replacement, public regional publication,
unapproved app deletion or modification of the forest checkout/processes occurred.
