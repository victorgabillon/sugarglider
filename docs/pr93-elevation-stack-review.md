# PR93: elevation stack integration and endurance review

Base: PR92, `313d0cb934a80291a4103f7ce08b26052c4f6b53`, on
`feature/interactive-elevation-pr92`. Review date: 16 October 2026.
Main reviewed: `6c0b022f48c110467c920fed6570f91daf6c4c75` (124 changed files
through PR92; most added lines are deterministic synthetic test vectors).

This review adds no elevation functionality or parameter changes. It fixes a
confirmed regional-index retention path and strengthens Release CI. Private
terrain, regions, route captures, APKs and device logs remain outside Git.
Physical distinct-region acceptance is still in progress; the final decisions
and measurements below will be completed before delivery.

## Confirmed defects and changes

1. The Places worker could retain a complete previous Nature analysis after a
   region change. `load_places_version` assigned the full analysis object to
   `placesData`. In addition, its name-search function shared a closure context
   with Nature analysis, so merely keeping that function retained Nature too.
   A controlled Chromium experiment with local synthetic data and explicit CDP
   garbage collection demonstrated this: Nature remained reachable while only
   name search was retained, then disappeared after that session was released.
   PR93 gives name search a separate context containing Places data/metadata only,
   and gives the worker a narrow immutable Places session. The same experiment
   now collects Nature while keeping identical working name search. This proves
   a retention fix, not an unbounded leak or a quantified device-memory saving.
2. Android CI previously linted Release without assembling its APK or checking its
   native alignment. CI now builds unsigned Release and checks both Debug and
   Release APK ZIP/ELF 16 KiB alignment. No upload signing credentials are required.

Shell cache generation advances to v93; exact asset pins remain enforced.
The opt-in Android-test endurance phase requires two installed references with
*different graph hashes*, checks native mappings and active-file removal safety,
and records heap/PSS/closure. It does not install or delete regional files and
is absent from Release.

## Integration boundaries reviewed

| Boundary | Evidence and retained behavior |
| --- | --- |
| Native actor and leases | One synchronized engine and one current actor. Replacement closes JNI before creating another actor; the actor retains its repository lease until closure. Request leases cover the whole native callback. Failed opens/initialization and idempotent closure have focused tests. Physical mappings and switching are checked separately below. |
| Immutable V2 install | Exactly five mandatory components, canonical build identity, streamed size/SHA-256 checks, bounded HGT decoding/coverage, full native tile headers, completion reference and atomic browser activation. Failed/cancelled staging cannot replace the old committed pointer. Existing unit/browser corruption and cancellation tests are retained. |
| Bridge | Exact configured appassets origin, current WebView, main frame, nonce/request ledger and operation ownership. No JavaScript interface, wildcard origin, new permission or authenticated redirect transport. Page invalidation cancels optional work and drops stale replies. |
| Elevation | Native nullable heights, distance-bound samples and unchanged PR89/PR91 algorithm/parameters. Missing data stays null; segments split at missing/unsupported spans; partial full-route totals stay unavailable. Synthetic complete/partial/void/reversal/numeric invariants remain distinct from DEM accuracy validation. |
| Presentation | Current candidate/generation/profile/geometry/region/component binding; bounded existing cache. One SVG/control and one style-independent marker, no hover rerouting/panning. Worker, observer, listeners, pending frame and marker cleanup are exercised. |
| GPX and planning | PR93 changes no route generation, ranking, canonical geometry, elevation analysis or GPX implementation. Export remains the returned canonical candidate, one track/segment, no elevation/extensions. |
| Packaging | Normal Debug and unsigned Release compile the same native runtime and shared web shell without requiring the research build flag. Research classes remain in Debug/androidTest source sets. APK inspection independently verifies assets, permissions, IDs, lack of private data and alignment. |

## Regression verification

- `uv run --offline make check`: Ruff, strict mypy, **1,380 passed / 16 deselected**;
  final run 196.72 s. Deselected service integration tests require external services.
- **46 browser harnesses / 908 scenarios passed**, including the new Places-session
  contract, existing bridge/security/GPX/planning/offline tests and real module-worker
  MapLibre security tests. The runner waits for terminal passed/failed status.
- `tests/browser/pr93_retention_acceptance.cjs`: controlled-GC regression passed;
  Nature released and name-search output unchanged.
