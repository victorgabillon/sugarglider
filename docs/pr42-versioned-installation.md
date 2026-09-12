# PR42 preparation — versioned regional storage

This work follows the bounded integrity preparation `4ac910c` / draft
[PR #47](https://github.com/victorgabillon/sugarglider/pull/47). The full installer
is not implemented or physically accepted yet.

The installation contract uses one committed regional manifest as the logical
activation point. Maps stay in OPFS behind the existing shared map implementation;
places/nature reuse the existing shared index reader and worker; routing archives
stay solely in native application files. No archive is copied into both OPFS and
native storage for a uniform layout.

A new regional version is staged separately from the current committed version.
All PR39 identities, file sizes, hashes, component formats and matching coverage
must validate before a single active-record replacement. Cancellation/failure
before that replacement leaves the current version available. A crash before
commit leaves explicit incomplete data for recovery or cleanup. Corrupt active
metadata never authorizes a guessed version or a fallback to staging.
The active record uses `FileSystemWritableFileStream.close`, whose file update
is expected to be atomic by the [File System Standard](https://fs.spec.whatwg.org/#api-filesystemwritablefilestream).
Uncertain close outcomes are still re-read and reported explicitly; host tests
do not establish phone power-loss durability.

Every planning request captures the committed region references once. Native
routing must receive explicit version references and may resolve only those
completed archives; neither file discovery nor a newly staged archive may change
an in-flight request's graph. Public profile identity, one-region selection,
strict route budgets and canonical candidate behavior remain unchanged. Native
transport changes are internal to the packaged application; canonical planning
request/result schemas are not changed.

The coordinator owns serialized install/update/remove operations and preserves
operation ownership through cancellation, native replies, worker messages and
page lifecycle changes. It checks browser and native storage independently and
reports failures explicitly. Removal first makes the region unavailable through
the same committed record, then cleans only files owned by that region. Optional
cleanup failures must be reported without inventing active data.

Distribution remains static, with PR39 manifests and original component bytes.
Catalog entries must carry actual region identity, coverage, version, size and
verified manifest location; an unhosted offering must not appear downloadable.
A public hosting choice remains an external gate. Implementation and local/host
validation continue independently; final acceptance still requires a real fresh
consumer-region install through the normal Fairphone UI, restart, map, both
planning modes, export, cancellation, removal and update/reinstallation.

The shared activation component is `region_versions.js`: bounded OPFS metadata storage,
immutable staging tickets, explicit four-component verification before activation,
a compare-and-swap check against the prior commit, outcome recovery when a close
response is lost, inactive-only cleanup and explicit corrupt-pointer recovery.
Its list reports a *committed record*, separately from component readiness. It
does not select a version by scanning staged directories or automatically delete
previous versions. `withCommittedRegions` retains one immutable snapshot through
the complete planning promise, including the native drain. Version-specific
writer locks let downloads proceed alongside planning on an existing version;
activation and inactive cleanup wait for that version's component writer to drain.
The lock order is version ownership, then the short global metadata transaction.
Callbacks must not re-enter mutations that acquire their own lock.

`region_components.js` scopes the existing `MapPackStore` and PR40 index store to
the owned version directory. It does not duplicate PMTiles reading or the index
representation. The index installer accepts the captured PR39 manifest rather
than refetching a newer manifest halfway through an operation. The map installer
checks the component manifest's size/hash, pack identity, bounds and schema before
downloading its archive. It retains those exact manifest bytes, including
whitespace, so restart verification compares the original digest. Scoped map
opening verifies both stored files and then uses the existing PMTiles validator
and bounded random reads. Scoped index opening checks the full compressed digest,
decodes and structurally validates the existing documents. A completed component
can be verified and reused after an interrupted installation; corrupt completed
data needs explicit cleanup.

`RegionalRoutingPackReference` is the native immutable identity: safe region and
pack IDs, the regional build digest, matching bounds, and bounded file sizes and
SHA-256 digests. `RegionalRoutingPackStore` writes only the exact native directory
`<region>/<build>/<pack>`. It streams an externally supplied input in **64 KiB**
chunks to a temporary archive, checking size, digest and cancellation, syncs the
file, and writes completion last. A process-wide file lock rejects concurrent
native mutations. The native boundary independently limits storage to eight
regions, two versions per region, one archive per version and 64 inspected
directory entries. Failed updates clean only their new directory and empty
parents; existing complete bytes are immutable. Interrupted partial data remains
explicit until removal. Opens verify the exact reference and full file digests;
no directory discovery selects an active version. Cleanup rejects a different
completed identity and does not follow symlinks outside its owned directory.

The native store deliberately has no Android UI, HTTP client or JNI dependency.
Its caller must supply the Android storage estimate, bounded transfer timeouts
and cancellation, and retain request ownership before removal. Android documents
`getAllocatableBytes` and allocation as worker-thread operations that account for
reclaimable cache; that platform adapter remains part of runtime integration.
[Android storage API](https://developer.android.com/reference/android/os/storage/StorageManager).
The implementation currently hashes the complete native
archive on each open; no validation cache or phone timing is claimed. Index
decoding still needs to be connected through the existing worker for the product
flow. Maps remain solely in OPFS and routing archives solely in native storage.

These foundations are packaged with shared shell **v38**, but they are not yet
connected to application startup or the production native routing request path.
The existing phone planner continues to use its previously installed development
archives. A complete installer still needs the native transport, captured version
references in routing calls, worker/coordinator wiring, catalog, product UI and
physical consumer-region acceptance. This is not PR42 or V1 completion.

Validation uses synthetic data and real host storage:

- `tests/browser/pr42_region_versions_harness.html`: 20 cases cover inactive
  staging, component failures, cancellation, compare-and-swap, lost commit replies,
  explicit corrupt-record recovery, bounded counts, real OPFS, and concurrent
  planning/writer/activation/removal ownership. Native component acknowledgements
  in these metadata tests are synthetic.
- `tests/browser/pr42_region_components_harness.html`: 10 cases use actual OPFS,
  a synthetic PMTiles archive through the real PMTiles reader, and the existing
  Python golden POI/nature documents. They cover exact source bytes, captured
  manifests, restart reads with fixture fetches disabled, corruption, cancellation,
  failed-update preservation, completed-map reuse, and owned removal. Native
  routing completion is explicitly synthetic; no route is computed by this harness.
- `RegionalRoutingPackStoreTest`: 14 JVM cases use temporary directories and
  synthetic archive-header bytes. They cover strict identities, bounded streaming,
  completion ordering, exact reopen, cancellation, corruption, partial recovery,
  stale cleanup, storage limits and cross-instance file locks. They use no network,
  real map data, Docker or JNI routing.

Runtime integration and Fairphone regional-install evidence remain pending.

Validation completed on 2026-09-12:

- `make check`: **1,033 passed / 16 existing integration deselections**, Ruff
  passes (259 files), strict mypy passes (247 files).
- `uv run python /tmp/sugarglider-pr42-versions-browser.py`: **334 cases across
  18 browser harnesses pass**. The unchanged canonical comparison validates 50
  complete `PlanResult` fixtures and 59 GPX exports against Python.
- `uv run python /tmp/sugarglider-pr41-normal-ui.py`: the actual shared planner
  page passes Waypoint Route and Auto Tour with hike/city-bike fixtures, exact map
  geometry and GPX after fixture-server shutdown. Its native bridge is synthetic.
- Android `testDebugUnitTest lintDebug testReleaseUnitTest lintRelease assembleDebug
  bundleRelease`: **164 tests per variant**, zero failures/errors/skips, no lint
  errors/fatal findings. Lint retains the existing two debug / one release warning.
  The initial new `UsableSpace` warning was resolved by requiring the platform
  adapter to provide its estimate; no lint rule was suppressed. Kotlin compilation
  emits no new warning. Build logs use `/tmp/sugarglider-pr42-versions-android-final.log`.
- `uv run python /tmp/sugarglider-pr42-versions-artifacts.py`: all **92 shared
  assets** match the APK/AAB source bytes. The ARM64 native library remains
  unchanged and identical in both artifacts.
- `git diff --check` and the staged whitespace check pass. No new test skip or
  expected failure was added.

Android checks used Java 17 and the installed SDK at `/home/pompote/Android/Sdk`,
with the existing constrained build command from `android/`:

```sh
env JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64 \
  ANDROID_HOME=/home/pompote/Android/Sdk ANDROID_SDK_ROOT=/home/pompote/Android/Sdk \
  systemd-run --user --scope -p MemoryMax=3G -p CPUQuota=200% \
  ./gradlew --offline --no-daemon --no-configuration-cache --max-workers=1 \
  -Pkotlin.compiler.execution.strategy=in-process -Dorg.gradle.jvmargs=-Xmx1400m \
  testDebugUnitTest lintDebug testReleaseUnitTest lintRelease assembleDebug bundleRelease
```

Historical build outputs from this preparation; these paths are now superseded
by [native transfer preparation](pr42-native-transfers.md):

| Artifact | Path | Bytes | SHA-256 |
| --- | --- | ---: | --- |
| Debug APK | `android/app/build/outputs/apk/debug/app-debug.apk` | 151,626,364 | `d916a1b9e577df30083acf8d7f9e60c53c7f4f41091d18760bd97c0b13337178` |
| Unsigned AAB | `android/app/build/outputs/bundle/release/app-release.aab` | 47,381,958 | `1216c415cf7acc108b4ca0a9c1a63661e5636fa9cae3839830f6c4c766b87ec2` |

The Fairphone remains on the previously accepted `b8ebe3a` APK. These artifacts
are not the final V1 release candidate and were not installed on the phone.
