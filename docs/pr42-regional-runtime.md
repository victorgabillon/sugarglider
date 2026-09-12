# PR42 — explicit regional runtime bridge

This foundation follows native-transfer preparation `e7dc680` / draft
[PR #49](https://github.com/victorgabillon/sugarglider/pull/49). The complete
installer, application wiring and phone acceptance are still pending. This is
not a consumer release. The accepted phone build remains `b8ebe3a`; its legacy
development archives are not implicitly migrated or used by this new engine.

## One region per request

`createRegionalPlanningContext` captures one selected, committed PR39 manifest
under `withCommittedRegions`. It checks native routing, map integrity and the
exact index-worker identity before invoking the whole planning callback. The
callback includes search, native drain and canonical publication. A sole
committed region can be selected automatically; multiple regions require an
explicit selection. An unavailable selected region never chooses another one.
The application region screen will supply that selection in the next slice.

Every internal native capability/route request carries the immutable routing
reference. Route protocol version 3 requires region/build/pack IDs, bounds and
manifest/archive size and SHA-256. Version 2, missing references and extra fields
are rejected. An unbound shared bridge cannot route. The engine opens only the
referenced private version and validates all ordered points and profile access;
it no longer discovers the old `routing-packs` directory. Returned native
geometry, six public profile identities and canonical public schemas are unchanged.

The canonical publication worker records `regional_version` in candidate
`diagnostics.details.local_routing` and search `details.local_planning`.
Publication rejects a native pack identity different from the committed reference.
GPX still serializes the stored canonical candidate without rerouting or adding
regional extensions.

## Native ownership and operations

`RegionalRoutingRepository` holds a native read lease through the complete JNI
callback. Removal checks the same region/build/pack path under the lease gate,
including stale references with different hashes. At most 16 leases are admitted.
A page disappearing cannot authorize deletion beneath its still-running JNI call.
Capabilities perform archive validation on the route worker, with page-owned
reply delivery. Every native open currently rehashes the archive; no validation
cache or unmeasured phone latency improvement is claimed.

`RegionalRoutingOperations` owns one application worker and one latest operation.
Inspect, install and remove return bounded status; polling/cancellation performs
no file I/O on the Activity thread. Installation uses the existing bounded native
downloader; removal uses the read-lease repository. Another operation is rejected
while work is running, and duplicate commands reuse the same operation. Progress
is archive bytes only. The manager retains no durable queue or operation history.

The bundled main-frame origin alone may invoke native regional operations and
local routing. Existing nonce/channel/navigation/ledger checks remain in force.
The configured sharing origin cannot obtain this capability. Page invalidation
cancels its own regional work. Cancellation stays running until the worker has
finished file cleanup; a definite completed removal remains acknowledged. No
service, job, reboot restoration, participant authority, coordinate or native
path is added to this protocol.

The shared adapter polls every 500 ms, bounds each bridge exchange to five
seconds, and requests cancellation after an uncertain transport outcome. Its
31-minute ownership bound does not assert that every native DNS/socket operation
can be interrupted. An unconfirmed outcome is explicit and must retain staged
files. Presentation callback failure cannot release running file work.

## Shared component workers

The index worker accepts an owned OPFS version directory through structured
clone. It never reacquires the coordinator's region lock. A staged installation
preserves any already-loaded committed analysis session. A cached parsed session
still revalidates compressed file hashes on its next version load, so missing or
corrupt disk data cannot be concealed by a matching in-memory build ID.

Maps retain the existing shared `MapPackStore`, PMTiles reader and bounded OPFS
random reads. Map methods use the packaged classic PMTiles runtime on the page;
index methods can run in the module worker. No second component representation,
native map copy, network routing fallback or cross-region stitching is introduced.

## Validation and remaining gates

- `make check`: 1,033 Python tests pass, 16 existing integration tests deselected;
  Ruff and strict mypy pass (247 typed source files).
- `uv run python /tmp/sugarglider-pr42-runtime-browser.py`: 348 cases in 19
  browser harnesses pass. This includes 13 new runtime cases and a real OPFS /
  module-worker case that detects corrupt compressed data despite a parsed cache.
  Synthetic native replies are explicitly fixtures, not physical routing evidence.
- The browser outputs pass Python validation for 51 complete canonical results,
  30 individually submitted native-fixture candidates and 16 diagnostic snapshots.
  All 60 candidate GPX documents match Python's serializer structurally.
- Both native variants pass 187 JUnit tests with zero failures/errors/skips.
  `lintDebug` and `lintRelease` pass with the same two debug / one release
  existing warnings; no new warning or suppression was introduced.
- Bounded offline Gradle `testDebugUnitTest lintDebug testReleaseUnitTest
  lintRelease assembleDebug bundleRelease` passes in 4 min 7 s. All 95 packaged
  shared assets match their current source bytes in both APK and AAB.
- Shell v39 packages all new shared modules. Cache-generation assertions were
  refreshed; old architecture assertions now require explicit references instead
  of development-directory discovery. No test gate was relaxed or skipped.

The normal `app.js` region coordinator and product UI are the next dependent
slice. Static catalog/distribution, backup-rule integration, real Fairphone region
installation, planning, restart, cancellation, update and removal remain open.
Do not merge this foundation until its dependent product and physical gates pass.

## Build artifacts (not installed on the phone)

- Debug APK: `/home/pompote/oldata/victor/sugarglider/android/app/build/outputs/apk/debug/app-debug.apk`; 151,648,780 bytes; SHA-256
  `4e6509f21938259eb8588ae7f91ccfee20ed3cbd6f5464d7a47fd980d9af9363`.
- Unsigned release AAB: `/home/pompote/oldata/victor/sugarglider/android/app/build/outputs/bundle/release/app-release.aab`; 47,405,170 bytes; SHA-256
  `77e44fa7b5acf035b6d304523f72d78604ea1f1073e167892ea716039f4b61df`.

Both contain the unchanged pinned ARM64 native library, SHA-256
`e60d66dba922a17c53397e4a00ba4380a9ec87f8f203d3761fefe86bef9b2bbb`.
The release build uses the unsigned pipeline; no signing key was created. The
standard build paths are overwritten by later builds, so these hashes identify
this preparation result rather than a permanently retained release artifact.
