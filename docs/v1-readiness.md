# Android V1 readiness

## Immutable outcome

Deliver a Google Play release candidate that installs normally, downloads at least
one useful supported region, and provides offline maps, six-profile on-device
Valhalla Waypoint Route and Auto Tour planning, local places/nature where supported,
and graph-valid single-track/single-segment GPX. Ordinary Android planning requires
no routing server. The optional production service owns immutable shared routes,
outings and latest-only live positions. No hidden network routing, straight-line
fallback, cross-region graph stitching, location history or false coverage claims.

The complete acceptance brief is the V1 Goal supplied on 2026-09-11. Each milestone
needs concrete automated and (where specified) physical evidence before merge.
PASS never means an author assessment alone. Superseded evidence stays identified.

## Starting evidence

- `git status --short`: only unrelated `?? Continue,` and `?? native`.
- `git branch --show-current`: `main`.
- `git log -3 --oneline --decorate`: main/origin/main at `15f3df3`, merge of
  GitHub PR #38 / conceptual PR39; implementation `0724d30`; previous merge `dd61f2e`.
- `git stash list --format='%gd %H %s'`: protected `stash@{0}` is
  `6abe302207f4336b04e3a050966c263c218393a1`, experimental Marly–Trianon requests.
- `AGENTS.md` and PR32–PR39 documentation read. Unrelated entries and stash must
  remain untouched throughout the goal.
- GitHub authentication is available. Fairphone USB detected but initially
  unauthorized; no physical PASS inferred from prior milestones.

## Milestones and gates

| Milestone | Status | Required success evidence |
| --- | --- | --- |
| PR40 local Auto Tour v2 / POI / nature | MERGED; REQUIRED PR40 CHECKS PASS | Validated local PR39 readers/storage; bounded deterministic search; real Fairphone nature/POI outcomes, repeat, native geometry and zero-network acceptance recorded below |
| PR41 production Android local planner | SHARED RELEASE ROUTER PACKAGED; FINAL RELEASE / REGION GATES PENDING | Normal release-equivalent Generate for Waypoint Route and Auto Tour; canonical display/export objects; pedestrian/bicycle device runs; no backend call; uncovered-region failure |
| PR42 region product | UI / COMMITTED REGIONAL PLANNER IMPLEMENTED; DISTRIBUTION / PHYSICAL GATES OPEN | Static catalog; verified failure-safe install/update/remove UI; useful measured region; fresh Fairphone install, restart, map, planning, cancellation and removal |
| PR43 tiny production service | CODE MERGED; LIVE HOSTING PENDING | Reproducible HTTPS/SQLite social-only deployment, limits, backups/recovery, graceful offline behavior; no routing dependency; public hosting remains an external action |
| PR44 Play release candidate | PREPARATION DRAFT; FINAL RELEASE GATES OPEN | Current official policy audit; release tests/lint/AAB; secret-safe external signing; permission/privacy/store documents; physical lifecycle/permissions/export matrix |

Global validation requires `make check`, Android unit tests/lint/release bundle,
relevant shared-web browser tests and `git diff --check`. No failing/skipped gates
may be hidden. Device results must state network isolation, exact build/data and
limitations; keep hotspot, Wi-Fi and cellular state intact and never use `pm clear`.

## PR40 audit and decisions

- PR35 uses shared web orchestration and sequential native `local_route` calls,
  at most 24. PR34 supplies continuous Valhalla geometry and snapped leg boundaries.
- PR35 has no local POI/nature consumption, no exact edge repetition or graph
  backtracking evidence. Geometric proximity must not populate those fields.
- PR39 already supplies independent gzip POI v2 and nature v1 files, manifest
  checksums, region bounds and source identities. Reuse these bytes and formats.
- Preserve and expose the best no-POI control. Missing exact repetition or
  backtracking evidence cannot authorize preference-based POI promotion.
- Release Valhalla remains disabled until PR41's deliberate audited integration.

Implementation/evidence is detailed in
[PR40](pr40-local-auto-tour-regional-evidence.md). Current automated evidence:

- `make check`: **991 passed / 16 integration tests deselected**, Ruff and strict
  mypy pass (229 source files). No skipped/xfail test was introduced.
- `JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
  ANDROID_HOME=/home/pompote/Android/Sdk make android-check`: **PASS**; 136 JUnit
  tests, zero failures/errors/skips; `lintDebug` passes. Initial attempts lacked
  the SDK environment and selected a compiler-less JRE; those environment failures
  were corrected without changing or weakening build/test configuration.
