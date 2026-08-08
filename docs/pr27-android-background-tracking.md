# PR27 installable Android shell and screen-off location sharing

## Product boundary

PR27 adds an installable Android application with package ID
`io.github.victorgabillon.sugarglider`. It is a Kotlin WebView shell around the existing
Sugarglider browser application plus a native location foreground service. The APK does
not contain the Python API, SQLite databases, GraphHopper, OSM data, or an independent
outing application. A reachable Sugarglider server remains required.

Ordinary browsers are unchanged. Without the origin-injected Android bridge, the outing
page continues to use PR25's explicit, foreground-only `watchPosition` tracker and
PR26's separately opt-in browser persistence. Public outing SSE remains in the web page;
the native service never opens or duplicates an EventSource.

## Architecture and trust boundary

`MainActivity` owns server-origin configuration and one recreated WebView. It enables
JavaScript for the existing first-party interface, disables file/content access, blocks
mixed content, cancels TLS errors and HTTP authentication prompts, and permits in-WebView
navigation only within the configured exact origin. Ordinary external links open in the
system browser. Changing the origin first requires the complete shutdown of any active
or stopping native session,
then destroys the WebView and its message listener before creating a new boundary.

The bridge uses AndroidX WebKit's
`WebViewCompat.addWebMessageListener`, never `addJavascriptInterface`. Its allowlist is
the single normalized configured origin. Native code additionally checks the source
origin, main-frame flag, and active WebView object. Messages use schema version 1 and
strict field allowlists:

- web to native: `hello`, `get_status`, `start_tracking`, `stop_tracking`,
  `ack_terminal_failure`;
- native to web: `hello_result`, `tracking_status`, `start_result`, `stop_result`,
  `permanent_failure`.

Every message has `schema_version`, `request_id`, and `type`. Start alone carries the
exact origin, outing slug, public participant ID, participant capability, outing expiry,
and current sequence. Native replies carry only safe identity and status fields: outing
slug, participant ID, active/state, last publication time, pending flag, and an optional
Stop warning. They never return a token or coordinate. Each document creates a
cryptographically random 128-bit page nonce. Bounded request IDs include that nonce and
a monotonic page counter, and the Activity ledger keys idempotency by nonce plus request
ID. Top-level navigation invalidates the prior reply channel, so an old document's cache
or late reply cannot enter its successor. Requests are operation-owned; another origin,
subframe, stale WebView, malformed JSON, extra authority field, unknown type, version,
or stale reply is ignored.

The first-party `outing_native_bridge.js` performs a handshake. Only a trusted native
bridge replaces the browser tracking backend. It never starts both trackers, never
starts from reload or restored participant state, and applies native status only when
both outing slug and participant ID still belong to the displayed outing. A status
handshake can restore the display of an already-running native service without returning
its participant token. Public live viewing remains capability-free and independent.

## Server configuration and network policy

First launch shows a native origin form. It stores only normalized scheme, host, and
optional non-default port in Activity-private preferences. User info, paths other than
`/`, query strings, fragments, missing hosts, and invalid ports are rejected. Release
builds accept HTTPS only and set `usesCleartextTraffic=false`; no release network-security
override exists. Debug-only manifest/resources allow HTTP only when native validation
also identifies localhost, emulator, link-local, or RFC1918 private-LAN addresses. The
debug default is `http://10.0.2.2:8000`.

Native PR24 calls use the configured origin and these existing endpoints exactly:

```text
PUT    /v2/outings/{slug}/participants/{participant_id}/position
DELETE /v2/outings/{slug}/participants/{participant_id}/position
GET    /v2/outings/{slug}/live
```

PUT and DELETE send the participant capability only in
`X-Sugarglider-Participant-Token`. Path identities are strictly validated. The platform
HTTP client uses default TLS verification, no cookie handler, fixed connect/read limits,
bounded response reads, reliable stream/connection closure, and redirect following
disabled. A redirect therefore never receives participant authority at another URL.
Response bodies and sensitive fields are not logged.

## Explicit disclosure and permissions

