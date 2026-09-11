# PR44 release audit — in progress

Audit started 2026-09-11 against main `5be5780`, before enabling the production
local planner. This is a working evidence record, not a release approval. PR40
physical acceptance, PR41 production integration and PR42 region installation
remain dependencies. No signing key, developer account, domain or store submission
has been created.

## Current official requirements

| Topic | Verified requirement / implication | Official source |
| --- | --- | --- |
| Target API | New standard Android apps and updates require Android 16 / API 36 from 2026-08-31. Current `compileSdk` and `targetSdk` are already 36; `minSdk` is 26. No SDK downgrade or exemption is planned. | [Target API](https://developer.android.com/google/play/requirements/target-sdk?hl=en) |
| Native page size | Apps targeting API 35+ must support 16 KiB pages on 64-bit devices. The current guide states update enforcement from 2027-02-01. V1 will validate alignment and runtime compatibility rather than rely on that later deadline. | [Page sizes](https://developer.android.com/guide/practices/page-sizes) |
| Location foreground service | Declare the location service type and permission, and complete the Play Console FGS declaration with a demonstrable user-facing use case. User-initiated location sharing is listed as an applicable location FGS use case. | [FGS requirements](https://support.google.com/googleplay/android-developer/answer/13392821?hl=en) |
| Background location policy | Lack of `ACCESS_BACKGROUND_LOCATION` does not automatically exempt a foreground service from background-location policy review. Keep explicit activation, stop controls, disclosure and review material for screen-off outing sharing. | [Location policy](https://support.google.com/googleplay/android-developer/answer/9799150?hl=en) |
| Data Safety | Report actual off-device collection. User-directed sharing and qualifying processors have specific sharing exceptions; applicability depends on the final services and disclosures. Do not declare persisted live updates ephemeral or claim no collection because there are no user accounts. | [Data Safety](https://support.google.com/googleplay/android-developer/answer/10787469?hl=en) |
| Personal developer accounts | If the account was created after 2023-11-13, production access requires at least 12 testers continuously opted in for 14 days, followed by the production-access application. Account type/date are not yet known. | [Testing requirements](https://support.google.com/googleplay/android-developer/answer/14151465?hl=en-GB) |
| Upcoming precise-location policy | Current guidance announces further minimum-scope/location-button changes effective 2026-10-28. Recheck the policy and Play Console immediately before submission; the guide discusses ongoing sharing as a continuous-location use case. | [Sensitive permissions](https://support.google.com/googleplay/android-developer/answer/16558241?hl=en), [location-button guidance](https://support.google.com/googleplay/android-developer/answer/17033915?hl=en) |
| Android backup | `allowBackup=false` alone may not disable manufacturer device-to-device transfer on Android 12+. Explicit transfer exclusions and no-backup storage matter. | [Auto Backup](https://developer.android.com/identity/data/autobackup) |

The policy audit uses current Google/Android pages, not old repository policy
numbers. Recheck these links before the final signed build and submission.

## Existing Android evidence

- Application ID/namespace: `io.github.victorgabillon.sugarglider`; debug adds
  `.debug`. Version code/name are currently `1` / `0.1.0`.
- Release factory currently returns `DisabledNativeRouteEngine`; Valhalla
  dependencies are debug-only. Enabling this belongs to PR41 after the preceding
  required physical evidence. The existing release is not the V1 product.
- Existing debug APK includes one arm64 library,
  `lib/arm64-v8a/libvalhalla-wrapper.so`, 138,225,776 bytes. Direct ELF-header
  inspection found all three `PT_LOAD` alignments equal to 16,384.
- `build-tools/36.0.0/zipalign -c -P 16 4
  android/app/build/outputs/apk/debug/app-debug.apk`: PASS. This checks the existing
  debug artifact only. The final AAB, its delivered APKs and 16 KiB runtime still
  need validation after release local-routing integration.
- Release cleartext is disabled. Debug permits the existing restricted local
  development origins. WebView disables file/content access, mixed content,
  multiple windows and third-party cookies. The bridge uses exact origin and
  main-frame checks through `WebViewCompat.addWebMessageListener`.
- Main launcher activity is exported; the location foreground service is not.
  The custom outing deep link carries only an outing slug. It is not a capability
  transport or a substitute for a final verified web-link configuration.
- Native session ciphertext is stored with `AtomicFile` under
  `context.noBackupFilesDir`. Manifest backup flags are false; extraction rules
  now exclude all nine documented storage domains for cloud/device transfer.
  Cross-platform transfer has no corresponding iOS product or configured identity;
  its newer platform behavior remains part of the final OS audit.
- Optional external release signing configuration is prepared, with unsigned
  validation when absent and explicit failure for malformed configuration. Both
  properties and keystore must resolve outside the checkout. Permanent signing
  material remains an external user action; see [signing workflow](pr44-signing-and-bundle.md).
- Release unit compilation exposed existing common protocol tests referring to
  geometry helpers located only in the debug source set. The unchanged pure
  polyline/continuous-leg helpers now live in the common source set, and the
  architecture test still enforces their graph continuity and vertex bound.
  This does not enable the release routing engine or add a Valhalla dependency.

## Preparation validation

After relocating the helper and updating both source-location assertions,
`make check` passes with 1,013 tests / 16 existing integration tests deselected,
Ruff and strict mypy (240 source files). Initial debug JUnit completed all 136
tests with zero failures/errors/skips, and debug lint completed with zero errors.
The initial combined debug/release Gradle process exceeded the deliberately low
1.5 GiB process-scope limit; it was not a test assertion failure. Fresh release
checks use a separate 2 GiB scope. Their first compile found the source-set issue
above. After correction, **133 release JUnit tests pass with no failures/errors/
skips, release lint has zero errors, and `bundleRelease` succeeds**. The exact
command includes `--no-daemon --no-configuration-cache --max-workers=1`, a 768 MiB
heap/512 MiB metaspace and in-process Kotlin compilation. The combined release
run took 6 min 54 s under a one-CPU scope. Debug regression and disposable signing
pipeline checks are still running.

The initial unsigned preparation artifact is
`/tmp/sugarglider-v1-pr44/android/app/build/outputs/bundle/release/app-release.aab`,
3,528,250 bytes, SHA-256
`ac4e278c5efda8742eed4640a6992dc4439dde113d4ad24a055ee9b6085ec798`.
It contains no native library because production local routing remains disabled.
It is not the final V1 artifact; later builds/signing validation may supersede it.

Debug lint's nine warnings remain visible: available dependency/Gradle updates,
debug arm64-only ChromeOS coverage, and explicit debug cleartext. Release lint
and dependency/security review are separate gates. Do not suppress warnings or
change the pinned native engine without reviewing graph compatibility and
repeating required device evidence.

The upstream 0.5.1 Kotlin actor delegates each request to a JNI function that
constructs a native actor for that call. The app's cached object is the Kotlin
wrapper, so its current initialization timer must not be presented as complete
native initialization or persistent native graph-cache evidence. The JNI error
path also prints exception text, and the inspected phone configuration contains
the library's default stdout logging sections. These findings need explicit
runtime logging/configuration and failure-path review before production enablement;
no claim of a silent native library or native actor reuse is justified yet.
[Pinned actor source](https://github.com/Rallista/valhalla-mobile/blob/0.5.1/android/valhalla/src/main/java/com/valhalla/valhalla/ValhallaActor.kt),
[pinned JNI source](https://github.com/Rallista/valhalla-mobile/blob/0.5.1/src/wrapper/main.cpp).

The current AndroidX WebKit release notes list 1.17.0 and mention a new lint rule
for missing renderer-crash handling. The application presently has no
`onRenderProcessGone` handler; add lifecycle-safe recovery and verify it before
calling the release hardened. Upgrading the support library alone is not a
substitute for that behavior or an up-to-date device WebView implementation.
[WebKit release notes](https://developer.android.com/jetpack/androidx/releases/webkit?hl=en).

## Permission inventory

| Permission | Existing use |
| --- | --- |
| `INTERNET` | Application/web assets, optional sharing/live HTTP, and future explicit region downloads |
| `ACCESS_COARSE_LOCATION` | Required companion to fine permission and Android location consent choices |
| `ACCESS_FINE_LOCATION` | Explicit private planner location actions and explicitly started outing sharing |
| `FOREGROUND_SERVICE` | Ongoing, visible native outing-sharing service |
| `FOREGROUND_SERVICE_LOCATION` | Declared service type for that sharing session |
| `POST_NOTIFICATIONS` | Ongoing sharing/Stop notification; permission required before native Start on supported Android versions |

`ACCESS_BACKGROUND_LOCATION`, wake locks, boot receivers, background jobs,
activity recognition, Health Connect, advertising identifiers and broad external
storage permissions are absent from the current source manifest. Re-audit the
merged release manifest and dependency contributions before release.

The existing foreground service starts only from a visible activity after the
native disclosure and precise-location/notification consent. It remains
`START_NOT_STICKY`, never restarts automatically after process death/reboot, and
retains one latest pending fix. Keep this minimum Android permission scope.
Prepare the Play FGS/location-policy explanation; do not claim prior approval.

## Privacy findings requiring final work

The native disclosure now explicitly describes sending precise location and
briefly retaining recent updates for viewer reconnection, alongside deliberate
screen-off sharing, unlisted viewers, persistent notification, Stop and uncertain
clearing. PR24's bounded replay log defaults to 15 minutes / 1,000 events per outing
in PR43. The current-position table remains authoritative and there is no
activity-track API. Device presentation of the corrected disclosure remains
pending.

The final inventory must cover:

- Local plans, private map location and locally inspected GPX; no routing upload
  merely to compute a route in the intended production local planner.
- Explicit shared snapshots (90-day production default), independent outing
  snapshots/membership (30 days), nicknames/avatar choice and random identifiers.
- Optional precise live coordinates and accuracy, server freshness/expiry,
  bounded reconnection replay, and the latest-only browser/native pending sample.
- Capability tokens in the permitted in-memory or explicitly remembered/encrypted
  stores, with only hashes in server persistence; no tokens in GET models/URLs/logs.
- PR43 private structured logs and backups: backups omit all live position/replay
  rows, retain snapshots/membership for seven days when the supplied timer runs,
  and require an operator-controlled encrypted off-host destination.
- Online map-tile requests where the final product still uses them, static region
  downloads, TLS/server providers, their request metadata and applicable policies.
  The release planner/region UI must establish the final network inventory.
- Actual deletion/expiry paths and backup restoration limits. Logical deletion
  must not be described as immediate forensic erasure.

Final privacy-policy publisher/contact/URL, Data Safety selections, location/FGS
declarations, a short demonstration script and the account-specific submission
checklist remain pending. No analytics or advertising integration has been found
in this initial source audit; the final dependency/network review is still due.

## Outstanding technical gates

Production local planning and a useful installable region; final release origin
and first-launch packaging; canonical local result/export behavior; all mandatory
Fairphone cases; final permission/backup/disclosure/link/icon audit; external
signing setup; release unit/lint/bundle validation; final AAB path, size and hash;
delivered APK alignment and runtime verification; approved public privacy identity;
and actual human Play Console declarations/submission.

The current main still asks for a server origin on first launch. PR41 must supply
a bundled first-launch path with a stable trusted origin and preserve OPFS origin
identity plus existing same-origin participant-authority isolation. This needs
deliberate integration, not merely enabling the release native factory.
