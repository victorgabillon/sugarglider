# Mobile AI experience and Android installation inventory

Work is isolated on `feat/ai-mobile-experience`, based on PR #110 at
`88bdb8c674e3cbbfbb51c8595d9b04fc3a9ac968`. The forest-search checkout and branch
are untouched. No phone installation, launch, force-stop, disabling, uninstall,
permission change or app-data access was performed. Production and publication
are unchanged.

## Phone inventory, 26 October 2026

Read-only ADB inventory found 24 related packages: 13 launchable apps and 11
non-launcher instrumentation helpers. Eight launchable audit clones share the
same full **Sugarglider V2 Staging** label. Android's launcher truncation therefore
cannot identify a package. Staging had a running process; none of the audit apps
was running at the process snapshot. The foreground snapshot showed another app,
so it does not identify which Sugarglider app appeared in the user's earlier
screenshot.

The device reports 1116 × 2484 physical pixels at density 480 (372 × 828 dp before
system bars). Browser evidence uses a representative 372 × 760 WebView viewport,
390 × 844, 800 × 372 landscape, and 1280 × 844; it does not establish the exact
physical WebView insets. Large-text evidence uses 200% root text sizing.

All installation/update times below are the device's reported values; no timezone
conversion is inferred. Labels are the APK's full application labels. Test helpers
have no application label or launcher activity. Package contents were copied
read-only to calculate hashes and inspect public manifest/signing metadata, then
the temporary local APK copies were removed. App-private data was not read.

| Package | Purpose | Recommendation |
|---|---|---|
| `io.github.victorgabillon.sugarglider` | Production | Keep; public app |
| `io.github.victorgabillon.sugarglider.debug` | Debug | Assess; retain until experiments and stored data are accounted for |
| `io.github.victorgabillon.sugarglider.placesrealdata` | Places real-data experiment | Assess; retain until experiments and stored data are accounted for |
| `io.github.victorgabillon.sugarglider.v2auditb1` | Audit | Potential cleanup after explicit authorization and data review |
| `io.github.victorgabillon.sugarglider.v2auditb2` | Audit | Potential cleanup after explicit authorization and data review |
| `io.github.victorgabillon.sugarglider.v2auditf1` | Audit | Potential cleanup after explicit authorization and data review |
| `io.github.victorgabillon.sugarglider.v2auditf2` | Audit | Potential cleanup after explicit authorization and data review |
| `io.github.victorgabillon.sugarglider.v2auditn1` | Audit | Potential cleanup after explicit authorization and data review |
| `io.github.victorgabillon.sugarglider.v2auditn2` | Audit | Potential cleanup after explicit authorization and data review |
| `io.github.victorgabillon.sugarglider.v2auditn3` | Audit | Potential cleanup after explicit authorization and data review |
| `io.github.victorgabillon.sugarglider.v2auditp1` | Audit | Potential cleanup after explicit authorization and data review |
| `io.github.victorgabillon.sugarglider.v2debug` | Research | Assess; retain until experiments and stored data are accounted for |
| `io.github.victorgabillon.sugarglider.v2staging` | AI Test / V2 Staging | Keep; main AI testing app, update in place only after authorization |

The staging app is the user's reported owner of the original 23.172 km route and
ChatGPT connection. Its installed APK SHA-256 is
`bc17d1d8ef48fbae6c885361d71557bf2c3fe72247605de304bbb27b50d97796`, matching
PR #110's recorded physical-acceptance receipt. That older APK has no packaged
source-revision display; a launcher label alone does not prove its source commit.
All other packages may also hold data. Their data-preservation status is **unknown**.

**Minimal cleanup proposal, not executed:** keep production and `.v2staging`.
First replace staging in place with the reviewed, integrated APK using the same
application ID and signing certificate; this retains its own app storage and
makes it recognizable. Then, only after explicit authorization naming packages
and confirming their data can be discarded, remove these eight audit apps:

