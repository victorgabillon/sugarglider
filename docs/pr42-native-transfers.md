# PR42 preparation — native regional transfer adapter

This work follows `0f79845` / draft [PR #48](https://github.com/victorgabillon/sugarglider/pull/48),
whose five CI checks pass. It is not yet connected to the native bridge or the
normal region screen. The phone still uses the previously accepted `b8ebe3a` APK.

`RegionalRoutingDownloader` accepts the captured native reference and the static
PR39 regional manifest URL. It derives only the two routing component URLs under
that directory. URLs cannot carry user information, query parameters, fragments,
encoded path separators or dot traversal. HTTPS is the default; private HTTP
requires the explicit development setting. Redirects and partial responses fail
explicitly. The client uses platform TLS, no social authority, no HTTP cache, and
identity encoding. Streamed bodies must match their declared reference sizes and
SHA-256 digests before native completion.

Connect/read operations use 15-second socket timeouts. A 30-minute elapsed
deadline and caller-owned cancellation flag are checked between operations and
around reads. Cancellation does not block the UI on `disconnect`; a stalled
operation must reach its timeout/checkpoint before reporting final cleanup.
These checkpoints do not establish hard wall-clock interruption of every platform
DNS/socket operation. Completion is never reported while a worker is still
cleaning up. Completed valid archives can be reopened without another download;
corrupt or partial versions remain explicit and require cleanup.

`createRegionalRoutingPackStore` places native files in the application's private
`regional-routing-packs` directory. The Android adapter uses `getAllocatableBytes`
for its preflight estimate and `allocateBytes` on the newly created archive file
descriptor before opening the archive download. These are worker-thread operations
and can reclaim system-managed cache, as documented by the
[Android storage API](https://developer.android.com/reference/android/os/storage/StorageManager).
No external-storage permission or directory fallback is added. Transfer byte
counts remain authoritative even when allocation has extended the file with
zeros; allocation or download failure removes only the new incomplete version.

Current tests use fake HTTP connections, synthetic archive headers and temporary
directories. They exercise URL boundaries, transport settings, response and size
failures, cancellation, timeout checkpoints, digest failures, completed reuse,
previous-version preservation, and allocation ordering. They do not establish a
real HTTPS download, phone installation time or physical consumer-region acceptance.

Required next steps are bridge/lifecycle integration, explicit version references
in production routing, worker/coordinator integration, catalog and product UI,
then real Fairphone installation/update/restart/removal/cancellation acceptance.

Validation completed on 2026-09-12:

- `make check`: **1,033 tests pass / 16 existing integration deselections**;
  Ruff and strict mypy pass. Log: `/tmp/sugarglider-pr42-transfers-check.log`.
- The constrained Java 17 / SDK 36 Gradle command recorded in
  [versioned storage](pr42-versioned-installation.md) passes
  `testDebugUnitTest lintDebug testReleaseUnitTest lintRelease assembleDebug
  bundleRelease` in **3 min 48 s**. Each variant passes **174 tests** with no
  failures/errors/skips, including nine downloader cases and the additional
  preallocation/short-response case. Lint retains only the existing two debug /
  one release warnings, with no errors or fatal findings. The final run uses one
  fixed source snapshot after an earlier run overlapped edits.
- `uv run python /tmp/sugarglider-pr42-transfers-artifacts.py` checks all **92
  packaged shared assets** against their exact source bytes. Shared web code is
  unchanged from `0f79845`, where 334 browser scenarios and the normal shared UI
  checks passed. This native-only preparation does not claim new physical evidence.
- The ARM64 native library remains identical in APK/AAB, SHA-256
  `e60d66dba922a17c53397e4a00ba4380a9ec87f8f203d3761fefe86bef9b2bbb`.
- Whitespace checks pass; no new skipped/expected-failure test or lint suppression
  was introduced. Logs/reports use `/tmp/sugarglider-pr42-transfers-*`.

Ignored artifacts superseding the previous files at these paths:

| Artifact | Path | Bytes | SHA-256 |
| --- | --- | ---: | --- |
| Debug APK | `android/app/build/outputs/apk/debug/app-debug.apk` | 151,634,516 | `07e41206f779add2c8ffb91224d2c41ff6ffbfef82a2fef90666e4b184f22e9c` |
| Unsigned AAB | `android/app/build/outputs/bundle/release/app-release.aab` | 47,389,057 | `af7afb52bb5dd4bb8aa2abea98e60955d8ede914834b14a994b8fef1b4695fec` |

These are preparation artifacts, not the final V1 release candidate. The phone
was not upgraded and no region was downloaded onto it by this change.
