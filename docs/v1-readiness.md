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
| PR41 production Android local planner | NOT STARTED | Normal release-equivalent Generate for Waypoint Route and Auto Tour; canonical display/export objects; pedestrian/bicycle device runs; no backend call; uncovered-region failure |
| PR42 region product | NOT STARTED | Static catalog; verified failure-safe install/update/remove UI; useful measured region; fresh Fairphone install, restart, map, planning, cancellation and removal |
| PR43 tiny production service | NOT STARTED | Reproducible HTTPS/SQLite social-only deployment, limits, backups/recovery, graceful offline behavior; no routing dependency |
| PR44 Play release candidate | NOT STARTED | Current official policy audit; release tests/lint/AAB; secret-safe external signing; permission/privacy/store documents; physical lifecycle/permissions/export matrix |

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

## External actions and blockers

| Gate | Status | Action / effect |
| --- | --- | --- |
| Fairphone USB authorization | RESOLVED | User reconnected the phone; ADB reports Fairphone 6 as authorized. |
| Fairphone visible/unlocked app | USER_ACTION_REQUIRED | Android reports keyguard showing and NotificationShade focused. Unlock and foreground Sugarglider Debug; request pending. No physical PASS or merge is allowed yet. |
| Static production hosting / domain | NOT YET AUDITED | Prepare static assets first; no paid account or credentials invented. |
| Upload signing key | NOT YET AUDITED | External configuration only; no permanent key creation without user action. |
| Public privacy-policy identity/URL and Play declarations | USER_ACTION_REQUIRED BEFORE SUBMISSION | Prepare truthful drafts in PR44; publication/legal declarations remain human gates. |

## Current V1 status

IN PROGRESS. No new milestone has passed or merged. No V1 readiness or signed
release artifact is claimed.

Physical-test setup pending the unlock: a temporary static-only server is running
on host loopback port 8000, with an owned `adb reverse tcp:8000 tcp:8000` mapping.
It serves only application assets and the three PR40 Marly data files, no planning
API. Remove it before backend-isolated acceptance. To keep the device awake on
USB, `stay_on_while_plugged_in` was temporarily set to 2; its original value 0 is
recorded in `/tmp/sugarglider-pr40-phone-display.json` and must be restored after
testing. Hotspot, cellular, Wi-Fi and airplane-mode settings remain untouched.
