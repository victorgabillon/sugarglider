# Android V1 submission and device acceptance

Working release checklist, 2026-09-12. This is not a submission or a claim of
Google approval. The existing Play application ID is
`io.github.victorgabillon.sugarglider`; do not create a replacement app or install
a disposable certificate over its existing Fairphone installation.

## Publisher submission material

- Confirm the existing upload-key/App Signing configuration and the highest used
  version code on every track. The proposed update is code 2 / name 1.0.0.
- Approve the public publisher identity, privacy contact, policy text and active
  HTTPS policy URL. Embed that URL with
  `SUGARGLIDER_ANDROID_PRIVACY_POLICY_URL`, and verify the in-app link and policy
  from a device before upload. The local Privacy screen is available now.
- Review the [privacy and Data Safety draft](pr44-privacy-data-safety.md), precise
  location justification, location foreground-service declaration and applicable
  background-location review. Absence of `ACCESS_BACKGROUND_LOCATION` does not
  establish an exemption for screen-off sharing.
- Complete audience, content rating, ads, app access and other applicable App
  content declarations in the existing Play Console. Do not invent an age rating,
  account eligibility, review access, legal identity or Google approval.
  [Google review preparation](https://support.google.com/googleplay/android-developer/answer/9859455).
- Prepare screenshots from the final app and a consented synthetic outing demo.
  The [28-second shot list](pr44-privacy-data-safety.md) shows disclosure, consent,
  screen-off notification and Stop. Do not commit screenshots or GPX fixtures.
- Inspect the final AAB in Play's internal testing/pre-launch workflow and record
  actual findings. Upload/submission/publication requires the publisher's explicit
  authorization. Use the existing package and signing identity.

Suggested listing copy after regional/device acceptance: “Plan outdoor routes
on your Android phone. Download a supported region to view its map and create
Waypoint Routes or Auto Tours locally, then export GPX. Optional outings let you
share a route or explicitly share your current position.” Name the available
region and supported ARM64 devices accurately. Do not claim worldwide coverage,
turn-by-turn navigation, activity recording, a safety service, routing-server
parity, guaranteed access or any unproven profile/POI behavior.

## Permission inventory

The inspected release merged manifest has exactly these six permissions:

| Permission | Use and boundary |
| --- | --- |
| INTERNET | Explicit static regional downloads, optional sharing and external policy page |
| ACCESS_COARSE_LOCATION | Android paired coarse/fine runtime request and user-chosen location features |
| ACCESS_FINE_LOCATION | Explicit precise current-location/sharing request; precise permission required for native sharing |
| FOREGROUND_SERVICE | User-started native outing sharing session |
| FOREGROUND_SERVICE_LOCATION | The non-exported location service's declared type |
| POST_NOTIFICATIONS | Native sharing requires notification permission and an ongoing notification with Stop |

There is no background-location, storage, boot, wake-lock, advertising-ID or broad
package-query permission. The launcher/deep-link Activity is exported. The
AndroidX profile-install receiver is exported with the system `DUMP` permission;
it does not expose participant authority. The AndroidX initializer provider and
location service are not exported. GPX saving uses the user's system document
picker; the app declares no sharing file provider or broad storage access.

## Required final Fairphone matrix

Record APK/AAB source commit, signature type, size/hash, phone/WebView versions,
selected region/build and exact request fixtures with each run. Keep synthetic
fixture coordinates distinct from the user's real position. Never record secrets,
real precise-location logs or capabilities. ADB/CDP observation is test machinery;
the consumer operation itself must be available through normal release UI.

| Scenario | Required evidence | Current status |
| --- | --- | --- |
| Fresh consumer-region install | Real Download action, four integrity checks, activation, measured duration/storage | Pending approved static host and unlocked device |
| Normal local planning | Waypoint + Auto Tour, pedestrian + bicycle, selected production region, deterministic repeat, no routing API | Earlier Marly debug/shared-engine evidence only; final region/build pending |
| Six profiles | Public selection/capability identity; real reachable requests or truthful failures for each | Shared-engine automated coverage; final regional device cases pending |
| Offline restart | Installed map/POI/nature, routes and GPX after restart with backend inaccessible | Pending final region; do not change hotspot/radios |
| Remove/reinstall/cancel | Real product controls, retained valid version, explicit interruption/recovery | Automated coordinator/storage coverage passes; physical pending |
| No region / outside coverage | Disabled Generate or explicit failure with unchanged request and no fallback | No-region locked-device startup observed on product build; final visible cases pending |
| Rotation and resizing | Plan, current page and focus remain usable; no automatic geolocation or sharing | Pending final implementation/device check |
| Background/resume / process restart | UI truth and region persistence; sharing lifecycle and uncertain GPX outcome preserved | Pending final build |
| Renderer loss | Explicit Reopen, truthful unsaved/GPX warning, native Stop available, no implicit Start | Callback unit coverage; physical recovery pending |
| Permission denied | Location/notifications denial remains explicit; local planning still usable | Prior architecture tests; final physical pending |
| Location disabled | Explicit native-sharing failure with no hidden fallback | Pending; changing the user's device setting requires separate per-test agreement |
| GPX save/export | System Cancel + Save, one track/segment, exact canonical geometry, no routing during export | Earlier real device Marly evidence; final production region/build pending |
| Social unavailable | Local planner remains independent; social error explicit | Architecture/browser evidence; final physical pending |
| Social available | Approved HTTPS service, synthetic sharing/outing/Start/Stop and cleanup | No approved production endpoint configured |
| Release identity / upgrade | Existing upload-signing path, compatible update with retained user data | Disposable host pipeline only; existing Play app untouched |
| Launcher / large screen | Existing artwork legible, system-bar/cutout/keyboard controls visible | Legacy bitmap icon retained; adaptive/launcher presentation not asserted |
| 16 KiB runtime | Compatible runtime launch and local route on a 16 KiB device/emulator | Binary/package alignment is separate evidence; runtime pending |

Do not use `pm clear`, uninstall the Play app or replace it with a disposable
signature. Fresh state can use app-level region removal or a separately named test
application. Browser simulations and unit tests cannot close physical rows.

## Current policy dates

Official sources were rechecked on 2026-09-12. Standard new apps and updates must
target API 36 from 2026-08-31. This project compiles/targets 36 and supports API
26+ ARM64. [Target API requirement](https://developer.android.com/google/play/requirements/target-sdk).

The current 16 KiB guidance states that API 35+ apps on 64-bit devices must support
16 KiB pages, with unsupported update releases blocked from 2027-02-01. Verify the
actual delivered native ELF/APK alignment and runtime; bundle creation alone is
insufficient. [16 KiB guidance](https://developer.android.com/guide/practices/page-sizes).

The current precise-location guidance lists November 2026 declaration availability
and 2027-01-27 compliance, and associates the transactional location button with
API 37+ targets. Earlier draft October dates are superseded. Recheck actual Console
requirements before submitting this API 36 release.
[Minimum location scope](https://support.google.com/googleplay/android-developer/answer/17033915).
