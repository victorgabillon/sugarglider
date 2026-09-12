# Android V1 — first goal-pass handoff

Recorded 2026-09-12. **V1 BLOCKED — approved regional distribution and final
production-region/device acceptance remain open; publisher/privacy/signing
decisions are deferred.** This is the completed implementation/preparation pass,
not a declaration that the global V1 acceptance criteria pass. The user has
explicitly requested that open questions be collected for later and that the app
**not be published to Google Play**.

The code, tests, unsigned AAB pipeline, prepared regional data and deployment
instructions are reviewable. No app upload, public region release, account,
paid service, domain or permanent signing key has been created. Remaining
milestones stay draft because the original physical/merge gates still apply.

## What the implementation does

The Android APK bundles the shared web planner at
`https://appassets.androidplatform.net`. Ordinary startup needs no development
server. Shared JavaScript owns bounded search, candidate publication, map display
and GPX; a narrow exact-origin/main-frame Android bridge supplies local Valhalla,
native regional downloads and the system document picker. Debug and release
compile the same production routing factory and native library.

One committed regional context binds a plan to its map, routing archive, local
places and nature. The regional screen coordinates their independent verified
downloads, stages a version before activation, retains valid data after failed
updates/cancellation, and offers explicit recovery/removal. Missing or damaged
data and outside coverage remain failures. There is no server routing fallback,
straight-line fallback or cross-region stitching. The prepared catalog currently
shows the region with **Download unavailable**, because no host is approved.

Both normal Generate modes publish the canonical immutable product objects used
by candidate selection, maps, snapshots and GPX. Waypoint Route allows at most
16 native calls; Auto Tour at most 24, including at most six POI calls after its
no-POI control. Gateway caches and diagnostics retain explicit public profile
identity. GPX serializes the selected result without another routing call, as one
track/segment with validated deliberate waypoints and no analysis extensions.

The six public profiles are `hike`, `trail_run`, `city_bike`, `gravel_bike`,
`mountain_bike` and `road_bike`. They are preferences over mapped data, not
condition/access/safety guarantees. Elevation is disabled. Exact repetition,
backtracking and unavailable path-detail facts remain unknown; missing evidence
cannot authorize POI promotion.

The current local subset is deliberately narrower than the reference server:

- Waypoint Route supports fixed/bounded optimized ordering, exact interior points,
  Shortest, nature off and loop-geometry preference off. Hard maximum gates remain.
- Auto Tour supports a fixed-start loop with indexed scenic/water and nature
  preferences. Interior mandatory points, imported soft stops, open tours and
  custom excursion allowances currently fail explicitly.
- Native reversal, map-wide local POI discovery, detailed native nature coloring
  and full low-overlap/loop-geometry analysis are not connected. Their absence is
  visible and does not trigger a server retry.

See [normal planning](pr41-normal-local-planner.md),
[native routing](pr41-production-native-routing.md),
[regional product](pr42-region-product.md) and the chronological
[readiness ledger](v1-readiness.md) for exact contracts and historical evidence.

## Milestones and review history

