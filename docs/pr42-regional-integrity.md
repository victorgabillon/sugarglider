# PR42 preparation — bounded regional map integrity

This dependent preparation follows production-router commit `b8ebe3a` / draft
[PR #46](https://github.com/victorgabillon/sugarglider/pull/46), whose five CI checks
pass. It adds the shared checksum primitive needed before coordinated region
activation. It does not yet provide the catalog, four-component staging/commit
protocol, native archive downloader or consumer installation UI.

`verifyRegionalFile` reads an inactive OPFS file snapshot in sequential **256 KiB**
slices and computes incremental SHA-256. It rejects invalid descriptors, different
sizes, short reads and digest mismatches. Expected identity is captured before the
first asynchronous read. Cancellation is checked around reads and before success;
periodic event-loop yields let worker cancellation messages run. Verification
writes nothing and retains no complete file buffer or coordinate data. Read errors
use bounded generic codes.

The existing shared `MapPackStore.installPack` accepts an optional `expectedArchive`
from the verified top-level PR39 manifest. When supplied, size agreement is checked
before archive download, and the file digest is checked before the map completion
marker is written. Failure removes only the owned incomplete install; it cannot
make mismatching bytes active. The standalone PR36 map manifest has no SHA-256
field; its existing flow retains that limitation. The future regional coordinator
must always supply the PR39 descriptor. This addition does not claim atomic
multi-component activation or update support.

Incremental SHA-256 uses locally vendored modules from
[noble-hashes 2.4.0](https://github.com/paulmillr/noble-hashes/releases/tag/2.4.0),
released 2026-08-27, pinned locally with its MIT license. The official npm tarball
was checked against its published SHA-512 integrity value; module hashes and
provenance are in `static/vendor/noble-hashes-2.4.0/README.md`. Only SHA-2 and its
three local dependencies are copied; trailing spaces are normalized for the
repository whitespace check, with upstream and normalized hashes recorded. There is no runtime CDN/npm request and no
change to signing or token storage. Shared shell v37 and Android's generated
allowlist include the complete import closure and license.

The browser harness covers known vectors, WebCrypto cross-checks around SHA-256
padding and file-read boundaries, single-flight bounded reads, progress,
corruption, metadata/descriptor failures, cancellation before/during/after reads,
timer fairness, descriptor mutation, generic read failures, and actual OPFS.
Three map-store cases cover correct activation, checksum rejection/cleanup without
retry, and descriptor/size rejection before archive download. Existing map and
normal-planning cases remain included. The shell import-graph test now resolves
relative imports against each module's own directory, covering nested vendor
modules instead of assuming every import lives at the static root.

A separate host measurement uses the real Yvelines PR39 map archive:

- Regional build: `1bbf598d64f5d5cc987a60f9a4cb22318392d596ff88f3eb6b40cb70dceb4691`.
- **81,571,296 bytes**, SHA-256
  `620dddfcb7e9c77995d91987299a5651ad1be4ef957154ab5c81ff414b60ff94`.
- Streamed to actual Chrome OPFS, then the temporary fixture server was stopped.
  Incremental verification passes in **4,533 ms**, with **312 reads**, each at most
  **262,144 bytes**; total bytes read exactly equal file size.
- The owned OPFS fixture and temporary browser profile are removed afterward.
  Report: `/tmp/sugarglider-pr42-integrity-large-map.json`.

Final validation on 2026-09-12:

- `make check`: **1,033 passed / 16 existing integration deselections**; Ruff and
  strict mypy pass (247 files).
- `uv run python /tmp/sugarglider-pr41-document-browser.py`: **304 scenarios in
  sixteen browser harnesses pass**, including 15 new integrity and three map-store
  scenarios. The existing canonical/GPX comparisons remain green.
- The actual shared-page synthetic-native test passes both planning modes with
  hiking/cycling and local export after server shutdown. No planning API call or
  route-generation behavior changes.
- Android `testDebugUnitTest lintDebug testReleaseUnitTest lintRelease assembleDebug
  bundleRelease` passes in 2 min 25 s. Both variants retain **150 tests** with no
  failures/errors/skips. Lint retains two debug / one release existing warnings,
  with no errors/fatal findings. The unchanged native library remains identical
  in APK/AAB. After whitespace-only normalization of the two vendor files,
  APK/AAB assembly passes again in 1 min 23 s and `make check` passes again.
- All **90 packaged shared assets**, including the incremental-hash module closure
  and license, match their source bytes. `git diff --check` passes.

Historical generated artifacts from this preparation (the build-output paths
are now superseded by [versioned-storage preparation](pr42-versioned-installation.md)):

| Artifact | Path | Bytes | SHA-256 |
| --- | --- | ---: | --- |
| Debug APK | `android/app/build/outputs/apk/debug/app-debug.apk` | 151,613,326 | `d9991d89bcadf6cd176244f1652574dfe7e5bb90f039ee514e16309b4df1c251` |
| Unsigned release AAB | `android/app/build/outputs/bundle/release/app-release.aab` | 47,368,403 | `e355ff37522d5c73f818e21e787d76e08f629cc1ed978385008b914ab0a99ff9` |

Logs and reports: `/tmp/sugarglider-pr42-integrity-*`. Initial checks exposed a
DOMException assertion treating its numeric legacy code as the cancellation name,
the old harness count, and the root-relative import-graph assumption. The upstream modules also contained trailing spaces, normalized as recorded
above. Those tests
were corrected and the affected complete suites passed afterward.

This is host integrity evidence, not phone installation time, whole-application
memory usage, fresh consumer-region acceptance or final V1 readiness. The phone
remains on the previously validated `b8ebe3a` production-engine preparation APK.
No radio, hotspot, user data, region archive or protected worktree entry changed.
