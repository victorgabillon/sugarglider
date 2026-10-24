# Installed terrain attribution

Installed regional cards expose **Data sources and licences** independently of
routes and elevation analysis. All essential notices and the seventeen IGN source
archive editions ship in the shared web/Android application shell. Licence and
source links open only on deliberate activation. Map credits remain separate and
continue to come from the map pack's attribution; IGN licensing does not cover
the basemap's other sources.

## Provenance boundary

`region_versions.js` parses and validates the installed V2 regional manifest.
Installation verifies component bytes before activation. That regional manifest
contains descriptors, not the full derivation in `elevation/manifest.json`.
The card deliberately does not reopen component files, acquire additional storage
leases, fetch metadata, or run elevation analysis.

`terrain_attribution.js` therefore contains a narrow, code-reviewed registry of
known payload identities. IGN recognition requires all four HGT descriptors in
their canonical order, matching **path, byte size, SHA-256 and format**, plus a
well-formed elevation-manifest descriptor. Region names, IDs, publication flags,
source URLs, claimed product names and arbitrary derivation strings never select
or supply notices. The claim that terrain is incorporated in Valhalla additionally
requires the exact known routing-archive descriptor; a different graph gets an
explicitly unknown routing-terrain provenance message.

The historical Copernicus four-hash recognition, source description, full credit,
licence link and disclaimer are preserved. Unsupported or malformed identities
receive a neutral notice without an inferred source or licence. All notices and
external link destinations are code-owned; DOM construction uses text nodes.

The IGN registry's ledger SHA-256 and all seventeen edition filenames are checked
against `offline-regions/sources/ign-rge-alti-5m-four-tiles.json`. Source archive
edition dates are not terrain acquisition dates for individual cells. The panel
explains the ground model, NGF-IGN69 / EPSG:5720, conversion to one-arcsecond HGT,
integer-metre quantization and loss of the original 5 m grid resolution.

## Scope and maintenance

Recognition concerns the known elevation payload, independent of the regional
build ID and the elevation metadata's publication flags or publication-basis
digest. This handles both private metadata and the proposed public descriptor
without importing or changing the publication-authorization mechanism.

This registry is deliberately not a generic provenance parser or a new integrity
verifier. It relies on the existing installation checks; reopening a disclosure
does not rehash stored data or certify its current integrity. Attribution is not
publisher approval, legal clearance, endorsement, or a promise that every other
component of a region has been cleared. New payloads need an explicit registry
review with source evidence and updated tests; they remain unknown until then.
No end-to-end terrain rebuild reproducibility is asserted here.

The chart shares the IGN display name and licence destination but derives its
source from the **selected candidate's owned, verified elevation analysis**. It
does not inherit the currently selected region card's source. Reset, cancellation,
unavailable analysis and missing coverage remove stale chart source text; the
installed-region disclosure remains available. Existing analysis, sampling,
region-management and map-credit behavior is unchanged.

## Regression checks

`tests/browser/ign_attribution_harness.js` uses a presentation-only fixture with
real V2 descriptor structure and the exact reviewed IGN HGT/routing identities.
Other component/source fields are synthetic. The private and proposed-public
elevation metadata descriptors differ; test build IDs are recalculated and pass
the production regional parser. No private regional manifest, payload, unsigned
publication request or legal bundle is included.

The harness exercises OPFS metadata restart, refresh, switching, malformed and
hostile inputs, independent graph attribution, unchanged Copernicus notices and
zero source-disclosure I/O or mutation. Installation acknowledgements are
synthetic; existing regional suites cover component verification and activation.
The dedicated Chromium acceptance runner also checks actual Enter/Space keyboard
activation, focus, all seventeen wrapped filenames and scrolling with the browser
offline at 320, 360, 390, 420 and 1280 px. Screenshots may be saved outside Git via
`ATTRIBUTION_EVIDENCE_DIR`. This is browser acceptance, not physical Android
acceptance or permission to publish regional data.