| Milestone | GitHub work | State at handoff |
| --- | --- | --- |
| PR40 local Auto Tour / places / nature | [#39](https://github.com/victorgabillon/sugarglider/pull/39), merge `d129c22` | Required PR40 tests and real Marly phone acceptance passed; merged |
| PR43 social-only service | [#40](https://github.com/victorgabillon/sugarglider/pull/40), merge `5be5780` | Code/container/HTTPS/backup checks passed; merged; public host unconfigured |
| PR42 measured production region | [#41](https://github.com/victorgabillon/sugarglider/pull/41), `86cf7e0` | Separate data-build worktree; verified Yvelines data; phone/distribution gates open |
| PR41 canonical export and normal Android planner | [#43](https://github.com/victorgabillon/sugarglider/pull/43) → [#44](https://github.com/victorgabillon/sugarglider/pull/44) → [#45](https://github.com/victorgabillon/sugarglider/pull/45) → [#46](https://github.com/victorgabillon/sugarglider/pull/46) | Dependent draft stack; shared production router and bundled startup implemented |
| PR42 verified regional installation | [#47](https://github.com/victorgabillon/sugarglider/pull/47) → [#48](https://github.com/victorgabillon/sugarglider/pull/48) → [#49](https://github.com/victorgabillon/sugarglider/pull/49) → [#50](https://github.com/victorgabillon/sugarglider/pull/50) → [#51](https://github.com/victorgabillon/sugarglider/pull/51) → [#52](https://github.com/victorgabillon/sugarglider/pull/52) | Dependent drafts; storage, bridge, UI and static publication tooling implemented |
| PR44 production hardening and security | [#53](https://github.com/victorgabillon/sugarglider/pull/53) → [#54](https://github.com/victorgabillon/sugarglider/pull/54) → [#55](https://github.com/victorgabillon/sugarglider/pull/55) | External signing/privacy configuration, lifecycle recovery, patched MapLibre and region feedback implemented |

Old independent [#42](https://github.com/victorgabillon/sugarglider/pull/42) is
superseded preparation. Do not merge/cherry-pick it wholesale: its obsolete
release-router/debug boundaries would undo production integration. The required
pieces were selectively integrated into #46/#53. Its branch/worktree remains
preserved. No draft has been merged past an unmet acceptance gate.

## Production region and distribution

**Yvelines et ouest parisien** is the measured first offering, with bounds
`[1.445097, 48.38, 2.25, 49.1]`; this is a rectangle, not an administrative or
connectivity guarantee. Build ID:
`1bbf598d64f5d5cc987a60f9a4cb22318392d596ff88f3eb6b40cb70dceb4691`.

| Component | Stored/download bytes |
| --- | ---: |
| Offline map | 81,571,296 |
| Native routing archive | 96,051,200 |
| Places | 108,248 |
| Nature | 10,634,994 |
| Three manifests | 3,130 |
| Total regional files | **188,368,868** |

The real region passes build verification and the bounded production index reader:
2,153 places and 62,191 nature features / 1,450,033 positions. The measured build
took 48 min 35 s while reusing an independently verified nature build; summing all
component work is about 56 min 6 s. Host hash/decode + indexing took about 10.4 s,
peak RSS 661,268 KiB. These are **host measurements**. Phone installation time,
minimum/peak free storage, update storage and route latency remain unmeasured for
this production region. The 188.4 MB payload is not a free-space guarantee.

Full Île-de-France was actually built and measured: 592,588,177 bytes and
4,170,750 nature positions. It exceeds the unchanged two-million-position consumer
limit, so it is not offered. The Yvelines build/specification evidence remains in
the #41 worktree at
`/home/pompote/oldata/victor/sugarglider-v1-pr42-region/docs/pr42-production-region-measurement.md`.

The prepared publication ZIP is 188,374,659 bytes, with deterministic contents,
checksums, attribution, catalog and confined extraction. The proposed separate
public GitHub repository/Release asset/Pages workflow is still inactive. Its
current limits, licensing notices, HTTPS/CORS requirements and exact deployment
steps are in [static distribution](pr42-static-distribution.md). Files go to
static hosting, never through FastAPI; no regional data enters Git.

## Physical acceptance: evidence and limits

Fairphone 6, API 36, WebView 151; the user resolved USB authorization. Test APKs use
the separate `.debug` package. The existing Play-installed main package, code 1 /
name 0.1.0, is untouched. No `pm clear`, radio/hotspot change, real location
publication or permanent signing-key operation was performed.

| Scenario | Evidence | Remaining limit |
| --- | --- | --- |
| PR40 local nature/POI Auto Tour | Real Marly data, deterministic repeat, native geometry, zero observed network; required milestone passed | Development region/earlier build |
| Normal Waypoint Route | Shared-engine Marly: hike 2,361 ms / city bike 304 ms, one call each, 4,226 / 4,249 m | Production region and final release package pending |
| Normal Auto Tour | Shared-engine Marly: hike 1,136 ms / city bike 1,088 ms, six/eight calls, two candidates each; repeated geometry/order unchanged | Production region and final release package pending |
| Graph-valid GPX | Real system Cancel and Save, 518 points / 22,717 bytes, exact Python XML equality, no reroute | Earlier Marly build; final region pending |
| Outside coverage | Explicit single native failure, unchanged request and no routing API retry | Earlier Marly build; final region pending |
| Current bundled first launch / no region | Visible normal page and finished `regional_required`; Generate disabled | Consumer download remains unavailable |
| Privacy and rotation | Readable local Privacy, same page/edit retained; portrait/landscape and original rotation restored | Patched preceding build; final public policy link absent |
| Keyboard | Focused distance field stays above keyboard; viewport 709 → 430 → 709 CSS px | Same native inset code as current build |
| Current renderer loss | Empty renderer deliberately crashed; native process survives; readable recovery; explicit Reopen works | No active route, GPX or sharing session tested in this crash |
| Current background/resume | Empty planner retains page sentinel and PID 5760 after Home/reopen | No active route/sharing or installed production region |
| Current process restart | Only empty debug process stopped; PID 7555 restarts bundled origin, no-region truth, no sharing | No data reset; installed-region persistence still pending |
| Production download / activation / map / cancel / remove / reinstall / offline restart | Real browser product/OPFS/worker tests pass | Required physical run awaits approved downloads |
| Permission denial / location disabled / screen-off sharing / social HTTPS | Existing architecture and browser coverage; prior native lifecycle tests | Final physical matrix and approved social endpoint remain open; no device-setting change inferred |
| Signed update / 16 KiB runtime / large-screen launcher | Disposable signing, delivered APK signature and binary/ZIP alignment pass | Existing-key update and compatible runtime/device acceptance pending |

The four normal-page desktop tests use a disclosed synthetic native adapter;
they prove UI/canonical map/GPX integration, not Valhalla graph or physical
acceptance. Backend-isolated phone checks are not described as radio-off tests.
See the detailed [device/store matrix](pr44-store-acceptance.md).

## Automated validation and current artifacts

For application source commit **`05b77baedcd203345101e5d39536a8bb68d6f3e4`**:

- `make check`: **1,055 passed**, 16 existing integration tests deselected; Ruff
  and strict mypy pass. No skip/xfail was introduced to hide failure.
- Twenty-one relevant browser harnesses: **366 cases pass**. Six additional UI
  harnesses previously passed 114 cases before the focused status-only fix:
  480 applicable passing cases across those runs, not a claim of one fresh
  480-case invocation. The real-page synthetic adapter passes four additional cases.
- Canonical cross-language validation: 51 complete results, 30 submitted native
  fixtures, 16 diagnostics and 60 exact GPX comparisons pass.
- Android `testDebugUnitTest lintDebug testReleaseUnitTest lintRelease
  assembleDebug assembleRelease bundleRelease`: **196 tests per variant**, zero
  failures/errors/skips, full build 4 min 42 s. Lint has zero errors and only the
  existing two debug / one release warnings (development cleartext/ARM64 coverage).
- All 103 packaged shared assets and the sole ARM64 library match source in APK
  and AAB. Official bundletool 1.18.3 validates the current unsigned AAB.
- MapLibre's actual previous 4.7.1 bundle fails the attribution exploit regression;
  official 6.4.1 passes all four security/worker cases. Package integrity is verified.
- Source `git diff --check` passes. GitHub #55 at `05b77ba` passes all five checks;
  final documentation-only follow-up CI is available on the linked PR.

External signing configuration validation, a disposable signed AAB, bundletool
universal APK construction, `apksigner verify`, `zipalign -c -P 16 4` and native
ELF LOAD alignment passed during this pass. The temporary signing secrets were
deleted. This verifies the pipeline; it does not supply the existing Play app's
upload identity or prove a 16 KiB runtime.

Artifacts are retained outside Git in:
`/home/pompote/oldata/victor/sugarglider-v1-artifacts/2026-09-12-05b77ba/`.
`manifest.json` and `SHA256SUMS` identify the exact copies.

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| `sugarglider-1.0.0-code2-unsigned.aab` | 47,496,095 | `88c9cb2aecb96553bbc2387b53b8c10281388021adb9df7dedb1d60328d6b691` |
| `sugarglider-1.0.0-code2-debug.apk` | 151,938,674 | `ad83ccb0a4c39e6031acf8606fd451e76037f88c02eedce77af68519ccafe8fa` |
| `sugarglider-regions-static.zip` | 188,374,659 | `40990c600c0b7bf934522daef1c92d7db44d0ab890077e1224084a6244476a9f` |

The AAB is **unsigned** and is not upload-ready. Its copy under the usual ignored
`android/app/build/outputs/bundle/release/app-release.aab` may change on the next
build; use the preserved copy and hash for this evidence. The debug APK must not
replace the Play-installed main application.

## Server, release policy and privacy

The optional production service is one Python application with SQLite behind
Caddy HTTPS. It stores exact shared snapshots, independent outing routes, current
positions and bounded reconnect replay. It has no routing engine, regional build
or bulk-download endpoint. The supplied deployment includes resource/request
limits, restricted logs, health/readiness, expiry cleanup and backups excluding
all live-position/replay rows. Real local HTTPS/container/restart/backup tests
passed. See [deployment and recovery](pr43-social-production.md).

Cost drivers are a small persistent host, snapshot storage, encrypted backups and
shared-content/SSE bandwidth. Generating 100 routes adds zero server routing CPU;
region download bandwidth belongs to static hosting. No provider price, production
capacity or public deployment is claimed.

The official policy audit was refreshed on 2026-09-12: compile/target API **36**,
minimum API **26**, ARM64. Current standard new-app/update target requirements are
met. Version **code 2 / name 1.0.0** is proposed, subject to the existing app's used
track versions. Release is non-debuggable, HTTPS-only, backup-excluded across the
configured domains, and uses external signing and an optional public policy URL.
MapLibre is patched for GHSA-jrc7-96c5-q579. Direct dependency queries found no other
matching advisory; they are not a complete embedded-native/OS security audit.
The vendor JNI still emits generic SDK/exception messages; the bounded synthetic
log check found no fixture coordinates but does not prove every failure path.

The merged release manifest has exactly six permissions: Internet, coarse and
fine location, foreground service, location foreground service, and notifications.
There is no `ACCESS_BACKGROUND_LOCATION`, storage, boot, advertising ID or wake
lock permission. Native location sharing starts only after an explicit visible
Start, disclosure and precise-location/notification permission; a private location
foreground service and ongoing Stop notification support the existing optional
screen-off outing feature. It never auto-starts after process death/reboot. Google
may still require background-location review for this use case; absence of the
background permission is not an exemption or approval.

The [privacy/Data Safety draft](pr44-privacy-data-safety.md) inventories precise
location, route snapshots, participant identifiers/content, capabilities, static
host metadata, logs, local pending samples and backups. Defaults: snapshots 90
days, outings 30 days, current positions stale at two minutes/expire at one hour,
replay at most 15 minutes/1,000 events, backup retention seven days with no live
rows. No analytics/advertising integration was found. The local Privacy dialog
is implemented; a final public policy link, provider details and publisher
declarations are still absent. Official policy links and the 28-second disclosure
demo shot list are in the linked privacy and store documents; recheck before upload.

## Open questions to answer later

No reply is required during this pass. These are the remaining external decisions,
in the order that unlocks the next work:

1. **Where should people download regions?** Approve the prepared free public
   `victorgabillon/sugarglider-regions` repository/Release asset/GitHub Pages proposal,
   or name an existing HTTPS static host. Nothing has been published. Once chosen,
   verify the real download/CORS/checksum contract, enable the catalog URL, and run
   the complete Yvelines phone matrix before claiming consumer readiness.
2. **Who publishes the app, and how can users contact them about privacy?** Supply
   the public publisher name and contact, then choose where the prepared privacy
   page should be publicly readable. The privacy-policy URL is simply that page's
   HTTPS address. Final named hosts/retention must match the actual deployment.
3. **How is the existing Play app signed?** Its upload key is the publisher's
   signing credential for updates, distinct from a chat password. Confirm the
   existing Play App Signing/upload-key setup and highest used version code across
   all tracks. If an external signing-properties file already exists, supply only
   its path; never send passwords or private-key material. Exact steps are in
   [signing and bundle preparation](pr44-signing-and-bundle.md).
4. **Where should optional sharing/outings run?** Name an approved server/domain
   and encrypted backup destination, or leave this optional endpoint unconfigured
   for the next local-planner test. Provider-neutral deployment is ready; public
   HTTPS/social acceptance needs an actual destination.
5. **Before any later Play submission:** the publisher must review Data Safety,
   location/foreground-service declarations, audience/content rating, ads/app
   access, listing, screenshots and review/demo material. Confirm the existing
   app identity and review any Console findings. Upload/publication remains a
   separate explicitly authorized future action.

The remaining device checks are work for the next acceptance pass, not policy
answers to invent: real download/activation, storage/time measurements, all six
profile identities and truthful route outcomes, pedestrian/bicycle Waypoint and
Auto Tour, POI/nature behavior, deterministic repeat, isolated-backend restart,
map/GPX, cancellation/interruption/remove/reinstall, final permission/sharing
lifecycle, compatible signed update and 16 KiB runtime. Preserve the phone's
existing Play app, user data and hotspot. No destructive test is required now.

## Submission sequence and repository handoff

1. Resolve distribution, perform the remaining physical checks and fix any
   discovered code issue; run the documented automated checks on the exact source.
2. Review/merge the dependent drafts in order only after their criteria, CI,
   physical gates, scope and GitHub mergeability pass. Integrate the independently
   measured #41 build/specification changes deliberately; never import generated
   data or obsolete #42 implementation wholesale.
3. Supply approved privacy/public configuration and the existing external upload
   identity; build the final AAB, verify its certificate, bytes/hash, bundletool
   output and delivered APK/runtime behavior. Do not substitute the debug key.
4. Complete publisher declarations and final screenshots/video; when separately
   authorized, use the existing Play app's internal testing/pre-launch process,
   resolve actual findings, then seek authorization for publication. No such
   upload or publication occurs in this pass.

The working branch is `fix/pr44-region-readiness-feedback`, draft #55. Application
source is `05b77ba`; subsequent handoff-only documentation commits do not change
the preserved artifacts. `main` and `origin/main` remain
`d129c22a808c0031c0bb09174ecbc5c22dfbda8d`. The other draft branches and separate
PR42/old PR44 worktrees remain preserved, with their status explained above.
Tracked changes are committed/pushed before handoff; final CI/working status is
recorded in the ledger and final response.

`Continue,` and `native` were never read, modified, staged, moved or deleted.
Protected `stash@{0}` remains
`6abe302207f4336b04e3a050966c263c218393a1`,
`On fix/spur-rejoin-snapped-endpoints: experimental Marly-Trianon route requests before PR22`.
Generated data, APK/AAB/GPX, screenshots and all signing material stay out of Git.
No owned USB forwarding, temporary test server or tracking session is left active.
