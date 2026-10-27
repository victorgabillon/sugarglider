# Final mobile and independent-map consolidation

The integration starts from main `5fb8732eabe988c8c2cfc5d8608f6dd6bf0ef41d`.
GPS-only commit `cbcb263d4ea6e2fe108b362ec5bf130f4f068baf` is cherry-picked;
the old feature branch is not merged. Its cream 48 × 48 control and blue active
outline retain the existing five states, images, positioning and GPS controller.

The Android planner composes two existing OPFS authorities:

- Complete products retain their committed version directories. Their maps may
  be viewed independently of the selected routing region. Verification checks
  the selected version first; planning still verifies that exact selection under
  its existing version lease. No native graph or route identity changes.
- Independent maps use the existing `MapPackStore` directory, PMTiles reader,
  streaming download and bounded incremental SHA-256 verification. No database
  or duplicate copy of a complete product's map is introduced.

The shared smallest-area, then pack-ID rule chooses one covering map; maps are
never stitched. Complete maps have a region-management action, not independent
removal. Invalid and incomplete independent packs remain explicit and cannot
displace verified complete maps. Removal and download cancellation drain through
the existing store. Cancel remains enabled while the manifest is downloading.

Tools → Map display → Offline maps provides a trusted package selector in the
bundled planner. The matching private staging catalog enables the reviewed
Île-de-France offer; production catalogs are unchanged. The installer accepts
only its exact URL and bundled integrity descriptors:

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| Manifest | 621 | `cce4e686a2d8cddfb0d938c822a66d655a5a868f357f70bb9c1480c06faf098e` |
| PMTiles | 243,080,284 | `eeea1321da3641ebb867473114bcd3706cb0d9f0b6ab2692baaf51058230b7a9` |

Both identities are checked before activation. A cold runtime rechecks stored
bytes, and warm reads remain pinned to verified immutable File snapshots.
Outside the selected routing region, the map explains the complete-region
requirement and offers the existing region manager. No online routing, region
switch, weakened route retry or connection between graphs is added.

Browser coverage includes trusted-source rejection, manifest and same-size
archive checksum failures, interrupted and missing downloads, pending-manifest
cancellation, incomplete-install recovery, cold/warm corruption, overlapping
coverage, removal, optional-storage failure and the unchanged routing-version
gate. The normal bundled application tests retain French/English mobile headers,
five GPS visual states, canonical route/selection/editor/camera and exact GPX
comparisons. Browser native replies are synthetic; they do not establish
physical routing or live AI acceptance.

The existing installed `d85130b` SG AI Test APK is a separate artifact. This
integration does not authorize updating it. Its Marly, Yvelines and Puy-l'Évêque
files, saved adventures, original 23.172 km route, GPX, account and preferences
must be preserved. The Lot 34.364 km / 710 m / 2.614-second physical evidence is
retained in the prior private installation receipt and is not rerun here.

Before any physical update, identify the final APK by full source revision,
SHA-256, signer, bundled-asset hashes, private catalog and CA. Obtain approval
for that exact artifact, back up and verify the complete protected state, then
perform only an in-place staging update. The new APK, independent map install,
physical acceptance and any live ChatGPT inference remain separately recorded
states. No production, Play or public regional catalog change is included.
