# Privacy and Play disclosure preparation

Working draft, 2026-09-12. Do not publish as a final policy. The publisher's legal
identity, contact, approved hosts, public policy URL and final physical network
acceptance are pending. The bundled production local planner and regional
installation path are implemented. This inventory describes their current code
and the supplied PR43 production defaults;
it is not a claim that every release acceptance gate has passed.

## Code-backed inventory

| Data | Trigger and destination | Retention and control |
| --- | --- | --- |
| Planning inputs and routed geometry | The bundled Android planner uses local Valhalla and installed local map/POI/nature data. Only an explicit share/save action sends a snapshot to the optional service. The separate development/reference web planner can send its requests to its configured reference server; that is not the bundled Android planner. | Editable planner state and user-chosen local copies. Final offline release behavior requires device evidence. |
| Local GPX inspection/export | File chosen or exported by the user; inspection runs in the browser. | The app does not upload inspection files. Files exported to another app or storage are controlled there. |
| Shared route snapshots | Explicit Save/Share submits the exact request, route, analysis, names and deliberate stops. Anyone holding its unlisted link can read it. | Production default 90 days, configurable shorter; owner capability authorizes earlier deletion. |
| Outings and membership | Explicit creation/join: outing title, nickname, mascot choice, random public participant ID and optional independent route snapshot. | Production default 30 days, configurable shorter; owner deletion or participant leave. Outing snapshots remain independent of their source saved route. |
| Live position | Explicit Start with permission: precise coordinate, accuracy, capture time and sensor-provided altitude/speed/heading when available. Sent through authenticated HTTPS and visible to holders of the outing link. | One current position per participant. Stale after 120 seconds; expires after 3,600 seconds without replacement. Stop clears current position when confirmed; uncertain clearing leaves the expiry warning. |
| Reconnection replay | Live updates and clear/leave events retained to reconnect viewers. | At most 1,000 events per outing and 15 minutes under production settings, pruned by requests/cleanup. This temporarily contains recent coordinates; there is no activity-track or historical-location API. |
| Capabilities | Random owner/join/participant secrets authorize their exact actions. Server stores hashes. Owner/join remain out of browser storage; participant memory is default. Join fragments are scrubbed immediately. | Explicit Remember may persist only the whitelisted participant session in IndexedDB. Native tracking stores one participant session encrypted with Android Keystore in no-backup storage. Forget/removal clears the matching remembered identity. |
| Pending location | Browser Remember may retain one latest token-free sample; native service may retain one latest encrypted fix. | No coordinate history. Restored browser sample requires explicit foreground Start/Resume and is discarded if older than 15 seconds. Stop/Forget/removal/expiry clear matching pending state. |
| Offline snapshots | Explicit Save for offline use copies only public immutable route/outing data. | At most eight copies; no capabilities, live positions, replay or cursors. Optional browser storage may be evicted. Clear offline data removes these copies. |
| Map and regional downloads | Explicit static pack downloads reveal IP and requested files to the chosen host. An online raster view, where enabled, reveals IP and tile coordinates to its provider. | The bundled planner uses installed regional maps with no raster fallback. Static publication is prepared but awaiting approval; no host is represented as live. Separate reference web maps can use the configured online raster provider. No bulk raster caching. Regional files remain local until explicit removal or app-data removal. |
| Service request metadata | Supplied PR43 app log: random request ID, fixed operation category/method, status and duration. No request URL, slug, body, capability, IP or coordinate in these logs. | Container logs have bounded rotation. Rate limiting uses a process-salted IP hash in bounded memory, with idle expiry. Proxy access/request logs are disabled in the supplied configuration; infrastructure-provider metadata must be separately confirmed. |
| Backups | Supplied daily backup copies snapshots, outings, membership and capability hashes. | No live-position or replay rows. Completed backups are pruned after seven days by the supplied timer. Off-host encrypted backups and retention require operator configuration. |

Primary code under `src/sugarglider`: `social_server/settings.py`,
`social_server/http.py`, `social_server/sqlite_repository.py`,
`outings/live_service.py`, `outings/live_sqlite_repository.py`,
`saved_routes/sqlite_repository.py`, `web/static/pwa_store.js`,
`web/static/outing_durable_session.js`, `web/static/region_product.js`, and
`web/static/regional_map_store.js`. Android sources include
`NativeSecureTrackingStore`, `NativeOutingApi`, `LocationSharingService`,
`RegionalRoutingDownloader` and `MainActivity`. Recheck the deployed operator
settings and the final merged artifact before publishing.

No advertising, analytics, advertising ID, account registration or proprietary
location SDK was found in the first-party source/dependency declarations examined.
Android/WebView, hosting and any enabled online map provider are still third-party
components/services; do not describe the app as having no third parties.

## Privacy-policy source text

Before publication, supply the actual publisher/contact and approved policy URL,
replace the host paragraph with named providers and verify the final release
against every statement below.

Sugarglider helps you plan outdoor routes and optionally share routes and outings.
After a supported region is installed, the Android V1 planner calculates routes
on your device. Planning itself does not send your route to a Sugarglider routing
server. A map-region download makes an Internet request to the region host.

You choose whether to share a route or join an outing. A shared snapshot includes
its route coordinates, names, selected places and planning details. An outing
includes its title, participants' chosen names and any routes they attach. Links
are unlisted, not private to named recipients: anyone who receives an unlisted
link can view its contents. Do not share a link with someone you do not want to
see that information.

