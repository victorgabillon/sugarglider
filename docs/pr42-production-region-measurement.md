# PR42 production-region measurement — in progress

This branch measures the preferred Île-de-France offering before choosing a
consumer download or a smaller meaningful partition. It does not yet implement
the normal download UI or establish a device acceptance pass.

## Reproducible input and limits

- Main baseline: `5be5780` (PR43 social service merged).
- Source: existing local `ile-de-france-latest.osm.pbf`, 335,288,680 bytes,
  SHA-256 `2ac2b0d9c7ca8374af078a6f564c342a08a2634a110c1f18bae1cbd1cda5d849`.
- Requested bounds match the source header:
  `[1.445097, 48.11918, 3.560409, 49.24271]`.
- Existing PR39 manifest/component formats, Protomaps 4.14.1 and Valhalla 3.6.3;
  pedestrian and bicycle graph access modes support the six existing public
  profile preferences. Bounds are a selection envelope, not proof that every
  coordinate inside has a traversable road/path.
- Build containers default to 3,072 MiB, two CPUs and no swap. The map JVM heap is
  three quarters of the memory limit. Explicit overrides accept 512–32,768 MiB
  and 1–16 CPUs, with malformed values rejected before tools run.
- The measurement driver also places host Python and children in a user-systemd
  scope with `MemoryMax=3G`, `MemorySwapMax=0`, `CPUQuota=200%`. Container limits
  remain separate. These are reproducible test-machine constraints, not measured
  minimum system requirements.

The standard entry point remains:

```sh
SUGARGLIDER_BUILD_MEMORY_MB=3072 SUGARGLIDER_BUILD_CPUS=2 \
  make offline-region REGION=ile-de-france PBF_INPUT=/absolute/local/source.osm.pbf
```

The current `/tmp/sugarglider-pr42-measure-region.py` invokes the same sequential
PR39 map/routing/POI/nature builders and final verifier, adding phase timing.
Report: `/tmp/sugarglider-pr42-idf-build-report.json`; detailed build log:
`/tmp/sugarglider-pr42-idf-build.log`. Generated files remain ignored under
`data/offline-regions` in the separate PR42 checkout.

## Measurements so far

Build started 2026-09-11 11:17:47 UTC. Tool/source caches were already available.

| Component | Bytes | Elapsed build time | State |
| --- | ---: | ---: | --- |
| Map archive, zooms 0–15 | 243,080,284 (231.82 MiB) | 1,252.505 s (20 min 53 s) | Component built; full regional verification still pending |
| Routing archive | 318,443,520 (303.69 MiB) | 952.890 s (15 min 53 s), including extract | Component built; full regional verification still pending |
| Places | Pending | Running | Not yet built |
| Nature | Pending | Pending | Not yet built |

The completed map and routing files have been retained as measurement-only hard
links in ignored directories so a later component failure does not erase this
evidence. They are not an active installed region. No existing valid pack was
replaced. The routing archive SHA-256 is
`11a1abd9f4f45bb420a59cbc9a93ae0519c815874500f0f4da2d26d367e959b8`.
The two large components total 561,523,804 bytes before places/nature and metadata.

Total download/installed/free storage, expanded index size and topology counts,
phone installation time and route/Auto Tour latency remain unmeasured. Compare
the actual output to PR40's existing reader limits before selecting a product
region. Do not raise limits without memory/latency evidence or present the Marly
development pack as the production offering.

## Static-host candidate

GitHub's current release documentation allows assets smaller than 2 GiB each and
states no total-release-size or bandwidth limit. This makes Releases a possible
initial host if every component fits, subject to real download/CORS/redirect and
interruption checks. It is not a bandwidth SLA or proof of consumer suitability.
[GitHub release limits](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases)

The existing manifest uses relative component paths such as
`map/basemap.pmtiles`. Release assets are individual downloads, so do not assume a
GitHub release URL implements that directory layout. A Releases-based installer
would need an explicit catalog mapping from each validated logical component
path to its immutable asset URL, with bounded HTTPS redirects and unchanged
identity/size/checksum checks. A static object-store layout can preserve the
relative paths directly. This transport decision and actual browser/native
download validation remain open; do not publish a catalog before they are tested.

Use immutable versioned assets, publish the verified regional manifest last and
keep the existing independent component paths/identities. A catalog must point
only at fully published, verified builds. No routing or bulk-file API server is
needed. No release asset or consumer catalog has been published yet.

Distribution must retain visible OSM/ODbL attribution and the applicable license
notice/access to derivative data. Map attribution also includes ESA WorldCover,
Natural Earth and Protomaps. Audit the exact generated databases and ancillary
source licenses before publication; do not assume the application code license
licenses the map data. [OSMF attribution guidance](https://osmfoundation.org/wiki/Licence/Attribution_Guidelines)

## Automated evidence

`make check`: **1,033 passed, 16 existing integration tests deselected**, Ruff and
strict mypy pass. The new 22 resource/specification tests use no Docker, network
or real map data. The actual long-running build is separately identified here;
it is not counted as a unit test or physical acceptance.

Outstanding: completed measurements and integrity verification, regional catalog
and normal failure-safe four-component install/update/remove flow, staged
activation/recovery, and every required Fairphone fresh-install/offline/restart/
cancellation/removal case. No PR42 readiness or merge approval is implied.
