# Place and address search

Search is a coordinate acquisition tool. A chosen result becomes an ordinary
`name`, `lat`, `lon` point through `route_point_acquisition.js`. The existing
`automatic_intent.js` grammar decides Start, loop stops and open End extension.
Move uses the same replacement operation as map placement, preserving point ID,
constraints, approach overrides, itinerary reason and selection. One selected
result makes one history edit, clears stale candidates and leaves Generate explicit.
Search/cancel/typing alone do not change canonical intent. Chip drag still reorders;
a normal map POI tap still inspects only.

The compact + menu and contextual Move menu offer Search place or address and
Choose on map. One native modal supplies a labeled input, explicit Search/Enter,
semantic result buttons with names, context and coordinates, arrow/Tab navigation,
announced status/errors, scrolling and Close. GPS remains the existing recenter/
follow tool; no new permission or current-location acquisition action is introduced.

`location_search.js` owns the provider-neutral `searchResolvedLocations` boundary.
It queries the selected committed region's installed Places first through the
existing region lease and worker. Accent/case-insensitive name/category matching
uses validated, loaded OSM-derived features and their stored coordinates. Private,
restricted and explicitly non-potable records are excluded. This is a mapped-place
index, not a street-address database. Up to six local results are shown, with at
most eight rows across both groups. A Places-only verified loader lets acquisition
work independently of an unrelated invalid nature index; planning/index installation
still use their existing complete validation. Multiple regions need a selected
region; storage or index absence is reported without disabling map editing.

Online search uses IGN Géoplateforme's no-key France geocoder for BAN addresses and
BD TOPO named places. The typed `UiConfig.geocoding` boundary owns availability,
provider, HTTPS endpoint, coverage and attribution; the same model generates
`android_ui_config.json`. It is public configuration, with no keys. The packaged
WebView uses its existing ordinary HTTPS/CORS path; navigation, bridge trust and
permissions are unchanged. See the current [service documentation][service],
[rate limits][limits] and [terms][terms] when changing providers or operating the app.

Only pressing Search or Enter sends the trimmed text online. Nothing sends GPS,
route coordinates, itinerary reasons, profile, participant capabilities or the
whole plan. Credentials/referrer are omitted; redirects are rejected. Queries are
3–200 characters, reject controls and are URL-encoded as text. There is no
search-as-you-type request, background search, automatic retry or persistent
geocoder cache. One page serializes remote calls with at least one second between
starts, a ten-second timeout, six-result provider limit and 256 KiB response bound.
HTTP 429 delays the next explicit search by at least five seconds, respecting an
exposed Retry-After up to sixty seconds. Limits shared by an IP remain enforced by
the provider. Closing, reopening or submitting again aborts obsolete work; only the
current dialog operation may render. Optional local work has a five-second bound.

On this device and Online results stay separate. Results are normalized to name,
secondaryLabel, numeric lat/lon and source, rendered with textContent. Only
name/lat/lon cross into editing. No query, provider ID, result blob or acquisition
source is retained in route state or canonical JSON. Coordinates are authoritative
once selected and are never re-resolved for routing or GPX. The external itinerary
v1 parser, dialog and schema remain unchanged.

Offline, installed Places remain usable in a loaded/cached browser shell or bundled
Android shell. Online address search reports unavailability; map placement remains
available. Timeouts, provider errors, 429, malformed responses, empty results and
cancellation have concise messages. Search credits IGN Géoplateforme, BAN / BD TOPO,
Open Licence 2.0, a source link and the retrieval date; existing map attribution
remains visible. There is no promise of current access, arrival or address accuracy.

For fixture-based validation run the browser `location_search_harness.html` with the
other suites. `location_search_acceptance.cjs` requires a real immutable Yvelines
pack served at /pack, a baseline server and an isolated evidence directory; it tests
actual offline Places, one explicit public-address IGN query and route/GPX equality.
Its provisioned OPFS snapshot is disposable, not a native installation or claim that
an invalid original nature index passes the normal region installer. Screenshots
and GPX evidence belong outside Git. Physical Android WebView/keyboard checks remain
separate from browser viewport and source-byte Android-origin simulation.

[service]: https://cartes.gouv.fr/aide/fr/guides-utilisateur/utiliser-les-services-de-la-geoplateforme/geocodage/
[limits]: https://cartes.gouv.fr/aide/fr/guides-utilisateur/utiliser-les-services-de-la-geoplateforme/limites-d-usage/
[terms]: https://cartes.gouv.fr/cgu/?lang=fr