- `io.github.victorgabillon.sugarglider.v2auditb1`
- `io.github.victorgabillon.sugarglider.v2auditb2`
- `io.github.victorgabillon.sugarglider.v2auditf1`
- `io.github.victorgabillon.sugarglider.v2auditf2`
- `io.github.victorgabillon.sugarglider.v2auditn1`
- `io.github.victorgabillon.sugarglider.v2auditn2`
- `io.github.victorgabillon.sugarglider.v2auditn3`
- `io.github.victorgabillon.sugarglider.v2auditp1`

Do not include Debug, Research or `.placesrealdata` automatically. The 11 `.test`
helpers have no launcher icons, so removing them is unnecessary for launcher
cleanup and may affect instrumentation. Future audit builds retain an explicitly
launchable MainActivity but omit the LAUNCHER category, avoiding new drawer icons.
This does not hide already installed audit APKs retroactively.

## Exact APK metadata

Certificate **P** (production):
`2ffa87378fe9c275494599029e238dd898c3fe684f979b6dd34082dc24e9f4a1`.
Certificate **D** (all development and helper packages):
`e84155df3a2c7ea48723876b1fe8e0e602cb600f8374d6539b9fea9aa42cfbd7`.

| Application ID | Full label | Version (code) | First installed | Updated | Cert | APK SHA-256 |
|---|---|---|---|---|---|---|
| `io.github.victorgabillon.sugarglider` | Sugarglider | 1.2.0 (8) | 2026-08-28 14:47:34 | 2026-10-13 11:09:24 | P | `a20ddfab268e02b559a7edc676ae94cfd6054085c4b11952f96403bf03a8f29d` |
| `io.github.victorgabillon.sugarglider.debug` | Sugarglider Debug | 1.2.0-debug (8) | 2026-10-06 13:46:57 | 2026-10-14 18:29:32 | D | `e8c2e1f2d6a6a6b8c53412bf64a0edeb121b491c4e9e4a89e8f0812b7b97fe3f` |
| `io.github.victorgabillon.sugarglider.debug.test` | No application label / no launcher | null (0) | 2026-10-14 18:11:25 | 2026-10-14 18:29:34 | D | `a0a9ab204dfe052db5d6595bd4718b547d05eab58221d3cf7d011740ad4a0186` |
| `io.github.victorgabillon.sugarglider.placesrealdata` | Sugarglider Debug | 1.0.2-places-real-data (4) | 2026-09-21 16:32:20 | 2026-09-21 16:32:20 | D | `b9ae14b08b13ac4c8e006516121e932608d0aef7c695e6655fbf796703ed1db1` |
| `io.github.victorgabillon.sugarglider.v2auditb1` | Sugarglider V2 Staging | 1.2.0-v2-staging (8) | 2026-10-18 20:50:59 | 2026-10-18 20:50:59 | D | `ee991904db74604258cbe9aaa1f1e9c5292794c47b6f9e70f23200da5b1ad320` |
| `io.github.victorgabillon.sugarglider.v2auditb1.test` | No application label / no launcher | null (0) | 2026-10-18 20:51:00 | 2026-10-18 20:51:00 | D | `6c127eacfd6172dcd6a1ccef30bc94e06b8185e14f4bb40fc464af74926861a3` |
| `io.github.victorgabillon.sugarglider.v2auditb2` | Sugarglider V2 Staging | 1.2.0-v2-staging (8) | 2026-10-18 20:57:29 | 2026-10-18 20:57:29 | D | `2ac90b7cb430a4d114e354351b4c0cd54194e4d7046248dd2d4e0530c2e662c1` |
| `io.github.victorgabillon.sugarglider.v2auditb2.test` | No application label / no launcher | null (0) | 2026-10-18 20:57:30 | 2026-10-18 20:57:30 | D | `0eccd5239d55993fc9320e0b0791bcfac53439902a8070cbdaead0b627635734` |
| `io.github.victorgabillon.sugarglider.v2auditf1` | Sugarglider V2 Staging | 1.2.0-v2-staging (8) | 2026-10-18 20:55:27 | 2026-10-18 20:55:27 | D | `c43f38b709880585ae204d2c0ad2e52bcf2d76ff23d794a2444d30498578b787` |
| `io.github.victorgabillon.sugarglider.v2auditf1.test` | No application label / no launcher | null (0) | 2026-10-18 20:55:28 | 2026-10-18 20:55:28 | D | `7de5aa819578e5f41fe6b04e1c7dcd4a3490c5a9f412f924c0e13185fc408804` |
| `io.github.victorgabillon.sugarglider.v2auditf2` | Sugarglider V2 Staging | 1.2.0-v2-staging (8) | 2026-10-18 20:59:54 | 2026-10-18 21:35:43 | D | `0e4788fcd42e186c3e486f615b57e99299841c84afa78f1a11428b5a744f05b1` |
| `io.github.victorgabillon.sugarglider.v2auditf2.test` | No application label / no launcher | null (0) | 2026-10-18 20:59:55 | 2026-10-18 21:35:44 | D | `d1b739929262fb7a9f2af3ca9ac117d9445df6eb0a77a1dc73bcb3bbe4cd3c26` |
| `io.github.victorgabillon.sugarglider.v2auditn1` | Sugarglider V2 Staging | 1.2.0-v2-staging (8) | 2026-10-18 22:55:54 | 2026-10-18 23:23:36 | D | `ff2a6f20a9ee09436a398643e7128528c7fc139b6788f5b11d7f94ad0ac0c64d` |
| `io.github.victorgabillon.sugarglider.v2auditn1.test` | No application label / no launcher | null (0) | 2026-10-18 22:55:55 | 2026-10-18 23:23:37 | D | `fc776a9aa07c71f59818f4577b9f7a3298c31d4959611d3c671ba4d813523485` |
| `io.github.victorgabillon.sugarglider.v2auditn2` | Sugarglider V2 Staging | 1.2.0-v2-staging (8) | 2026-10-19 10:19:18 | 2026-10-19 10:19:18 | D | `add52c04eab108f55459a85ecd87a724d9899b36f8e745e49f12ab00fd6d291d` |
| `io.github.victorgabillon.sugarglider.v2auditn2.test` | No application label / no launcher | null (0) | 2026-10-19 10:19:19 | 2026-10-19 10:19:19 | D | `abc61fc8780b011e179c7c6a8257c20e27f89eb52882e542b52f8451237fbdd2` |
| `io.github.victorgabillon.sugarglider.v2auditn3` | Sugarglider V2 Staging | 1.2.0-v2-staging (8) | 2026-10-19 10:22:04 | 2026-10-19 10:22:04 | D | `2404ef859df4c0a71535204d7931da18e308e774ff64e29143f4f84e271b9b33` |
| `io.github.victorgabillon.sugarglider.v2auditn3.test` | No application label / no launcher | null (0) | 2026-10-19 10:22:04 | 2026-10-19 10:22:04 | D | `91cfffe023f6b021e8a0201d1baca43d9e0dbfbe9a8007bad21e3e1660663f4d` |
| `io.github.victorgabillon.sugarglider.v2auditp1` | Sugarglider V2 Staging | 1.2.0-v2-staging (8) | 2026-10-19 14:47:06 | 2026-10-19 15:08:06 | D | `d6abb811b53a5b6ef5fc96b3ba5b5843b52f9eca27f4cdbe844755d385fabbbf` |
| `io.github.victorgabillon.sugarglider.v2auditp1.test` | No application label / no launcher | null (0) | 2026-10-19 14:47:07 | 2026-10-19 14:47:07 | D | `d0e65467c115ff730eb55835bee021a4eaee130778c3a2192f9226ffca520dc4` |
| `io.github.victorgabillon.sugarglider.v2debug` | Sugarglider V2 Research | 1.2.0-v2-research (8) | 2026-10-15 13:57:21 | 2026-10-16 13:51:58 | D | `e635d160574ade24e710924118cf6ebf7a7f2fe074d5fcf9af2f915dee97c02a` |
| `io.github.victorgabillon.sugarglider.v2debug.test` | No application label / no launcher | null (0) | 2026-10-15 13:57:22 | 2026-10-16 10:08:37 | D | `f27d025e5e04cbd78beaa29e832af91eb7bef8455144dc7f9d37afed3acf25ba` |
| `io.github.victorgabillon.sugarglider.v2staging` | Sugarglider V2 Staging | 1.2.0-v2-staging (8) | 2026-10-16 16:35:01 | 2026-10-26 11:47:32 | D | `bc17d1d8ef48fbae6c885361d71557bf2c3fe72247605de304bbb27b50d97796` |
| `io.github.victorgabillon.sugarglider.v2staging.test` | No application label / no launcher | null (0) | 2026-10-16 16:35:02 | 2026-10-18 19:38:26 | D | `6d859a5ea4fff6d302768e61376419627ca43d4a61b24186bc4ba90b9b7faf66` |