Live location sharing starts only when you explicitly start it and grant the
required permissions. The Android sharing service can continue sending precise
location when the app is minimized or the screen is locked. It does not restart
a sharing session automatically after process death or reboot. A visible notification
provides Stop. We receive location, accuracy, capture time and available sensor
altitude, speed and heading. We do not infer progress along your route or create
an activity track. We keep your current position and a short, bounded log of
updates to let viewers reconnect.

The production defaults retain shared routes for 90 days and outings for 30 days.
A position becomes stale after two minutes and expires after one hour without an
update. Reconnection updates are limited to 15 minutes and 1,000 events per outing.
Stop removes the current position once server clearing is confirmed. If the
network prevents confirmation, the app warns that it may remain visible until
expiry. Stop does not promise to erase already delivered updates from viewers'
devices or the short reconnection log immediately.

The owner can delete a shared route or outing using its owner capability. A
participant can leave using their participant capability. These are secret
controls, not account passwords. If you lose them, the app cannot reconstruct
them. Local Remember and offline-save actions are optional; Forget and Clear
offline data remove the corresponding local copies. Native sharing retains at
most one encrypted participant session and one latest pending fix. App removal
does not recall files you exported or copies other viewers made.

The supplied service writes limited operational logs without route coordinates,
capabilities, unlisted URLs or request bodies. Its backups omit live coordinates
and recent live events; backups of shared content and membership may remain for
seven days after deletion. Logical deletion is not immediate forensic erasure.
Restoring an older backup can restore previously deleted, unexpired shared data;
operators must apply the documented recovery/deletion procedure.

The app has no advertising or analytics integration in the audited release code.
Its network and map providers can receive connection metadata when their services
are used. The final policy must identify those providers and their relevant
retention/privacy terms. Contact the named publisher using the published contact
for privacy questions; do not send secret capability links or live coordinates
unless needed and requested through an appropriate channel.

## Play Console Data Safety working answers

Use the current [Google Data Safety guidance](https://support.google.com/googleplay/android-developer/answer/10787469?hl=en)
and the final implementation. The publisher must submit the actual answers.

- Collection: **yes**, optional snapshots, membership and live location;
  persistent storage is not ephemeral processing.
- Precise location: **yes, optional**, live coordinates and deliberately uploaded
  routes, for app functionality. Sensor altitude/speed/heading can accompany fixes.
- Personal information: review Name and User IDs for nicknames and random
  participant identifiers; account absence does not mean identifier absence.
- User content/files: review titles, place names and shared route snapshots.
  Local-only GPX inspection does not upload files.
- Sharing: assess user-directed sharing and service-provider exceptions for each
  recipient and purpose.
- Encryption: final release connections must use HTTPS; verify manifest/network
  evidence. Debug HTTP is outside that claim.
- Deletion: document capability controls, Forget/Clear, expiry, backup limits and
  lost-capability assistance. There is no account system.
- Ads/analytics: none found; confirm final dependencies and provider logging,
  including applicable diagnostic/interaction metadata categories.

## Sensitive-permission / FGS review material

The manifest requests fine/coarse location, location foreground-service permission
and notifications; it does not request `ACCESS_BACKGROUND_LOCATION`. The user
starts continuous outing sharing from a visible activity after disclosure.
Stopping closes that sharing session. Removing screen-off sharing would remove
the existing outing feature; V1 retains it within this minimum permission scope.

Draft use-case statement: “The user explicitly shares their current position with
an outing. A location foreground service keeps that chosen session active when
the screen is locked. An ongoing notification and in-app Stop end the session.
Location is not used for advertising, analytics or a recorded activity track.”

A foreground service is not a blanket exemption from background-location review.
The ordinary local planner works without continuous sharing, but removing
screen-off sharing would remove the existing explicit outing session capability.
This implementation retains that optional feature with no
`ACCESS_BACKGROUND_LOCATION`, no automatic start/restart and a visible Stop.
Its use case and store listing must be reviewed by the publisher; removal or
restricted distribution is a product decision if the use case is rejected.

The publisher must complete the current [FGS declaration](https://support.google.com/googleplay/android-developer/answer/13392821?hl=en)
and any applicable [background-location review](https://support.google.com/googleplay/android-developer/answer/9799150?hl=en).
No Google approval is implied. The current [minimum-scope guidance](https://support.google.com/googleplay/android-developer/answer/17033915)
states that precise-location declarations open in November 2026 with compliance
required on 2027-01-27; the one-time location button requirement applies to apps
targeting Android 17 / API 37+. This release targets API 36. Recheck the live
Play Console deadlines before upload; earlier draft October dates are superseded.

Suggested 28-second recording, using a synthetic outing and consented test
location: 0–5 s show the outing and explicit Start; 5–12 s show the prominent
disclosure, permission consent and policy link; 12–18 s show sharing active and
the ongoing notification after minimizing; 18–24 s press notification Stop;
24–28 s return to the app and show stopped/cleared state. The actual final app
must demonstrate this; do not edit away permission or clearing failures.

## Publication gates

The native Privacy action opens local details without navigating away from the
current plan. It is also available within the Start disclosure without dismissing
or consenting to that disclosure. An approved public HTTPS URL can be embedded
with `SUGARGLIDER_ANDROID_PRIVACY_POLICY_URL`; when absent, the app does not invent
an online destination. The public link is therefore still a release gate.

Final publisher/contact/public URL; approved social/static hosts and their data
practices; truthful in-app policy link; final disclosure presentation and device
recording; final release network/permission audit; Data Safety/content-rating
selections by the publisher; current policy recheck before submission. These are
open items, not completed declarations.
