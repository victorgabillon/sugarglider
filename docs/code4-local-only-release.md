# Sugarglider 1.0.2 / code 4: local planner only

This release supersedes code 3's optional Android sharing exposure. Historical
PR27/PR44 documents describe retained future implementations, not code-4 release
capabilities. No changes to accepted code-2/code-3 artifacts are required.

## Product boundary

`V1ReleasePolicy` is fixed in source for both debug and release, with no preference,
intent, environment variable or build-property opt-in. Native Sharing UI and
server configuration are inaccessible; stored sharing origins and restored outing
screens cannot override the bundled planner. Outing deep-link registration is
removed and explicit outing intents are ignored. Every WebView creation is limited
to the bundled origin; its exact-origin bridge additionally rejects all tracking,
participant and status requests. Same-origin server API paths are intercepted and
return local 404 responses, with no network fallback. The bundled configuration
already disables shared-route and outing features.

`LocationSharingService` is absent from the manifest. Its retained implementation
also stops before initializing a publisher, location source, notification channel
or engine. Application startup does not open, restore or clear sharing session
storage. Future sharing modules and their unit tests remain. These are not a
supported or reachable release capability.

Do not delete all social modules: `planner_location.js` imports coordinate
normalization from `outing_tracking.js`, and map rendering reuses avatar helpers.
Shared web assets, routing algorithms and the Valhalla native library remain
unchanged. GPX export is an explicit document save, not social/live publication.

## Minimum permissions

| Permission | Code 3 | Code 4 | Reason |
|---|---|---|---|
| INTERNET | Yes | Yes | Explicit regional static downloads; no sharing endpoint |
| ACCESS_FINE_LOCATION | Yes | Yes | Private foreground position marker and map centering |
| ACCESS_COARSE_LOCATION | Yes | Yes | Android foreground location permission request; approximate grant handled explicitly |
| FOREGROUND_SERVICE | Yes | No | Only the removed sharing service used it |
| FOREGROUND_SERVICE_LOCATION | Yes | No | Only sharing/live tracking used it |
| POST_NOTIFICATIONS | Yes | No | Only the sharing notification used it |
| ACCESS_BACKGROUND_LOCATION | No | No | No supported background location feature |

The existing planner requires a precise grant to display its fix; an approximate-only
or denied grant leaves manual planning available. With prior location permission,
the planner can resume private foreground sampling on startup. The explicit location
control requests permission when necessary and centers/follows the map. A hidden
page suspends its watch. No foreground service is used. This does not add an
automatic route-start change: placing START remains a planner action.

## Proposed privacy-policy replacement (not published)

The exact proposed public text is in `code4-privacy-policy-proposed.md`. It replaces
optional-service/operator/retention paragraphs with an explicit local-only scope,
explains private foreground location, retains static-host connection metadata and
export/deletion caveats, and removes claims that this release sends or stores live
positions on a server. No external publication is authorized by this preparation.

## Data Safety evidence matrix (code-4 candidate only)

| Data/flow | Actual behavior | Proposed conclusion |
|---|---|---|
| Device precise/approximate position | Permission-gated foreground WebView geolocation; private current marker, no upload/outbox | Not collected/shared by the Sugarglider planner; on-device processing |
| Planned route, places, preferences | Local workers/native routing and local storage | Not collected by a routing/social backend |
| GPX import/export | Local inspection; explicit Android document picker saves to user-selected storage | No automatic upload; user-directed export, destination provider controls its copy |
| Names, participant IDs, membership, live sensor metadata | Sharing unavailable, no account or reviewer server needed | No such collection through code-4 social functionality |
| Advertising ID, analytics, ads | No integration in audited first-party code/dependencies | No app ad/analytics collection; no AD_ID permission |
| Regional downloads | HTTPS requests to GitHub Pages/Releases; host necessarily sees IP, request metadata and chosen regional filenames | Do not claim zero network metadata or unconditional “no data collected”; hosting-provider processing must be reflected in final declarations |
| Encryption | Bundled origin intercepted locally; release downloads enforce HTTPS and reject insecure transport | HTTPS for supported app download traffic; user-selected external document provider is separate |
| Deletion | Regional removal and app storage removal; exported files remain user/provider controlled | No Sugarglider account or social-server deletion flow needed for code 4 |
| Foreground service | No service component or FGS/notification permissions | No location-FGS declaration justified by code 4 |

Google's [Data Safety guidance](https://support.google.com/googleplay/android-developer/answer/10787469?hl=en)
defines collection as off-device transmission, excludes local-only processing,
and distinguishes user-directed transfers and service-provider handling. This is
a technical evidence matrix, not submitted declarations. GitHub connection-log
retention and whether it derives approximate location from IP must not be invented;
confirm applicable hosting practices before finalizing that part of the form.
The published policy and currently distributed code 3 remain unchanged until a
separately authorized rollout. Do not describe the installed code 3 as code 4.

## Regression evidence

New JVM tests cover forbidden remote origins and sharing bridge messages, plus
allowed local capabilities/routing/GPX. Python tests verify entry-point wiring,
restoration/deep-link guards, inert service/storage initialization and manifests.
Existing social module unit tests remain. Full browser suites cover local Auto Tour,
Waypoint Route, Trail run default, region readiness, private location and GPX.
The real-page startup regression uses actual UI map clicks. Device acceptance uses
the separate debug package and must preserve the Play package and regional data.

Build, merged-manifest, package asset/native equality, 16-KiB alignment, signing and
Fairphone evidence are retained outside Git in the code-4 release receipt directory.