## Delivered behavior

- The bundled planner's opening header has one obvious **Ask ChatGPT** action with the supplied purple route-bubble illustration
  (**Demander à ChatGPT** in French). Plan keeps the same entry. Both open the
  existing adventure dialog with one state lifecycle, preserved draft/Start/End,
  cancellation and focus return. Opening performs no inference, routing or recording.
- Empty-plan header Generate is removed from the packaged UI hierarchy. Manual
  Generate remains in Plan and appears in the map route dock when the request is
  ready. It invokes the same controller and availability checks. Non-Android web
  header behavior remains available.
- The dialog prioritizes editable wishes, a 48 px microphone action, connected
  ChatGPT status, and a prominent Generate adventure footer. Opening focuses Close
  so the Android keyboard need not cover speech before the user chooses typing.
  Account management, spoken language/provider, model/research/structured settings,
  endpoints and full disclosures remain available in secondary sections.
- The concise visible disclosure explains explicit online text/geographic-context
  processing. The complete existing disclosure remains expandable. A persistent
  missing-region message survives account refresh. Explicit speech-provider choices,
  native recognition and consent are preserved. French core labels are localized
  without a translation framework.
- The normal bundled planner attaches only its WebView below root-owned status-bar
  and cutout insets. Root still owns lateral, navigation and IME clearance. The
  native chrome branch remains for modes needing native sharing/server navigation.
  Resume and renderer recovery continue to rebuild/apply insets through the same
  activity lifecycle.
