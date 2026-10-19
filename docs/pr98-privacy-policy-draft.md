# Sugarglider V2 privacy policy — DRAFT FOR REVIEW

**Not approved, not effective and not published.** Intended for the future
V2 offline-capable Android release. The current published policy is unchanged.
Effective date and final public URL: **publisher decision required**.

The current published page identifies Sugarglider as the public developer,
Victor Gabillon as publisher/data controller, and VictorGabillon@gmail.com as
privacy contact. Those are existing published facts, not newly authorized V2
publisher details; the publisher must confirm them for the final policy. No new
identity, contact, approval or effective date is invented here.

## Offline route planning and elevation

After downloading a supported region, Sugarglider calculates routes, displays
regional maps, analyzes elevation and exports GPX on the device without requiring
an internet connection. The region and its required files must be installed,
verified and cover the route. Normal local planning does not send planned routes
to a Sugarglider routing or sharing server. GPX inspection is local. Elevation
and D+/D− are terrain estimates, not surveyed measurements; access and current
conditions are not guaranteed. This is not a promise that Android/WebView services
are silent whenever the device has a connection.

## Private foreground device location

With permission, Sugarglider uses foreground location to show a private position
and center/follow the map. A previous permission grant can allow this to resume
when the planner reopens. The watch is suspended when the page is hidden. Denying
or revoking location permission leaves manual planning available. The current
planner requires precise permission for a fix; approximate-only permission does
not enable a hidden upload or background sharing service.

First-party planner code does not automatically upload the current position.
Android and its chosen location implementation are platform services; this draft
does not claim their processing is entirely local. Background location permission
and a location-sharing foreground service are absent from this packaged release.

## Local storage and deletion

Regional maps and Places/Nature indexes use browser storage; native routing and
terrain files use the application's private storage. Preferences and the trail
profile can be stored locally. Browser storage may be unavailable or evicted;
missing required data is reported and no remote routing substitute is used.
Use the region removal controls to remove a region. Android app storage controls
or uninstallation remove local application data. Backup/device-transfer exclusions
are enabled. Deletion is not a promise of forensic erasure or deletion of copies
held by hosting, platform or external storage providers.

## Explicit downloads and optional online actions

Downloading, updating or checking regional files requires an Internet connection.
Regional files currently use GitHub Pages/Release distribution infrastructure;
the V2 public host and launch catalog still require approval. The chosen host can
receive IP address, requested region/file, request time and client metadata. An
HTTPS download request is not a first-party upload of a planned route or private
location. Host retention and any location/identifier inference need confirmation
under the provider's practices; no retention duration is promised here.

Optional online address/place search sends the search text explicitly submitted
with Search or Enter to IGN Géoplateforme (`data.geopf.fr`). The search provider
also receives normal connection metadata. Source inspection shows no automatic
attachment of the device position or complete route to that query. A query can
itself contain a personal address or location. First-party address-search code sends no IGN query merely by
typing or opening the dialog; separate WebView communications are described below. Installed Places results remain local; online search
is unavailable without a connection and is not required for planning.

Opening the published privacy policy or attribution links uses the selected
external browser/provider and its network practices. These actions are separate
from ordinary local route calculation.

## Android WebView and platform communications

The app embeds Android WebView. Tests on Android API 36 with Google WebView
155.0.8059.43 observed requests to `content-autofill.googleapis.com` from simple
inputs and actual application forms, before typing or routing. The tested public
Autofill hints did not reliably prevent them. Other minimal local-HTML sessions
also produced network bytes whose source remains unknown. Some adjacent sessions
were silent; this does not settle the behavior for all sessions or providers.

Only permitted metadata was examined. Encrypted request contents, whether personal
information is included, the complete set of platform flows and applicable provider
retention were not established. We cannot claim those requests contain route
coordinates or user information, and cannot claim they contain none. Android's
WebView documentation also describes provider reporting behavior; it does not
establish that the unexplained bytes were reporting traffic. Platform-provider
questions and the final Data Safety declaration require publisher review.

## GPX export and disabled social publication

GPX is generated from the selected route on the device. Android Save lets the user
choose a destination. That document provider/app controls its copy and may upload
or synchronize it. Removing Sugarglider does not delete those exported copies;
manage them with the destination provider. No automatic export upload is performed
by first-party route-planning code.

The fixed local-only Android policy disables social sharing, outings, configurable
sharing servers and live-location publication. Retained future social modules are
not enabled in this release. No Sugarglider social account is needed to plan routes.

## Advertising, analytics and review contact

No advertising SDK, analytics SDK or advertising-ID permission was found in the
audited first-party release/dependency declarations. That statement does not
exclude WebView/platform communications, hosting metadata or optional online
search. Their data practices still need review; this draft does not certify a
blanket no-collection/no-sharing Data Safety answer.

Use the publisher-confirmed final privacy contact for questions. Do not send private
route coordinates or sensitive location details unless necessary and requested
through an appropriate channel. This proposal has not replaced the historical
[published policy](https://victorgabillon.github.io/sugarglider-regions/privacy/).

Review evidence and open decisions: [Data Safety matrix](pr98-data-safety-review.md),
[contract/release gates](pr98-offline-capable-product.md) and
[PR97 measured evidence](https://github.com/victorgabillon/sugarglider/blob/d891d263888efc664409b56d12e70bacd8255dd7/docs/pr97-webview-autofill-privacy.md).