Native sharing can begin only from the existing Start button while `MainActivity` is
visible. Before permissions, a native disclosure requires confirmation and explains:

- continuous precise location during the active session;
- continued sharing while minimized or screen-locked;
- visibility to anyone holding the unlisted outing link;
- retention of one latest current position rather than a historical track;
- the persistent notification and both Stop controls;
- possible server visibility until expiry after an uncertain clear.

The manifest declares only Internet, coarse/fine location, location foreground-service,
and notification permissions. It deliberately omits `ACCESS_BACKGROUND_LOCATION`:
Android permits a user-started location foreground service to continue with its visible
ongoing notification, which is the product behavior required here. Approximate-only
location is rejected because trail sharing requires precise fixes. Android 13 and newer
must grant notification permission before Start. Disabled device location services leave
sharing stopped and offer the system Location settings. No permission request occurs on
install, launch, load, reload, join, restore, reconnect, or reboot.

## Foreground service and notification

`LocationSharingService` is non-exported, declares foreground type `location`, promotes
itself promptly with `ServiceCompat.startForeground`, and returns `START_NOT_STICKY`.
`LocationManager` supplies GPS-capable precise fixes through a replaceable `LocationSource`
interface. The ongoing **Sugarglider live location** notification reports waiting,
last-update, offline-delay, or stopping state without showing a token, coordinate, or
unlisted link. It has explicit Open app and idempotent Stop sharing actions.

There is no boot receiver, WorkManager, AlarmManager, exact alarm, background sync,
battery-optimization exemption, wake lock, proprietary background-location SDK, or
hidden restart. Pressing Home or locking the screen leaves the user-started foreground
service independent of the Activity and service worker. Android force-stop ends it.
After process death its `START_NOT_STICKY` service is not recreated; a new application
process clears any orphaned encrypted record and requires a fresh visible Start.

OEM battery managers may still stop or throttle foreground services. Sugarglider does
not bypass those policies. Device-specific unrestricted-battery settings may improve
reliability, but are not requested by the app and do not change the no-auto-start rule.

## Location, publication, sequence, and retry

Required fixes must have finite latitude `[-90,90]`, longitude `[-180,180]`, accuracy
`[0,10000]`, and a valid positive wall-clock timestamp. Optional altitude
`[-1000,12000]`, speed `[0,150]`, and heading `[0,360)` become null when invalid. The
captured time is exactly `Location.time`; native code never clamps, invents, snaps,
smooths, or replaces it.

Acquisition may be faster than publication. The first valid fix publishes promptly;
accepted updates are at least five seconds apart. One PUT is in flight and one newest
pending fix replaces its predecessor. Offline operation keeps acquiring only while the
foreground service is active, atomically replaces that one sample, shows an offline
notification state, and uses one exponential retry timer capped at 30 seconds. Restored
connectivity publishes only the latest fix, never a backlog.

Sequences remain in JavaScript's safe range and use
`max(current epoch milliseconds, last accepted + 1)`. Exhaustion stops safely. On one
`outing_position_sequence_conflict`, native code reads `/live`, uses only the matching
participant's sequence, advances, and retries the newest sample once. A second conflict
does not loop. `outing_position_invalid` discards that fix. Transport and service
unavailability retain only the newest fix for retry.

A direct PUT or sequence-recovery `outing_not_found` stops acquisition and timers,
removes the matching encrypted identity/sample, stops the service, and sends the web
page only a monotonic event ID, affected slug, participant ID, and safe code. The
application repository retains that one-shot safe event across Activity/WebView
recreation until the matching page acknowledges it after PR26 identity/outbox cleanup.
The page clears matching in-memory authority immediately but acknowledges only after
best-effort durable cleanup succeeds; storage or acknowledgement failure leaves the
retained event retryable without producing an unhandled rejection.
Critical cleanup matches the session start identity and runs even after concurrent Stop
invalidates UI ownership; it cannot clear or mutate a newer participant/session.

## Encrypted latest-only state