- Tools → Privacy opens the existing native `showPrivacyDetails()` dialog. Its
  published-policy button is still a separate deliberate external-link action.
  `show_privacy` is an argument-free, strictly parsed request behind the existing
  exact-origin, main-frame, current-WebView, page nonce and request ledger gates.
  It accepts no command, URL or arbitrary native method and makes no network request.
- Tools → App status lazily reads the packaged label, Git revision (with `-dirty`
  when applicable), variant and version. It never guesses a commit from the account,
  region or launcher icon. The response contains no private paths or account IDs.
- Development names are **SG Debug**, **SG Research**, **SG AI Test**, or a unique
  **SG Audit <suffix>**. Staging uses a separate small XML TEST badge layered over
  the original mascot resource. The canonical and production artwork is unchanged,
  and no bitmap copy or remote image is added. The staging package/signing identity
  remains compatible with an in-place update.

## Supplied AI icon supplement

The supplied `Downloads/image(10).png` is preserved byte-for-byte in
`assets/brand/sources/sugarglider-ai-planner-original.png`. Its transparent-margin
crop and proportional reduction are documented with source/output hashes in
`assets/brand/README.md`. The 256×194, 78,621-byte transparent canonical UI copy is
`assets/brand/sugarglider-ai-planner.png`; the web runtime is byte-identical.
Only the optimized copy enters the PWA shell and Android's 154-asset allowlist.
The original full-resolution image is not packaged.

Map and Plan show the illustration beside readable text; the shared dialog uses
the same illustration in its heading. French localization updates the label span
without replacing the image. Empty image alt text leaves the adjacent label as
the accessible name; the full button retains its touch target. There is no
replacement artwork, recolouring, mascot change, launcher change, new AI dialog,
authentication change, recording or inference on open.

The full-app browser acceptance verifies all three images decode from the local
bundled asset, remain contained in the Map button, and open the same dialog when
the image itself is tapped. French portrait/landscape, English mobile/desktop,
200% text, editable speech, route preservation and canonical GPX checks remain
in the same acceptance flow. Updated screenshots are outside Git under
`artifacts/ai-icon/`, including opening Map and connected/disconnected dialog.
Physical Fairphone screenshots and acceptance still require separately
authorized installation after the forest integration; no device state was changed.

