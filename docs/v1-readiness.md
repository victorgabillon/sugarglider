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
| PR41 production Android local planner | LOCAL CANONICAL GPX IMPLEMENTED; NORMAL PLANNING / NATIVE EXPORT PENDING | Normal release-equivalent Generate for Waypoint Route and Auto Tour; canonical display/export objects; pedestrian/bicycle device runs; no backend call; uncovered-region failure |
| PR42 region product | WESTERN PARTITION BUILT / VERIFIED; PRODUCT UI PENDING | Static catalog; verified failure-safe install/update/remove UI; useful measured region; fresh Fairphone install, restart, map, planning, cancellation and removal |
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

The current release starts with server-origin setup and has no bundled normal
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
All five CI checks pass at evidence head `b6c7d20`; subsequent worker changes require their own CI. It connects
normal Download GPX to local serialization of the existing canonical candidate,
including a saved offline snapshot. It preserves exact track order/profile,
revalidates strict selected-stop arrivals, omits dropped stops and extensions,
and orders reached/approximated approaches together. Generated public profile
metadata comes from the sole Python registry. Shell v28 caches the serializer, metadata, client and worker modules.
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
Android file saving, normal local candidate publication, bundled first launch,
release native routing and every required PR41 phone case remain outstanding.
This preparation does not establish a release-equivalent device PASS.

## External actions and blockers

| Gate | Status | Action / effect |
| --- | --- | --- |
| Fairphone USB authorization | RESOLVED | User reconnected the phone; ADB reports Fairphone 6 as authorized. |
| Fairphone PR40 acceptance | RESOLVED | User unlocked the visible app; required PR40 acceptance passed. Phone reconnected on 2026-09-12; display restoration, staging removal, retained backup and empty ADB forwarding are verified. Further physical gates remain open. |
| Static production hosting / domain | LIMITS AUDITED; TRANSPORT / PUBLICATION PENDING | GitHub Releases may fit measured large components, but directory mapping, redirects, full index size and real downloads still need validation. No artifact published or paid account created. |
| Social production hosting / domain / off-host backups | USER_ACTION_REQUIRED FOR LIVE ACCEPTANCE | Provider-neutral assets and HTTPS acceptance are prepared in PR43; user choice of an existing approved host/domain or later provisioning remains pending. |
| Upload signing key | USER_ACTION_REQUIRED BEFORE SIGNED UPLOAD | External configuration and disposable-key pipeline pass. Publisher must supply an existing key or explicitly create/safeguard one; no permanent key created. |
| Public privacy-policy identity/URL and Play declarations | USER_ACTION_REQUIRED BEFORE SUBMISSION | Prepare truthful drafts in PR44; publication/legal declarations remain human gates. |

## Current V1 status

IN PROGRESS. PR40 and PR43's code-side milestones are merged; public hosting
remains pending. PR40 required physical acceptance passes; PR41/42/44 completion is outstanding. No V1 readiness
or signed release artifact is claimed.

PR40 setup's temporary static server and owned USB reverse mapping were removed
before accepted testing. On 2026-09-12 ports 8000/8989 have no listener and ADB
has no device/forward. The original stay-awake value `0` was recorded and a
restore command issued after testing; a retained readback is unavailable. Recheck
that setting and removal of the public temporary routing files on reconnection.
The private previous Marly routing archive remains backed up. No radio/hotspot
state was changed and no app data was cleared.