The app-private record has schema/version and strict size/field validation. It contains
one session with exactly server origin, outing slug, participant ID, participant token,
outing expiry, last accepted sequence, and start time, plus at most one pending sample
with sample ID, captured/queued times, coordinate, accuracy, and optional sensor values.
It contains no owner, invitation, join, or saved-route authority; history, previous
coordinate, route, participant list, event/cursor, analytics ID, or sequence list.

The record is encrypted with a non-exportable Android Keystore AES key using
`AES/GCM/NoPadding`, a fresh random 96-bit IV, authenticated envelope metadata, bounded
ciphertext, and `AtomicFile` replacement. Unsupported, malformed, truncated,
authentication-failed, or expired records are deleted and remain stopped. Every
conditional mutation matches origin, slug, participant ID, token, and session start
time. Latest-sample writes return a typed stored, ignored-older, session-mismatch, or
storage-failure result; an out-of-order GPS callback is ignored instead of stopping the
service. Store write/delete failures are caught on the serialized engine scheduler and
surface a safe, honest stopped/warning state. Each fix atomically replaces only an older
sample. A successful PUT conditionally deletes the
matching `sample_id`, so a late success cannot erase a newer fix.

## Stop and uncertain clearing

The in-app and notification actions enter the same idempotent state machine. Stop first
advances generation ownership, removes location updates, cancels cadence/retry/expiry,
prevents new PUTs, clears encrypted authority and pending state, and retains only the
captured session in memory for one authenticated DELETE. The single network executor
serializes DELETE after any already-dispatched PUT, with bounded HTTP timeouts. Local
sharing and the notification end regardless of network outcome.

A definite clear produces the normal stopped state. A timeout, transport failure,
uncertain PUT, or unsuccessful clear reports exactly the honest meaning:

> Sharing stopped on this device. The last position may remain visible until server
> expiry.

Late callbacks capture generation, slug, participant ID, and sample ID. They cannot
publish, retry, clear newer state, alter a newer notification/WebView, or restart the
service. Matching permanent authenticated cleanup remains the intentional exception.
The native lifecycle remains busy in `stopping` until the Service actually completes
shutdown. A same- or different-participant Start and Change server are rejected during
that interval. Android start-ID ownership also prevents a queued completion from an old
Stop from stopping a subsequently delivered explicit Start.

## Build, install, and physical-device setup

Install JDK 17 and Android SDK 36, then run:

```sh
cd android
./gradlew --no-daemon testDebugUnitTest lintDebug assembleDebug
cd ..
adb install -r android/app/build/outputs/apk/debug/app-debug.apk
```

The APK is `android/app/build/outputs/apk/debug/app-debug.apk`. An emulator can reach a
host server at `http://10.0.2.2:8000`. A physical phone needs the server bound to a
reachable LAN address with firewall access, entered as its private IP and port in a debug
build, or a normally trusted HTTPS origin. Custom trust managers and certificate bypasses
are intentionally absent. `sugarglider://o/{slug}` is a narrow optional capability-free
deep link to the configured origin's `/o/{slug}`; it accepts no query, fragment, or token.
No verified HTTPS App Link is claimed.

Release signing, a keystore, Google Play publication, Play foreground-location policy
declarations, store disclosure review, production hosting, and Digital Asset Links are
future deployment work and intentionally out of scope.

## Manual device acceptance procedure

Do not mark a step passed without a real emulator/device result.

1. Build the debug APK and install it with the command above.
2. Configure a reachable server, then create or join an outing in the existing UI.
3. Press Start, confirm the native disclosure, and grant precise location and notifications.
4. Verify the ongoing notification and the same public outing from a second browser.
5. Press Home for several minutes, then lock the screen for several minutes; verify updates continue.
6. Enable airplane mode and generate several fixes if possible; restore connectivity and verify only the latest fix publishes.
7. Stop from the notification; verify location acquisition ends and either DELETE succeeds or the honest uncertain-clear warning appears.
8. Reopen the app and verify sharing did not restart. Reboot and verify no auto-start.
9. Inspect the merged manifest for the non-exported location service and absence of `ACCESS_BACKGROUND_LOCATION` and `BOOT_COMPLETED`.
10. Inspect logcat and confirm no participant token or coordinate appears.