## Attribution behavior and evidence

MapLibre GL JS 6.4.1's built-in responsive AttributionControl starts expanded and,
by default, minimizes on a map drag below 640 px. This explains why full credits
can remain on the initial map indefinitely without a drag; the screenshot's actual
package and cause cannot be proven retrospectively.

The implementation retains that control and its source-derived credits. On a
narrow map it displays full credits initially, then activates its existing summary
after five seconds. Deliberate expansion or keyboard focus cancels automatic
collapse. Visibility changes pause/restart the acknowledgement, and changed
active-source credits reveal a fresh interval. Wide maps keep the responsive
expanded presentation. The information target is 44 × 44 px, keyboard accessible,
and has an explicit screen-reader label and expansion state. A ResizeObserver
includes the real control height in route-dock clearance, including expansion,
wrapping and text scaling. Long expanded credits scroll in their own readable
pane while the information button stays reachable. No provider credit is removed,
hidden off-screen or substituted. Explicit point-placement guidance allows unrelated map
taps through while keeping its Cancel button interactive.

The default OSM credit now links directly to its copyright/ODbL page. Actual local
pack source notices remain verbatim; complete offline source/licence disclosures
remain available through the existing map data-source UI. This is a presentation
change, not a new tile service, cache, licence or data distribution.

Checked primary guidance:

