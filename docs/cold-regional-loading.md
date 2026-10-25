# V2 regional startup

The map runtime and planning readiness share one opened map component per selected
immutable build. Opening fully verifies the regional map manifest and every archive
byte before PMTiles validation. The opened source reads only that verified `File`
snapshot. Reuse checks the committed directory identity, region/build identity,
current file metadata and readability of the original snapshots. Replacement or
invalidation fails explicitly; reuse never switches range reads to unverified bytes.
A new application runtime performs full verification again. Nothing persists a
“verified” flag, and selecting another build replaces the single opened component.
Installation and explicit download verification still run their full checks.

Previously, offline-map initialization, planning readiness and the following map
refresh each opened and hashed the same archive. A private Fairphone trace found
three full SHA-256 passes over an 81.6 MB archive, reading about 245 MB at startup.
The basemap now attaches before the longer planning lease, so tiles and icons can render while
native capabilities and the regional worker are prepared. Those independent checks
run concurrently under one version lease. Both outcomes are drained before the
lease is released, including on failure. Planning availability
still comes only from the completed native, map, Places and Nature checks. Map
initialization failure starts those checks too, preserving usable route controls
when WebGL is unavailable.

Nature remains eager. The index validates the source document and polygon topology,
projects every coordinate, and builds the same spatial tree and 64-segment boundary
blocks. It keeps only the two classification values needed from each source feature.
The original document, tags and geographic coordinates can therefore be released
while the projected analyzer remains active. Switching, clearing or removing the
selection also closes its analysis worker, including when no replacement is loaded.
Recursively freezing the discarded
source graph is unnecessary. No geometry predicate, traversal order, operation
budget, score or ranking changes.

A private fresh-process comparison also deferred the same Nature loading and
construction until first analysis. That moved construction into the first-analysis
latency without reducing time to complete readiness. Eager construction keeps that
cost out of the first plan; map-first startup supplies the early map independently.
Those pipeline trials used desktop Node and retained routed geometries, not a claim
about complete native Android generation time.

Regression coverage stays in the existing acceptance suites:

- `region_preference_acceptance.cjs` runs actual bundled startup with synthetic
  OPFS data, a held native reply, remembered selection and explicit clearing. It
  also runs the regional product harness: warm reuse, fresh-runtime verification,
  corrupt PMTiles, update/cancellation, and removal.
- `nature_performance_acceptance.cjs` retains numerical golden comparisons, strict
  budget failure, worker restart/cancellation and stale-session checks. Retention
  assertions verify both retirement of an analyzer and release of source geometry
  while an analyzer remains active. Explicit GC is confined to these tests.
- The other six browser acceptance suites and the Python/Android checks remain
  required. Real regional inputs, private profiles, GPX and APKs stay outside Git.