- `uv run --offline --with websockets python /tmp/sugarglider-pr40-browser.py`:
  **187 scenarios in ten harnesses PASS**, including 20 new PR40 scenarios, actual
  Chrome OPFS and a real module worker. Temporary driver/logs are outside Git.
- Real Marly host load: manifest and both component hashes valid; 407 POIs and
  6,734 nature features, successful bounded topology validation/index construction.
  This is data-reader evidence, not a substitute for physical planning acceptance.
- Internal review added ordered snap/geometry validation, invalidation draining,
  per-candidate POI outcomes, strict analysis accounting, worker failure handling,
  cancelled queued installs and optional-storage/cleanup failure isolation.
- `git diff --check`: PASS. Protected stash hash remains unchanged; `Continue,`
  and `native` have not been edited or staged.

GitHub [PR #39](https://github.com/victorgabillon/sugarglider/pull/39) originally
remained draft at `ca2fb51` pending physical acceptance. The current implementation
`c081878` passes all five CI jobs and GitHub reports it mergeable. The required
physical gate passed on 2026-09-11. Evidence update `dbf9900` passed all five CI
jobs and merged as `d129c22` on 2026-09-12 (merge commit). Main was refreshed;
the completed local/remote feature branch was removed. Protected untracked
entries and stash were verified unchanged.

After integrating main's PR43 merge into the PR40 feature branch (`e92b3b5`),
`make check` passes again: **1,022 passed / 16 existing integration tests
deselected**, Ruff and strict mypy pass (240 source files). This supersedes the
991-test Python total above for the combined branch; the earlier Android/browser
evidence remains identified with its original implementation.

A subsequent production-scale reader check raises only the installation topology
budget from 20 to 40 million operations, based on measured Yvelines data requiring
34.45 million operations / about 11.3 s parse+load / 420 MiB peak on the host.
The current reader accepts that component; the 2-million-position limit and
four-million-operation per-route analysis remain unchanged. `make check` passes
again (1,022 tests) and all 187 browser scenarios pass. Shell v25 delivers the
updated reader. These are component-only host measurements. The subsequent Marly device evidence
below passes PR40; a consumer-region installation remains a PR42 gate.

## PR40 physical evidence

Required Fairphone acceptance **PASS** at `c081878` / cached shell v25, using the
unchanged 144,132,773-byte debug APK, SHA-256
`ffcf4167db49da55f0b315d3d6503e9f6fa8da763ec6b868ff95afbbef5b5777`.
The actual UI installed the real PR39 Marly places/nature files; native archive
bytes separately matched their manifest. Phone API 36 / WebView 151.0.7922.199.

`uv run --offline --with websockets python
/tmp/sugarglider-pr40-phone-acceptance.py`: preferences off, preferences on and
identical repeat all pass with the temporary server stopped and USB reverse
removed. Native calls: 6 / 12 / 12 within 24; latency: 1,613 / 1,866 / 1,699 ms;
zero observed network requests in every run. Both native candidate geometries
matched their MapLibre sources. Nature partitions authoritative route distance,
unknown graph facts stay null, cache accounting is exact, and all six POI route
attempts report their loop-quality rejection without replacing the no-POI control.
Preference/repeat result digest (excluding only measurements/timing):
`84b91e6ba8483cc45f2e4a354eee9b0afc3fd26fb78c9d6985ec40d04ff59e51`.

[Full device evidence and limits](pr40-local-auto-tour-regional-evidence.md#fairphone-acceptance--2026-09-11)
records source/data/geometry hashes, exact requested fixture, honest POI outcomes,
the initial setup rendering failure and successful complete offline rerun.
Basemap was unavailable; route lines used a neutral background. No release UI,
bicycle, GPX or consumer-region device PASS follows from these PR40 runs.

## Independent PR43 evidence

Prepared from unchanged main `15f3df3` in an isolated checkout while the phone
was locked. GitHub [PR #40](https://github.com/victorgabillon/sugarglider/pull/40)
contains conceptual PR43 at `8a19b28`. All five CI jobs passed, including Android
and the new production-image checks; merged with commit `5be5780` on 2026-09-11.
Main was refreshed and the completed local/remote feature branch removed. The
detailed runbook is [PR43 deployment](pr43-social-production.md).

- `make check`: 1,011 passed, 16 existing integration tests deselected; Ruff and
  strict mypy pass (239 source files), including 31 new production social tests.
- Relevant browser harnesses: 94 scenarios pass (PR25 14, PR26 63, PR27 17).
- Locked nonroot container build, Compose/proxy validation and a network-disabled
  production-factory smoke pass. No routing process or regional data is required.
- Temporary HTTPS container acceptance passes snapshot/outing/live/SSE/GPX,
  restart persistence, exact stored candidates, absent routing endpoints,
  origin/query rejection, backup verification and private logs. Backups copy no
  live positions or replay events. Synthetic test volumes/networks were removed.
- Small-fixture measurement: 100 sequential HTTPS snapshot reads in 2.692 seconds;
  about 63 MiB application and 16 MiB proxy memory. This is not a production load
  guarantee. Report: `/tmp/sugarglider-pr43-acceptance-nukh9069/report.json`.
- Deployment, privacy-preserving logs, retention, seven-day backup timer and
  explicit restore instructions are prepared. No paid resource, domain or public
  service has been provisioned. Hosting destination question is pending.

## PR42 region measurement

GitHub draft [PR #41](https://github.com/victorgabillon/sugarglider/pull/41),
implementation `f81f951` with measurement update `0e919a0`, is preparing the
Île-de-France offering from main `5be5780`
in `/home/pompote/oldata/victor/sugarglider-v1-pr42-region`. It reuses the unchanged
PR39 formats and local source PBF, adds one matching region/map specification, and
caps build containers at 3,072 MiB / two CPUs without swap. The Python build scope
has the same memory/CPU bounds. No consumer download UI or physical PASS is
claimed yet. Measurements are pending in
`/tmp/sugarglider-pr42-idf-build-report.json`; generated files stay ignored.

Follow-up `7b230e6` passes `make check`: 1,036 tests / 16 existing integration
tests deselected, Ruff and strict mypy (240 source files). All five CI checks at `7b230e6` and measurement update `86cf7e0` pass.

Full Île-de-France totals 592,588,177 bytes. Map: 243,080,284 bytes / 1,252.505 s;
routing: 318,443,520 / 952.890 s; places: 366,485 / 1,603.828 s; nature: 30,694,816 /
502.714 s. The combined build was killed by its 3 GiB limit during final
verification after component completion. The same verifier in a fresh bounded
process passed in 24.94 s. Index builds now run in separate sequential processes
to release retained memory before the next stage; byte-equivalence and failure
cleanup tests pass. No inactive staging was presented as an installed region.

Full Île-de-France is unsuitable for the current reader: nature has 4,170,750
positions, beyond its unchanged 2,000,000 cap. The Yvelines/west-Paris partition
has a real PBF-built nature component of 10,634,994 bytes / 62,191 features /
1,450,033 positions. Its current shared-reader host check passes after the
measured topology-budget adjustment above. Its complete regional build and combined verifier now pass in the same
3 GiB/two-CPU bounds, reusing that exact checksummed nature component. Distribution:
188,368,868 bytes (map 81,571,296; routing 96,051,200; places 108,248; nature
10,634,994 plus manifests). Build ID:
`1bbf598d64f5d5cc987a60f9a4cb22318392d596ff88f3eb6b40cb70dceb4691`.
The observed run took 2,915.404 s with nature reused; its separately measured
nature build took 450.828 s. All phone installation/performance checks remain
pending. Report:
`/tmp/sugarglider-pr42-yvelines-build-report.json`.

GitHub release limits were audited, but its flat asset URLs need explicit catalog
mapping to PR39's logical paths or static storage preserving the directory layout.
No consumer catalog or public artifact has been published.

The first installer component now adds bounded incremental verification of OPFS
files, with a captured PR39 digest and size. The shared map store verifies that
identity before its completion marker; checksum failures never activate. It uses
pinned local noble-hashes modules, with no runtime dependency download. The real
81,571,296-byte Yvelines map verifies from Chrome OPFS after fixture-server shutdown
in 4,533 ms / 312 reads / maximum 256 KiB per read. This is host integrity evidence.
`make check` passes 1,033 tests / 16 existing integration deselections, 304 browser
scenarios pass, and Android checks retain 150 tests in each variant with no lint
errors. All 90 shared assets match APK/AAB bytes. That preparation's unsigned AAB was
47,368,403 bytes, SHA-256
`e355ff37522d5c73f818e21e787d76e08f629cc1ed978385008b914ab0a99ff9`.
[Integrity preparation](pr42-regional-integrity.md) records exact scope and tests.
Catalog/distribution, coordinated staging/activation/update/remove and actual
consumer-region phone acceptance remain open; PR42 is not complete.

The next [versioned-storage preparation](pr42-versioned-installation.md) adds
bounded regional activation records, concurrent request/writer ownership, scoped
reuse of the existing OPFS map/index formats, and a native immutable archive
store. Original component manifest bytes and full hashes survive restart checks;
failed updates preserve the active version. `make check` passes 1,033 tests,
334 browser scenarios pass, and Android passes 164 tests in each variant with
only the existing lint warnings. All 92 assets match the built artifacts. The
unsigned AAB from that preparation was 47,381,958 bytes, SHA-256
`1216c415cf7acc108b4ca0a9c1a63661e5636fa9cae3839830f6c4c766b87ec2`.
These stores are packaged but not wired into production planning or a download
screen. Native HTTP/storage adapters, routing-version transport, worker and
coordinator integration, catalog and Fairphone consumer-region acceptance remain
open. Browser native completion is synthetic and JVM archives are synthetic;
neither is physical regional-install evidence. The phone remains on `b8ebe3a`.

The [native transfer preparation](pr42-native-transfers.md) adds strict static
directory URLs, credential-free streamed downloads, timeout/cancellation checks,
and Android storage estimation/allocation before the archive download. It reuses
completed verified archives and leaves partial/corrupt versions explicit.
`make check` passes 1,033 tests; both Android variants pass 174 tests and retain
only existing lint warnings. All 92 shared assets and the native library are
unchanged. The current unsigned AAB is 47,389,057 bytes, SHA-256
`af7afb52bb5dd4bb8aa2abea98e60955d8ede914834b14a994b8fef1b4695fec`.
The adapter is not yet connected to the bridge or product screen. Runtime
version ownership, catalog, coordinator/worker/UI integration and physical
consumer-region acceptance remain open. No phone or public distribution claim
is made by these fake-connection tests.

## PR44 audit preparation

GitHub draft [PR #42](https://github.com/victorgabillon/sugarglider/pull/42),
implementation `b0d7761` in `/tmp/sugarglider-v1-pr44`, records current official
Google/Android requirements and release differences, external signing, privacy/
Data Safety drafts and the corrected bounded-replay disclosure. API 36 is already
configured. All nine documented Android storage domains are excluded from cloud
and device transfer. CI now validates the release variant and unsigned bundle.

- `make check`: 1,013 tests pass / 16 existing integration tests deselected;
  Ruff and strict mypy pass (240 source files).
- Debug: 136 JUnit tests and lint pass. Release: 133 JUnit tests, lint and
  `bundleRelease` pass. No test failure/error/skip was added. A low resource cap
  killed the first combined build; a separate release compile then exposed
  debug-only geometry helpers referenced by common tests. Those unchanged pure
  helpers now live in the common source set; all checks were rerun successfully.
- Five negative signing-configuration cases, a disposable-key signed bundle and
  signature verification pass. The unsigned artifact was restored and temporary
  key/password files removed. No permanent upload key was created.
- Renderer recovery (`acb66c4`) now discards the affected page and pending
  permission callback, invalidates page-owned work and offers explicit Reopen/Stop.
  It never automatically starts sharing. Automated lifecycle checks pass; physical
  crash/low-memory presentation remains pending.
- Archive-only configuration/timing follow-up `b5e9b1b` passes `make check`
  (1,013 tests), 138 debug and 134 release JUnit tests, both lint checks and AAB
  assembly. All 124 relevant browser scenarios pass. Lint has zero errors and
  visible dependency/update warnings. Native auxiliary/default paths are disabled,
  and debug timing labels describe wrapper setup/reuse accurately. Shell v24 on
  that branch must be reconciled with PR40's v25 on integration.
- Message-type follow-up `a10e835` rejects binary bridge payloads before WebKit's
  string accessor, preventing the pinned library's demonstrated exception. Exact
  origin/frame/page ownership checks remain intact. `make check` passes (1,013),
  as do 138 debug / 134 release JUnit tests, both lint checks and bundle assembly
  in a 3 GiB / two-CPU scope (3 min 19 s). No new device PASS is claimed. Evidence:
  `/tmp/sugarglider-pr44-message-type-{check,android}.log` and artifact report.
- PR44 merged main's PR40 through merge commit `2ab30b8`, preserving its native
  hardening and reconciling the shared shell at v27. Combined `make check` passes
  1,024 tests; 187 scenarios across ten browser harnesses pass. All five GitHub CI
  checks pass and the draft is mergeable. Native files are unchanged from
  `a10e835`, so its native test/bundle evidence still applies. This supersedes
  the earlier cache reconciliation note; full PR44 acceptance remains pending.
- Latest unsigned preparation AAB: 3,529,014 bytes, SHA-256
  `c6d2cf35d1f591560e7d36c8911bbdc0faacc92619dd8734690d87ff6d4c7804`, under the
  PR44 checkout's `android/app/build/outputs/bundle/release/app-release.aab`.
  It supersedes the 3,528,250-byte, 3,528,837-byte and 3,528,820-byte
  preparation artifacts.
  It contains no native routing library and is explicitly **not the V1 artifact**.
- Existing debug arm64 ELF alignment and APK `zipalign -c -P 16 4` pass. Final
  native release/delivered-APK/16 KiB runtime verification is still required.
- The wrapper embeds the expected Valhalla 3.6.3 commit and disables HTTP/services.
  Native 0.5.1 still creates an actor per call and prints exception text through
  JNI. Source/artifact inspection found generic route logs; physical failure-path
  logging and final native configuration validation remain required.

Production routing is still disabled. Final privacy identity/URL, public hosting,
real upload signing and all remaining final-release/device gates remain open.

## PR41 integration findings

The initial release started with server-origin setup and had no bundled normal
planner. Enabling its native factory alone cannot meet first-launch/offline
requirements. Integration needs bundled shell assets with a stable trusted
origin, normal Generate/candidate display, truthful unknown-detail coverage,
canonical signatures/traversal and local selected-candidate GPX export. The
existing canonical analysis has explicit availability/coverage fields; no
breaking result-schema change has been selected. Same-origin participant
authority must remain isolated. Normal Generate and physical acceptance remain
pending.

The first implementation part, `b6a097e` on `feat/pr41-local-canonical-export`,
is GitHub draft [PR #43](https://github.com/victorgabillon/sugarglider/pull/43).
All five CI checks pass at evidence head `b6c7d20`; the worker follow-up also passes all five checks at `6a0314c`; all five native-save checks also pass at `dad310c`. It connects
normal Download GPX to local serialization of the existing canonical candidate,
including a saved offline snapshot. It preserves exact track order/profile,
revalidates strict selected-stop arrivals, omits dropped stops and extensions,
and orders reached/approximated approaches together. Generated public profile
metadata comes from the sole Python registry. Shell v29 caches the serializer, metadata, client and worker modules.
See [PR41 local canonical export](pr41-local-canonical-export.md).

`make check`: 1,026 tests / 16 existing integration tests deselected, Ruff and
strict mypy pass (242 files). Relevant browser suites: 137 scenarios pass,
including 20 GPX cases. Validation/formatting now runs in a worker with a
16 MiB output bound, one pending export, cancellation and a 60-second limit. The actual shared-page host test saved a synthetic
snapshot through the UI, stopped its fixture server, reloaded offline and used
normal Download GPX successfully: zero export HTTP requests, unchanged snapshot,
and complete XML field equality with Python's canonical writer. Reports/logs:
`/tmp/sugarglider-pr41-export-worker-{check,browser,ui}.log` and
`/tmp/sugarglider-pr41-export-ui.json`.
The thin Android document-save adapter is implemented with bounded binary
transfer, the existing exact-origin/page gate, one picker/write slot, offloaded
output and truthful cancelled/failed/uncertain outcomes. Its validation passes
144 debug / 139 release unit tests, both lint checks, debug/release bundle assembly and 214
browser scenarios. Restart during saving retains only a boolean uncertainty
flag; file bytes and selected URIs are never restored. The actual shared-page offline Download test passes again.
Physical picker acceptance remains pending; the phone was in a call and was
left undisturbed. No new APK was installed during that call. The current unsigned
root preparation AAB has 3,531,390 bytes and SHA-256
`a0dc420df538974f3de50655de301e5b3e9c569878b35fb52a3d995fa1644574`; it has no native routing library and is not a V1 artifact.
The export document records both APK/AAB paths and hashes.

Physical Android saving, normal local candidate publication, bundled first launch,
release native routing and every required PR41 phone case remain outstanding.
This preparation does not establish a release-equivalent device PASS.

Normal-planner work continues on dependent branch
`feat/pr41-normal-local-planner`, based on `dad310c`. Both local searches now own
one shared request context with cached native calls and canonical budget/cache
diagnostics. Existing route/proposal behavior is retained; distinct concurrent
Auto Tour requests are rejected explicitly. `make check` and 223 browser
scenarios pass; 16 browser diagnostic snapshots validate through Python's
canonical model. [Normal integration evidence](pr41-normal-local-planner.md)
records this foundation. The next preparation now publishes canonical candidates
and full results through a worker and shared portfolio, including native nature,
validated reached POI approaches, explicit dropped outcomes and the mandatory
no-POI control. All 37 browser results pass the unchanged Python snapshot
validator; 264 browser scenarios and `make check` (1,028 passed / 16 deselected,
244 mypy files) pass. Shell v31 preserves normal offline GPX Download with zero
export fetches. Normal Generate and truthful unknown-detail UI integration remain
next; this is not a PR41 PASS or new physical evidence.

The subsequent normal-UI integration on draft GitHub
[PR #44](https://github.com/victorgabillon/sugarglider/pull/44) now selects the local
core when Android's bridge is present, publishes normal map/selection objects and
exports through the native document-save adapter. Shell v32 includes the existing
licensed required-label glyphs and restricts static cache access to its explicit
file list. `make check` remains green (1,028 / 16 deselected); 282 browser scenarios,
50 Python-validated canonical results and 59 matching candidate GPX exports pass.
Four actual-page tests with a disclosed synthetic native bridge pass after stopping
the static server: both modes with hiking/cycling, exact map lines/direction arrows,
normal GPX export, truthful unknown metrics and uncovered-region failure, with zero
generation/export API requests. These are host fixtures, not Fairphone or graph
evidence. Required/interior Auto Tour points, imported soft stops, native reversal,
map-wide local POI discovery, bundled first launch and release routing remain
explicit integration limitations; see the current PR41 document. All five CI
checks passed the earlier canonical-publication head `8fcd4a7`.

The next Fairphone preparation supersedes the earlier pending normal-UI/document
checks: the unchanged native APK was upgraded preserving data, and shell v34
passes normal Waypoint Route and Auto Tour with hiking and cycling. Exact map
geometry, direction arrows, visible local-map attribution, canonical validation,
local nature on tours, deterministic repeats, and outside-coverage failure pass.
There are zero planning API calls with the static setup server stopped. The
original cycling endpoint fails truthfully at 34.8 m against its 25 m limit; a
separate explicit graph-coordinate fixture succeeds. The error now exposes that
measured evidence without weakening the request. Android GPX Cancel and Save pass;
the 22,717-byte file matches Python exactly, retains 518 trackpoints in one track
and segment, and makes zero routing calls. `make check` and 283 browser scenarios
pass, and the final actual-page host check passes. All five CI checks passed
`fe80ea7`; the new follow-up needs its own checks. See the
[full physical evidence](pr41-normal-local-planner.md#fairphone-normal-planner-preparation--2026-09-12).
This remains a debug APK with a setup origin and development packs. Bundled first
launch, production routing, coordinated regional installation and the required
release-equivalent matrix remain outstanding; no PR41 or V1 PASS is claimed.

Bundled first launch is now implemented on dependent branch
`feat/pr41-bundled-android-shell`: normal launch opens the shared APK assets at a
fixed local HTTPS origin, with no server setup or service-worker dependency.
The local bridge accepts planning/GPX only, has a neutral handshake and rejects
tracking requests; optional sharing remains at its separate configured origin.
The Fairphone passes first launch, upgrade, cold process restart, the explicit
sharing/planner transition, both planning modes with hiking/cycling, outside
coverage and real GPX Save/Cancel. Its new origin correctly has no copied
map/POI/nature data; installed native routing archives remain independent.
`make check` passes 1,031 tests / 16 existing integration deselections, 286 browser
cases pass, and Android passes 149 debug / 144 release tests plus both lint checks
and APK/AAB assembly. The 84 packaged assets match source bytes in both artifacts.
[Bundled-shell evidence](pr41-bundled-android-shell.md) records exact boundaries,
commands, measurements and current artifact hashes. The unsigned AAB is 10,908,285
bytes, SHA-256 `1b1fc099a4c540d726040dc5611de51fd9035b42c1d66145bf9cc99886e8bd43`;
production routing remains disabled, so it is not the V1 artifact. All five CI
checks pass `af37a1f` and bundled-shell head `5f43bce` on draft
[PR #45](https://github.com/victorgabillon/sugarglider/pull/45).
Release routing, the coordinated consumer region installer/useful-region phone
acceptance and full release-equivalent PR41/44 gates remain open.

The next dependent preparation, `b8ebe3a` on
`feat/pr41-production-native-routing` / draft
[PR #46](https://github.com/victorgabillon/sugarglider/pull/46), passes all five CI
checks and now compiles
one shared production engine and profile policy in both variants. Configuration
uses only the selected archive, with auxiliary/default paths disabled; wire timing
fields are retained but described truthfully as wrapper/native-call measurements.
Both variants pass the same 150 unit tests, and their ARM64 native libraries are
byte-identical with 16 KiB ELF alignment. The normal app no longer binds the old
experiment panel at either origin. Common-engine Fairphone normal Generate,
repeats, exact canonical/map geometry, no planning API, explicit failures and
native GPX Save/Cancel pass. These are still debug-APK development-pack runs.
[Production native preparation](pr41-production-native-routing.md) records the
configuration/source audit, bounded log inspection, final checks/artifacts and
remaining release-equivalent/consumer-region gates. Earlier release-disabled
artifacts above are superseded; no PR41 or V1 PASS is claimed.

## External actions and blockers

| Gate | Status | Action / effect |
| --- | --- | --- |
| Fairphone USB authorization | RESOLVED | User reconnected the phone; ADB reports Fairphone 6 as authorized. |
| Fairphone PR40 acceptance | RESOLVED | User unlocked the visible app; required PR40 acceptance passed. Phone reconnected on 2026-09-12; display restoration, staging removal, retained backup and empty ADB forwarding are verified. Further physical gates remain open. |
| Static production hosting / domain | LIMITS AUDITED; TRANSPORT / PUBLICATION PENDING | GitHub Releases may fit measured large components, but directory mapping, redirects, full index size and real downloads still need validation. No artifact published or paid account created. |
| Social production hosting / domain / off-host backups | USER_ACTION_REQUIRED FOR LIVE ACCEPTANCE | Provider-neutral assets and HTTPS acceptance are prepared in PR43; user choice of an existing approved host/domain or later provisioning remains pending. |
| Upload signing key | USER_ACTION_REQUIRED BEFORE SIGNED UPLOAD | External configuration and disposable-key pipeline pass. Publisher must supply an existing key or explicitly create/safeguard one; no permanent key created. |
| Public privacy-policy identity/URL and Play declarations | USER_ACTION_REQUIRED BEFORE SUBMISSION | Prepare truthful drafts in PR44; publication/legal declarations remain human gates. |

## Temporary evidence availability

The host restarted on 2026-09-12 and cleared `/tmp`, including the PR43/PR44
preparation worktrees and their temporary AAB/reports. Their committed sources
remain on Git branches and GitHub; historical measured evidence above remains
recorded, but those temporary artifact paths are no longer available. PR44's clean checkout has now been restored at
`/home/pompote/oldata/victor/sugarglider-v1-pr44` from `2ab30b8`; the completed PR43
checkout was not needed. Rebuild PR44 artifacts before further current-artifact
claims. Root and PR42 checkouts, the protected entries/stash,
and uncommitted PR41 source changes survived. PR41 native-save checks were
rerun after restart; its current artifacts are under root `android/app/build`.

## Current V1 status

IN PROGRESS. PR40 and PR43's code-side milestones are merged; public hosting
remains pending. PR40 required physical acceptance passes; PR41/42/44 completion is outstanding. No V1 readiness
or signed release artifact is claimed.

Temporary static servers and owned USB reverse mappings were removed before
accepted PR40/PR41 testing. After the PR41 preparation on 2026-09-12, the phone
remains authorized, both ADB forwarding lists are empty, and the original
stay-awake setting is confirmed as `0`. The private previous Marly routing archive
remains backed up. No radio/hotspot state was changed, no location sharing was
started, and no app data was cleared.

## PR42 explicit regional runtime bridge

The next dependent foundation follows `e7dc680` / draft PR #49. It replaces
development-directory routing discovery with an explicit immutable region/build/pack
reference on protocol-v3 route calls. Native read leases protect complete JNI
operations from removal. One application-owned regional worker exposes bounded
inspect/install/remove status and cancellation; only the bundled main-frame origin
may invoke regional or local-routing operations.

The shared planning context holds a committed version through search, native drain
and canonical publication. Index workers open its owned OPFS directory and recheck
compressed hashes even when parsed data is cached. Candidate/search diagnostics
retain the exact regional version; GPX remains unchanged.

Validation: `make check` passes 1,033 tests (16 existing integration tests deselected),
Ruff and strict mypy. The host browser suite passes 348 cases in 19 harnesses,
including real OPFS/worker corruption checks; 51 full canonical results and 60 GPX
documents pass Python validation/serializer comparison. Native tests/lint and final
artifact details are recorded in [runtime bridge evidence](pr42-regional-runtime.md).
These are component and synthetic native-fixture tests, not physical PASS.

The application coordinator, selected-region map display, catalog and install UI
remain the next dependent slice. The phone remains on `b8ebe3a`; its real development
packs are preserved and are not silently migrated. This draft is not merge-ready
until the region product and physical acceptance gates pass.

The regional runtime artifact build passes in 4 min 7 s: 187 native tests per
variant, lint with only the existing two debug / one release warnings, debug APK
and unsigned release AAB, and all 95 packaged shared assets byte-identical to
source. Artifact paths/hashes/sizes are in the linked runtime evidence.


## PR42 region download product

Dependent branch `feat/pr42-region-product-ui` follows `1ac0a3c` / draft
[PR #50](https://github.com/victorgabillon/sugarglider/pull/50), which passed all
five CI jobs. The bundled app now selects its committed regional context for
normal planning and maps. One UI action coordinates verified map, native routing,
places and nature downloads. Update, cancellation drain, partial-data recovery,
scoped removal (including damaged metadata/orphaned native files), and map-view
controls are implemented. Catalog download URLs remain visibly unavailable
until static distribution is configured; this is not a consumer-region PASS.

`make check` passes 1,033 tests / 16 existing integration tests deselected. Twenty
browser harnesses pass 361 scenarios, including thirteen focused product cases;
51 full canonical results, 30 submitted fixtures, 16 diagnostics and 60 GPX
comparisons pass Python validation. An additional actual-page browser check
passes Download, activation, distribution-unavailable reload, shared PMTiles map
view, normal Waypoint Route and Auto Tour for hiking/cycling, exact canonical
map/traversal display and export without rerouting. It uses a disclosed synthetic
native adapter: no native/physical PASS is inferred. See
[product behavior and evidence](pr42-region-product.md).

Both native variants pass 195 unit tests and lint with zero errors/failures/skips.
The final APK/AAB must include all 101 shared shell assets byte-identically.
Consumer-region physical installation, restart, map, native planning latency,
interruption/cancellation and removal/reinstall remain required. The phone is
still authorized; no hotspot/radio or existing user-data reset was used.

The product APK and unsigned AAB now pass exact source comparisons for all 101
assets. APK: 151,696,861 bytes, SHA-256
`7c634034b20825a835d361cf8fb3a5be4fc0bfe11755b3866e9d4765c0e0fff2`;
AAB: 47,419,436 bytes, SHA-256
`4ab95d6456d20c937228b787d1d4a12e1183ef8aeb35bce52e4e753415c608b5`.
`adb install -r` upgraded the Fairphone successfully. While the phone was locked,
WebView inspection confirmed bundled startup, the honest unavailable 188.4 MB
catalog entry, no committed region, and Generate disabled with the download
explanation. This limited startup result does not replace visible physical
acceptance. No owned USB forward/reverse remains.

## PR42 static publication preparation

Product draft [PR #51](https://github.com/victorgabillon/sugarglider/pull/51) at
`b568418` passes all five CI checks. Dependent static distribution work prepares
and revalidates the exact regional files, attributed landing page/README, public
catalog and deterministic ZIP. A standalone confined extractor and inactive,
manually triggered GitHub Pages workflow are prepared for a separate public data
repository; generated data never enters either repository's Git history.

`make check`: 1,049 passed / 16 existing integration tests deselected; Ruff and
strict mypy pass. Real Yvelines publication ZIP: 188,374,659 bytes, SHA-256
`40990c600c0b7bf934522daef1c92d7db44d0ab890077e1224084a6244476a9f`,
at `/tmp/sugarglider-pr42-static-publication/sugarglider-regions-static.zip`.
Standalone extraction preserves all eleven site files exactly. The app catalog
remains unavailable and no data has been published.

USER_ACTION_REQUIRED: approve the proposed separate public
`victorgabillon/sugarglider-regions` repository, data release and free GitHub Pages
host, or supply an existing approved HTTPS static host. Current documented Pages
limits/terms, byte/CORS contract, retained-version publishing and physical gates
are recorded in [static distribution preparation](pr42-static-distribution.md).
No paid resource, account or domain is provisioned by this proposal.