- [MapLibre 6.4.1 AttributionControl source](https://github.com/maplibre/maplibre-gl-js/blob/v6.4.1/src/ui/control/attribution_control.ts)
  documents initial expanded responsive behavior and the built-in summary.
- [OSMF attribution guidelines](https://osmfoundation.org/wiki/Licence/Attribution_Guidelines#Interactive_maps)
  allow collapse after five seconds or map interaction, with discoverable licence
  access. This implementation preserves the initial acknowledgement and link.
- [ESA WorldCover usage and licensing](https://esa-worldcover.org/en/data-access)
  and existing installed-pack notices were checked; WorldCover, Natural Earth,
  Protomaps and additional pack credits remain available together.

Before/after PNGs are intentionally outside Git under the task's artifacts directory.
The baseline server reads immutable `88bdb8c` source without changing either
checkout. The comparison uses the same synthetic OPFS regional pack/credits and
French viewport. It is browser evidence, not a photographed or installed Android
acceptance. Screens cover initial/settled/expanded credits, disconnected/connected
ChatGPT, large text, landscape, active-region switching and missing-region readiness.
The browser link activation is intercepted locally, without contacting OSM.

## Validation and integration

The final local checks pass:

- `make check`: Ruff, strict mypy across 303 Python files, 1,612 tests; 16 live-service
  integration tests deselected and nine existing NumPy warnings.
- All 61 browser harnesses pass. All 19 self-contained acceptance drivers pass,
  including actual MapLibre, native-envelope fixtures, source switching, preserved
  manual state, endpoint adjustments, binary GPX export and exact restart recovery.
- Six legacy real-service drivers remain **unrun**, not passed:
  `automatic_intent_acceptance.cjs`, `itinerary_draft_acceptance.cjs`,
  `location_search_acceptance.cjs`, `route_dock_acceptance.cjs`,
  `ui2_request_acceptance.cjs`, `ui2_waypoint_acceptance.cjs`. They require the
  unavailable separate six-profile routing/map server fixture.
- Android JVM: Debug 289, Release 284, Staging 284 tests; zero failures, errors or
  skips. Debug/Release lint and assembly pass; staging lint and assembly pass.
  The audit manifest retains exported MainActivity, uses its unique AUDIT category,
  and generates `SG Audit mobile`; ordinary staging retains its launcher entry.
- Final staging source revision, APK/certificate hashes, exact packaged web asset
  comparison, native-library identity, private-input checks and 16 KiB alignment
  are retained in the external prepared-APK receipt. No changed APK is installed.

Principal source changes are in `android/app/build.gradle.kts`, MainActivity,
BridgeProtocol, BundledShellPolicy, variant manifests/labels and the two tiny
staging badge drawables; shared `index.html`, `app.js`, `adventure_dialog.js`,
`map.js`, `styles.css`, the shell-cache generation and default OSM attribution.
Browser and native gate tests cover the new entry points and changed layout.
Cached-asset identity assertions are synchronized with the new shell generation.
Canonical brand files, route search/ranking, credentials and regional data are
unchanged.

Final packaged identity and detailed test logs are recorded in the task's external
artifacts. The committed source and checks are independent of the still-active,
uncommitted forest-search lane. PR #110 must remain draft/unmerged until its own
acceptance requirements and the integrated checks are satisfied. No GitHub push/PR
or duplicate CI is needed before that integration revision is ready.

Remaining physical acceptance requires a separately authorized in-place staging
installation after integrating the committed forest revision: confirm the actual
status/cutout and gesture insets, keyboard, portrait/landscape, resume/Back/renderer
recovery, Tools Privacy, external licence links, launcher badge, retained 23.172 km
route/account, ChatGPT authentication and Android speech. No model request or
microphone test is authorized merely by this source/build preparation. No cleanup
package may be removed until separately authorized.

## Final bilingual GUI continuation, 26 October 2026

The Map header now uses only the existing supplied purple artwork in a compact
52 × 48 CSS pixel button. Its complete accessible name and tooltip are
“Planifier une aventure avec ChatGPT” / “Plan an adventure with ChatGPT”. Plan
retains a text entry into the same existing dialog. The original artwork and
production launcher resource remain unchanged. The separate staging TEST overlay
is inset so circular launcher masks do not clip its lettering.

French is the default independently of Android/browser language. Tools contains
one Langue / Language selector. A validated `fr`/`en` record uses the existing
PWA public-runtime store, with French fallback for absent, invalid or unreadable
preferences and an explicit session-only message when persistence fails. A
central complete-message dictionary and parameterized translation helpers cover
static declarations and explicitly bound dynamic UI messages. There is no
substring replacement of rendered HTML, external framework or extra database.
User prose, original geographical names, model stories, source URLs, licence
notices and canonical planning/GPX values stay original.

Switching updates the existing document and redraws presentation without a WebView
reload or new planning operation. Typed `set_ui_language` accepts only `fr`/`en`
behind the existing exact-origin, main-frame bridge and request ledger. Native
resources use that UI preference without recreating the Activity or WebView;
Privacy and speech-provider disclosures follow the selected language. Explicit
speech language and recognition provider remain independent. The interface
language supplies only the default spoken language and the language instruction
for a newly explicitly submitted AI request.

The focused full-app acceptance compares canonical requests, selected candidates,
result portfolios, all planner form values, settled map cameras and exact GPX bytes
across both language changes, including a displayed adventure. It counts native
routing, terrain, inference and microphone calls. French scenarios use an English
browser locale with no saved preference. Existing English UI fixtures now declare
English explicitly; their routing, capability, safety and byte-level assertions
remain strict. A separate localization harness covers default/fallback/persistence,
serialized writes, optional storage, parameters, accessibility and unchanged
user/place/story text. Browser screenshots and physical backups stay outside Git.

The refreshed physical inventory again found 24 related packages. Eight audit
clones were removed only after the user explicitly approved discarding each named
package's local data: `.v2auditb1`, `.v2auditb2`, `.v2auditf1`, `.v2auditf2`,
`.v2auditn1`, `.v2auditn2`, `.v2auditn3`, `.v2auditp1`, all under
`io.github.victorgabillon.sugarglider`. Their exact APKs, package/version/signing
identities and removal receipts are retained privately. Six had regional/browser
state; the other two had separate audit WebViews and diagnostics. No claim of
unique-data disposability was inferred from their labels or suffixes.

Production and canonical V2 staging were not removed or reset. The remaining
launcher-visible development packages `.debug`, `.v2debug` and `.placesrealdata`
are retained because their potentially valuable data has not been reviewed or
authorized for deletion. Eleven non-launcher instrumentation helpers remain.
See [the temporary audit workflow](android-audit-workflow.md) for fresh-package
ownership, non-launcher audit builds and mandatory session cleanup.
