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

## Full Île-de-France measurements

Build started 2026-09-11 11:17:47 UTC. Tool/source caches were already available.

| Component | Bytes | Elapsed build time | State |
| --- | ---: | ---: | --- |
| Map archive, zooms 0–15 | 243,080,284 (231.82 MiB) | 1,252.505 s (20 min 53 s) | Structurally verified |
| Routing archive | 318,443,520 (303.69 MiB) | 952.890 s (15 min 53 s), including extract | Structurally verified |
| Places | 366,485 | 1,603.828 s (26 min 44 s) | 7,171 features; structurally verified |
| Nature | 30,694,816 | 502.714 s (8 min 23 s) | 190,606 features; structurally verified |

The complete seven-file distribution is **592,588,177 bytes** (about 565 MiB),
including manifests. Places expand to 5,749,527 bytes. Nature expands to
132,550,175 bytes, with 4,170,750 positions in 205,098 rings. The four component
stages total 4,311.937 seconds (71 min 52 s); this excludes final verification.

The initial in-process build was killed by its 3 GiB limit during final
verification, after all four outputs and the combined manifest were written.
Nothing was activated. The same unchanged verifier in a fresh 3 GiB/no-swap
process **passed in 24.94 s**, with 2,983,060 KiB maximum RSS. Its content build ID
is `73a05f4feddb820adb66e039d6daa04b2351befe24e1a9d0d373e4087d3752e5`.
Outputs remain inactive measurement files; completed components are retained as
hard links in ignored directories. No old valid pack was replaced.

The cause was retained Python/native allocations across phases, not invalid
component bytes. Regional orchestration now starts each index builder in its own
sequential process, passes the exact source/output/bounds, and inherits the
caller's resource limits. Child failure stops subsequent phases and publication.
The existing standalone builders accept optional explicit bounds; unchanged tiny
fixture output is byte-identical across in-process and isolated builds.

**Full Île-de-France is not a supported V1 offering with the current reader.**
Its 4,170,750 positions exceed PR40's 2,000,000-position limit. The actual shared
reader rejects it with `regional_index_too_large` (host component probe, 5.67 s
parse plus 0.66 s admission, 847,772 KiB peak RSS). The 128 MiB expanded-byte cap
is only narrowly met. Keep the full-region specification as a measurement input,
not a published consumer catalog entry. Do not raise those size/position caps.

## Measured partition candidate

`yvelines-ouest-parisien` proposes **Yvelines et ouest parisien**, with envelope
`[1.445097, 48.38, 2.25, 49.1]`. This is an explicit regional rectangle around
Versailles, Saint-Germain-en-Laye, Rambouillet and Mantes-la-Jolie, not a claim of
an exact administrative boundary or connectivity at every point. These are the
four arrondissement centres identified by the
[departmental prefecture](https://www.yvelines.gouv.fr/index.php/Services-de-l-Etat/Le-departement-des-Yvelines).
It covers a useful western outdoor-planning area while retaining the existing
one-region/no-stitching contract. Coverage preview and edge failures remain explicit.

The original complete PBF was rebuilt with these bounds; no routing-only extract
was reused for nature. Its nature component is **10,634,994 bytes compressed**,
**45,278,253 bytes expanded**, with **62,191 features / 1,450,033 positions**.
Build time: 450.828 s (7 min 31 s), maximum RSS 1,276,420 KiB. SHA-256:
`abb0819a4f4b02d8ee844aa19de71c1760e0b63a1a9f7bd3410513d82dca7b90`.
The original reader passed size admission but exhausted its 20-million-operation
installation topology budget after 5.78 s (429,428 KiB peak RSS).

A temporary bounded benchmark established that complete validation needs
34,451,278 operations: 2.31 s parsing plus 8.97 s indexing/validation, with
429,868 KiB peak RSS. This supports the separately recorded PR40 adjustment to a
strict **40-million-operation installation budget**. The 2-million-position,
128 MiB expanded/32 MiB compressed and four-million-per-route analysis limits
remain unchanged. The benchmark is component-only host evidence, not a complete
installed region or Fairphone acceptance. Final current-reader validation,
combined map/routing/places measurements, phone installation/latency and storage
measurements remain required before this becomes a consumer offering.

Probe/build reports live under `/tmp/sugarglider-pr42-*`; generated data stays
ignored. The partition's matching spec/map template are source-controlled inputs.
No regional catalog or public artifact has been published.

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

`make check`: **1,036 passed, 16 existing integration tests deselected**, Ruff and
strict mypy pass. The resource/specification and isolated-builder tests use no Docker, network
or real map data. The actual long-running build is separately identified here;
it is not counted as a unit test or physical acceptance.

Outstanding: complete partition measurements and integrity verification, regional catalog
and normal failure-safe four-component install/update/remove flow, staged
activation/recovery, and every required Fairphone fresh-install/offline/restart/
cancellation/removal case. No PR42 readiness or merge approval is implied.
