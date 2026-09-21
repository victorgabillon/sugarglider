# Places: ice-cream discovery

Ice cream is a display-only category. Selecting it does not add a waypoint,
change a route, or make an Auto Tour preference. The existing scenic/water
preferences and nature analysis retain their semantics.

## Source and compatibility

`pois/classification.py` classifies these explicit OSM combinations:

- `amenity=ice_cream`
- `shop=ice_cream`
- `amenity=cafe` with an exact `ice_cream` token in semicolon-separated `cuisine`

Names, `ice_cream=yes`, frozen-food shops, and restaurant/fast-food cuisine tags
alone do not qualify. Existing scenic/hydration primary-category precedence is
preserved. The new primary category is `ice_cream`, group `refreshment`.
Classification retains mapped house number, street/place, postcode and city;
websites, phone numbers and general descriptions remain outside the public subset.

The [OSM ice-cream documentation](https://wiki.openstreetmap.org/wiki/Tag:amenity%3Dice_cream)
describes the amenity, shop and café combinations. Tests use tiny synthetic OSM
XML; runtime discovery never parses PBFs or queries a hosted POI service.

Index format remains 2. New builds declare classifier 2 in both index metadata
and the regional toolchain, changing the content identity. Readers retain support
for classifier 1. A classifier-1 installed region explicitly reports that it does
not include ice-cream places. Updating the application cannot add records to a
previously installed immutable index.

The audited published Yvelines index has 2,153 scenic/hydration records and zero
ice-cream records. A read-only audit of its configured source found 12 qualifying
ice-cream nodes inside the regional bounds. Validation used a separate source
excerpt and the existing basemap. **No production region was rebuilt, modified or
published in this change. A later regional data update is required to make these
places available to existing installations.**

## Shared application path

Python index construction remains `pois/build.py:build_poi_index`, orchestrated
by `offline_regions/build.py`. Server web discovery uses the lifespan-loaded
`PoiIndex` STRtree through `/v1/pois/search`.

Android discovery now uses the installed regional index:
`app.js` → `local_places.js` committed-version lease → `local_region_client.js`
→ `local_region_worker.js:search_pois` → `local_region_data.js:searchPois`.
The worker queries its existing spatial tree; it does not call native routing,
parse map data, or fall back to an HTTP POI service. Queries verify region/build
ownership, respect cancellation and installed coverage, and expose returned/total counts. The shared
UI requests at most 200 results; the local worker rejects limits above 500.
Auto Tour retains its separate 64-place radius query and excludes refreshment
records before truncation, so ice cream cannot crowd its shortlist.

Both paths use the same `place_presentation.js` category presentation and
`map.js` interaction code. The small registry owns display label, compact icon,
rich art, priority and zoom rules. It does not own routing eligibility.

## Presentation

Ordinary ice-cream places use a 24–26 px cone icon from zoom 13, with the existing
44 px clustering radius through zoom 13. The optional name appears from zoom 15
in the same symbol as its icon; collisions may hide the name without hiding the
icon. Required/start markers remain larger and retain their existing behavior.

One selected place uses the 56 px illustrated pin, a separate unclustered source,
and a selection ring. The in-memory map sprite is downsampled with high-quality
browser resampling; the supplied 1024×1536 RGBA source and packaged copy remain
byte-identical. No background removal, recoloring or cropping is performed.

The detail card shows the name, category, mapped address (coordinates when no
address exists), and mapped hours/seasonal/access context when present. Center
on map is a real action. Close and Escape clear both application selection and
map presentation and return focus to the map. Selection pans only as needed to
keep the whole card inside the map with room for attribution. The phone card is
bounded and scrollable; close and center actions are at least 44 px. Touch selection has an
enlarged hit area and chooses the nearest rendered place deterministically.

## Validation and deferred work

`tests/browser/places_harness.html` covers category mapping, safe text rendering,
responsive details, bounded local queries, old/new index versions, real OPFS and
worker transport, cancellation/removal, selection/dismissal and route independence.
Python ingestion/API tests use tiny local XML and no external services.
Android's generated shell allowlist and the PWA cache include the new modules and
canonical artwork.

Audit, size experiments, real-data renderer and full-page screenshots, and logs
are outside Git under
`/home/pompote/oldata/victor/sugarglider-v1-artifacts/places-ice-cream-2026-09-21/`.
The evidence distinguishes source-derived audit fixtures from the unchanged
published region and browser emulation from physical Android device validation.

Deferred: regional data publication, route-via-ice-cream preferences, other category
redesigns, global UI redesign, online POI search, and social/sharing work.
