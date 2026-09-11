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
| PR40 local Auto Tour v2 / POI / nature | CODE/AUTOMATED CHECKS PASS; DEVICE GATE PENDING | Validated local PR39 readers/storage; bounded deterministic search; truthful preference/arrival evidence; unchanged hard gates; real Fairphone data, repeat and backend-isolated acceptance still required |
| PR41 production Android local planner | INTEGRATION AUDIT STARTED | Normal release-equivalent Generate for Waypoint Route and Auto Tour; canonical display/export objects; pedestrian/bicycle device runs; no backend call; uncovered-region failure |
| PR42 region product | FULL REGION MEASURED; WESTERN PARTITION BUILDING | Static catalog; verified failure-safe install/update/remove UI; useful measured region; fresh Fairphone install, restart, map, planning, cancellation and removal |
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

GitHub [PR #39](https://github.com/victorgabillon/sugarglider/pull/39) is a draft
at implementation `ca2fb51`; all four Python/Android checks passed. It is
mergeable but remains unmerged because physical acceptance is still pending.

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
updated reader. These are component-only host measurements; physical acceptance
and a complete installed region remain pending.

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
tests deselected, Ruff and strict mypy (240 source files). The four CI checks on
its preceding head passed; the follow-up CI is being checked.

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
measured topology-budget adjustment above. Its complete map/routing/places build
is running in the same 3 GiB/two-CPU bounds, reusing that exact checksummed nature
component; full verification and all phone checks remain pending. Report:
`/tmp/sugarglider-pr42-yvelines-build-report.json`.

GitHub release limits were audited, but its flat asset URLs need explicit catalog
mapping to PR39's logical paths or static storage preserving the directory layout.
No consumer catalog or public artifact has been published.

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
- Latest unsigned preparation AAB: 3,528,820 bytes, SHA-256
  `5a1a8ff7b7e8054a72fc5d9aa0717505c6893bf26b1107df647208656e75c64f`, under the
  PR44 checkout's `android/app/build/outputs/bundle/release/app-release.aab`.
  It supersedes the 3,528,250-byte and 3,528,837-byte preparation artifacts.
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

The current release starts with server-origin setup and has no bundled normal
planner. Enabling its native factory alone cannot meet first-launch/offline
requirements. Integration needs bundled shell assets with a stable trusted
origin, normal Generate/candidate display, truthful unknown-detail coverage,
canonical signatures/traversal and local selected-candidate GPX export. The
existing canonical analysis has explicit availability/coverage fields; no
breaking result-schema change has been selected. Same-origin participant
authority must remain isolated. Implementation and physical acceptance are pending.

## External actions and blockers

| Gate | Status | Action / effect |
| --- | --- | --- |
| Fairphone USB authorization | RESOLVED | User reconnected the phone; ADB reports Fairphone 6 as authorized. |
| Fairphone visible/unlocked app | USER_ACTION_REQUIRED | Android reports keyguard showing and NotificationShade focused. Unlock and foreground Sugarglider Debug; request pending. No physical PASS or merge is allowed yet. |
| Static production hosting / domain | LIMITS AUDITED; TRANSPORT / PUBLICATION PENDING | GitHub Releases may fit measured large components, but directory mapping, redirects, full index size and real downloads still need validation. No artifact published or paid account created. |
| Social production hosting / domain / off-host backups | USER_ACTION_REQUIRED FOR LIVE ACCEPTANCE | Provider-neutral assets and HTTPS acceptance are prepared in PR43; user choice of an existing approved host/domain or later provisioning remains pending. |
| Upload signing key | USER_ACTION_REQUIRED BEFORE SIGNED UPLOAD | External configuration and disposable-key pipeline pass. Publisher must supply an existing key or explicitly create/safeguard one; no permanent key created. |
| Public privacy-policy identity/URL and Play declarations | USER_ACTION_REQUIRED BEFORE SUBMISSION | Prepare truthful drafts in PR44; publication/legal declarations remain human gates. |

## Current V1 status

IN PROGRESS. PR43's code-side milestone is merged; public hosting remains pending.
PR40 physical acceptance and PR41/42/44 completion are outstanding. No V1 readiness
or signed release artifact is claimed.

Physical-test setup pending the unlock: a temporary static-only server is running
on host loopback port 8000, with an owned `adb reverse tcp:8000 tcp:8000` mapping.
It serves only application assets and the three PR40 Marly data files, no planning
API. Remove it before backend-isolated acceptance. The temporary USB stay-awake
setting has been restored to its original value 0 while the phone remains locked;
the original is recorded in `/tmp/sugarglider-pr40-phone-display.json`. The static
server script now has the missing root shell mappings, but must be restarted
before refreshing the phone. Hotspot, cellular, Wi-Fi and airplane-mode settings
remain untouched.