- `tests/browser/pr92_elevation_acceptance.cjs`: actual mouse/keyboard/touch,
  scrolling and real MapLibre style/resize/remove passed at 360/390/420/1280 px.
- Android **238 Debug + 233 Release** tests, both lint variants, normal Debug and
  unsigned Release assembly, research main/test assembly and research lint passed.
  The final test-only native endurance instrumentation also compiled successfully.

The standalone retention runner uses an existing Playwright/Chromium installation:

```sh
PLAYWRIGHT_MODULE=/path/to/playwright \
CHROMIUM_EXECUTABLE=/path/to/chromium \
node tests/browser/pr93_retention_acceptance.cjs
```

## Distribution evidence and launch gates

The bundled catalog currently names Yvelines build
`902f951bedd1de527629baa572358aec4c388359ce5435d472639dac61f9bc71`.
A read-only request on 16 October confirmed that its actual regional manifest is
schema **1** with only map/routing/places/nature. Catalog schema 1 is the catalog
format, not proof of regional V2 compatibility. The new app deliberately rejects
V1 and preserves old files; releasing it against this catalog would leave new
installations without a compatible regional download. The catalog was not changed.

A coordinated V2 launch must:

1. Resolve rights/attribution and vertical-reference evidence for every terrain
   source and derivative, including DEM-enriched routing archives. Record an
   explicit approved publication policy rather than bypassing current false flags.
2. Build/independently verify every offered V2 region with the pinned 3.9.1 engine,
   all five mandatory components, exact bounds and immutable content identities.
3. Validate a private staging HTTPS distribution end to end, including sizes,
   byte hashes, nonredirecting/range-compatible transport and storage/restart/failure.
4. Coordinate the app's bundled catalog and hosted immutable artifacts. Keep V1
   artifacts/catalog available to the existing app until a separately approved
   migration/retirement policy exists. Never silently reinterpret V1 as V2.
5. Verify the final Release artifact, version/update policy, attribution/privacy
   presentation, supported-device memory behavior and ordinary install/export
   behavior. The present version remains 8 / 1.2.0; it is a review build, not an
   incremented or signed Play release.
6. Publish only after explicit authorization. No PR merge, signing change, public
   artifact, catalog update, social enablement or Play deployment occurred here.

### Four DEM tiles: evidence versus unresolved questions

The exact private source pins and hashes are in [PR90](pr90-v2-offline-regions.md).
PR93 rechecked object headers for N48E001/N48E002/N49E001/N49E002. Their lengths
and April 2016 Last-Modified dates still match the acquisitions; the HEAD responses
provide no per-tile imagery-source metadata. Hashes prove the acquired bytes,
not which upstream pixels, licenses or datum conversions produced them.

The [AWS registry](https://registry.opendata.aws/terrain-tiles/) identifies the
bucket and links to provider attribution, rather than granting a single blanket
license. Provider [source documentation](https://github.com/tilezen/joerd/blob/master/docs/data-sources.md)
describes mosaics of several datasets and a footprints database. PR93 privately
retrieved that public metadata (8,706,136 compressed bytes, SHA-256
`1882c61652283929aad1564734d1eb01575116f5936e9836ccd140c6d852d8b1`).
Geographic overlap finds SRTM, EU-DEM, GMTED and ETOPO1 candidate source footprints
around these tiles. Overlap, especially boundary-touching footprints, is not
proof of actual contribution, priority or the historical 2016 build recipe.

Provider [Skadi format documentation](https://github.com/tilezen/joerd/blob/master/docs/formats.md#skadi)
states WGS84 horizontal coordinates and metre heights referenced to WGS84/EGM96.
That is documented provider intent; it is stronger evidence than assuming a datum
from the HGT extension, but does not independently establish the processing of
these exact historical objects. The application/manifest's unresolved datum label
is intentionally retained pending that verification.

Provider [attribution guidance](https://github.com/tilezen/joerd/blob/master/docs/attribution.md)
requires source-specific investigation and identifies credits for EU-DEM,
SRTM/GMTED and ETOPO1. Before redistribution, establish the historical contributing
sources and their applicable terms, transformations/datum handling, derivative
routing-graph obligations and final in-app/download notices. Public access to
S3 and a software license for Joerd are not terrain redistribution approval.
No rights approval is inferred by this review.
