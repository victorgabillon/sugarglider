# Regions and Places

A region is an explicit, versioned set of four components derived from a configured
local OSM PBF: map, routing, Places and Nature. The static distribution host serves
files; it does not calculate routes, discover nearby places or store participant data.
The bundled catalog is `web/static/offline_region_catalog.json`; its entries point to
immutable build manifests with exact bounds, sizes and SHA-256 values.

## Build-time and runtime responsibilities

| Stage | Owner | Input/output |
| --- | --- | --- |
| Source coverage and build | `offline_regions/build.py`, region specs in `offline-regions/` | Explicit PBF, verified source identity and bounds, sequential component builders, validated staged output. |
| Map component | `scripts/build_pr36_map_pack.sh`, map manifests | Licensed regional vector data in PMTiles, with attribution. |
| Routing component | Regional Valhalla builder scripts, routing manifests | Validated engine/version-compatible tile archive; separate from maps. |
| Places / Nature components | `pois/build.py`, `nature/build.py` | Local deterministic indexes; no runtime PBF parsing or hosted discovery. |
| Distribution preparation | `offline_regions/distribution.py`, `deploy/regions/github-pages/` | Reviewed static directory/ZIP and separate publishing workflow template. |
| Reference runtime | Startup `PoiIndex` / `NatureIndex` | Immutable loaded models and reusable spatial trees; missing/invalid indexes remain unavailable without disabling routing. |
| Android runtime | Shared regional stores/workers and native routing repository | Exact installed build, OPFS map/index bytes, app-private native routing bytes. |

A build checks source coverage before work, verifies the source again after component
creation, validates the complete staged directory and only then moves it into its final
output. Existing output is never silently overwritten. Hash/build identity changes
when source/toolchain/component identity changes. Generated data under `data/` is ignored
and must not be committed.

## Install, update and remove

```text
Catalog entry → validate exact manifest/identity
              → stage Map + Routing + Places + Nature
              → verify each component
              → commit one regional build
              → expose Ready to planner and map
```

`region_product.js` coordinates the operation and cancellation.
`region_versions.js` owns the OPFS staged/committed version record and locks.
`region_components.js` adapts independent component formats. Native
`RegionalRoutingRepository.kt` owns the routing archive and its read/mutation leases;
`regional_native.js` is the page-side adapter. Download progress describes bytes and
phases, not an estimated readiness percentage.

A new region is unavailable until all components verify. Replacement stages a new build
while retaining the previous committed one. Cancellation, checksum/identity errors,
missing data and optional-storage failures remain explicit; cleanup of unused versions
is a separate identity-scoped operation. Do not report Ready merely because a transfer
finished or native routing alone is available.

`regional_planning.js` selects one committed region and holds its lease through the
whole planning callback, including native drain and publication. All required points
must fit that region and activity. There is no region stitching, hidden native/network
retry or fallback map. Maps live only in OPFS, and PMTiles uses bounded random reads
through the shared implementation; routing storage is not a second map cache.

Installation requires network and storage; a completed compatible region is read
locally. This says nothing about optional social API availability. Attribution remains
visible. Third-party raster tiles may be shown by the reference UI but are never
bulk-downloaded, prefetched or persisted.

## Places and explicit route intent

`pois/classification.py` classifies local OSM features. `pois/approaches.py` derives up to
eight deterministic meaningful approaches per feature; private/restricted/locked
approaches are excluded. The reference `PoiIndex` owns startup-loaded STRtrees over
features and approaches. Android loads verified indexes through
`local_region_client.js` / `local_region_worker.js`, reusing the local shared reader.

`local_places.js` performs bounded viewport searches; `place_presentation.js` owns
category/text/detail presentation; `map.js` owns clustered marker/label rendering.
Names and OSM provenance remain visible. Plain text rendering must not interpret mapped
names or descriptions as HTML.

A Place tap opens details only. Changing filters, selecting/dismissing a popup or
centering the map does not change required points, candidates, score, geometry or GPX.
An explicit route preference/edit is separate and invalidates the plan when appropriate.
**Pass through here** explicitly adds a hard route point using the same acquisition
as a resolved search result: only the display name and coordinate enter the route.
It is available in the editable planner for public/unknown-access places with valid
coordinates; private/restricted and explicitly non-potable places have no such action.
**Prefer for suggested route** remains a separate soft Auto Tour preference. Mapped
access, opening and potability information are not guarantees.
Only selected deliberate places become route anchors; incidental map discoveries do not.

Water classes remain distinct: verified drinking water, unknown potability and explicitly
non-potable features. Private and non-potable features are indexed but hidden by default
and excluded from normal Auto Tour selection. Only verified drinking water uses the blue
mascot pin. Mapping never proves current operation, quality or availability.

Ice cream is indexed from mapped feature/tag evidence, not a runtime shop search.
The classifier-2 regional data contains ice-cream records; older classifier-1 data
remains readable and the UI reports that this category is unavailable there. A category
filter never upgrades or replaces an installed region automatically. Opening hours,
stock and popularity are not inferred.

## Semantic location versus arrival

A place's display/semantic coordinate may be a center far from an accessible entrance.
Planning uses validated meaningful approaches and checks final routed arrival, not
center proximity. A reached stop carries validated routed coordinates; an approximation
reports both coordinates and measured remaining distance; an unselected or unreachable
considered stop has one explicit dropped reason. Approach overrides retain the same
place identity and obey server-controlled semantic/snap bounds in the reference planner.

## Nature analysis

`NatureRouteAnalyzer` reuses normalized routed geometry edges. Woodland, open-natural,
agriculture, water-crossing, urban and unknown classes partition the engine's total
distance. Park/protected and near-water are independent overlays and may overlap those
classes. Missing/uncovered/invalid data remains unknown rather than being guessed urban
or natural. Analysis never adds or changes route geometry.

The local shared reader has bounded analysis work and reports unavailable analysis
explicitly on failure. Reference and local detail coverage differ; use result diagnostics
instead of assuming a loaded index guarantees complete coverage. Nature preference
ranks below distance/structural safety gates. GPX contains no Nature extensions.

## Operational references

Region build/verify commands are in [development](development.md).
[Static distribution preparation](pr42-static-distribution.md) and the
[Pages template](../deploy/regions/github-pages/README.md) describe explicit publication
and immutable retention. Dated publication/acceptance records prove only their named
builds. Consult the current catalog rather than copying an old build ID from a handoff.
