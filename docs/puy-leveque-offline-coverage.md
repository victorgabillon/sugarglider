# Puy-l'Évêque offline coverage — 27 October 2026

Prepared privately for the 31 October–1 November weekend. **Ready for an authorized staging installation; physical Fairphone acceptance is pending.** No device transfer, APK installation, region replacement, route edit, production/catalog deployment or Play change was performed.

Source worktree starts at main `422e43715ba2530e452171efb94cc42db989fbd5`, verified against origin on 27 October. The earlier `18b7dd7` is an ancestor. Changes add a region/template, pinned source records and a bounded Copernicus source-grid conversion; no GUI, runtime reader limits, routing engine or regional schemas change.
## Coverage and sources

Bounds `[0.90, 44.30, 1.60, 44.75]` (west, south, east, north), approximately 55 × 50 km. Puy-l'Évêque, Prayssac, Duravel, Pescadoires, Luzech, the Lot valley and surrounding countryside are inside. Coverage is a selection envelope; mapped paths are not current-access guarantees.

The Lot-only extract and Midi-Pyrénées alone do not cover the proposed rectangle. The union of retained Geofabrik Aquitaine and Midi-Pyrénées `.poly` footprints covers the full final rectangle, with no uncovered area. The PBF header is not treated as footprint evidence. Both dated inputs have OSM timestamp **2026-10-25T21:21:21Z**, downloaded **2026-10-27**, and provider MD5 plus local SHA-256 checks.
- [aquitaine-261025.osm.pbf](https://download.geofabrik.de/europe/france/aquitaine-261025.osm.pbf): 296,567,832 bytes; SHA-256 `ddd4ee61d75074f74eb75075d2bc48d5fc2150fd2f29d3f99dfb9ace277ccba2`.
- [midi-pyrenees-261025.osm.pbf](https://download.geofabrik.de/europe/france/midi-pyrenees-261025.osm.pbf): 363,511,147 bytes; SHA-256 `45d72c5081c688c33a644a0f11f2190f5e748a3c7cc59b7ae9977bc76f580bad`.

Osmium 1.16.0 merges the same-snapshot inputs, then makes a `smart` extract with `types=any`, `complete-partial-relations=1` and explicit final bounds. No coordinates/tags are invented. Prepared input: **17,586,885 bytes**, SHA-256 `e72409ea7cdc3f0d980be4f90e2b3affca893af2936a157afb0f459131325214`. Complete ways have **zero missing node references**. Some enclosing relations have members outside the available provider extracts: the private reference audit records 72 missing node references, 12,792 way references and 971 relation references. These are not silently claimed complete. Full source ledger: [puy-leveque-osm-20261025.json](../offline-regions/sources/puy-leveque-osm-20261025.json). OSM attribution/ODbL and the map's WorldCover/Natural Earth/Protomaps notices remain visible.

Elevation is real **Copernicus GLO-30 2021 DSM**, converted from EGM2008 to **EGM96** using pinned NGA geoid grids, never labelled IGN ground elevation or IGN69. No verified reusable Lot IGN ground dataset was available locally. Final bounds require HGT **N44E000 and N44E001**. The COG mirror omits south/east shared samples, so sources include N43/N44 × E000/E001/E002 plus both geoid grids. Exact URLs, dates, sizes and hashes are in [copernicus-2021-puy-leveque.json](../offline-regions/sources/copernicus-2021-puy-leveque.json). Six new COGs were checked against Content-Length and S3 MD5 ETags; both existing geoid grids were rehashed before reuse. Conversion uses the existing `cop-dem-cog-egm96-v1` code, no network datum operation and no fill. Both HGTs have zero void/invalid cells; all 3,601 shared seam samples agree. Ten independent original-COG/manual-geoid checks have maximum 0.458 m integer quantization error. This checks conversion, not surveyed terrain accuracy.

## Exact private build

Documented private regional build: `b544ba067b06bb69d53d13806c6b6b25d2f86f2e89a2d339c3dfd584c6544510`. `publication_allowed` remains **false**. Every descriptor/hash, archive, component schema and source/DEM/graph binding passes the existing verifier.

| Component ID | Installed bytes, including component manifest | Primary data SHA-256 |
| --- | ---: | --- |
| `puy-leveque-vallee-lot-map-v1` | 23,442,754 | `dc8b01e577305827a3414814651767467e912e9c4659bab2c552c1e97dcba06a` |
| `puy-leveque-vallee-lot-routing-v2` | 15,759,631 | `1600f697cffb3033caaefbb6912841c5c5bba3dba6080728fc28592c7e12acb7` |
| `puy-leveque-vallee-lot-pois-v1` | 33,913 | `60b4671bc0378ee397135f20fa0b3edb4d9c78686626c6e1eb308e2ebd1f89d1` |
| `puy-leveque-vallee-lot-nature-v1` | 4,862,058 | `af553fa7910ce56ea79efbc93ad62f6029d1cf81d71701984525109c2811402b` |
| `puy-leveque-vallee-lot-elevation-v2` | 19,560,388 | `104dbc3bb254c56696c30a9c46810c50799823495ed149adb5546c67142457f6` |

Component total: **63,658,744 bytes**; regional manifest adds 2,912 bytes. Elevation's identity in the table is its manifest; its two HGT hashes are `c0f6e1d5151fdb97471af22d5f2a8780e309af17b62217d0b6fba062e5bd8c18` and `b405ebc195823ab955f934246b54e662dea6478503085e7273ca7ee1e709ce44`. The routing archive contains **15 genuine native Valhalla 3.9.1 tiles**, all with embedded elevation. Places has **593 features**, with access/potability classes retained. Nature has **17,100 features / 670,304 positions**, below the unchanged 2,000,000-position admission limit.

Final sequential build: **162.14 s**, maximum host-process RSS **2,162,444 KiB**. Containers were bounded to **3,072 MiB, 2 CPUs, no swap**; the observed cgroup peak reached that memory cap (including reclaimable cache). Existing support downloads were reused. The first smaller rectangle exposed a genuine empty Valhalla bin tile without an elevation flag and failed closed. Expanding east to 1.60 yielded a graph accepted by the unchanged Python and Android archive contract; the rejected experiment was never distributed.

## Real offline route acceptance

The unchanged browser `createLocalPlanner`, canonical publisher, local Nature reader and GPX exporter were exercised against a persistent **native Valhalla 3.9.1 host actor** in a Docker container with **network=none**, mounted read-only to this new graph and DEM. Browser external requests were blocked. The host adapter mirrors the app's six numeric profile policies and strict continuous-leg join; its wire engine label is a test adapter, not evidence of executing Valhalla Mobile on Android. Physical Trail Run/Hike acceptance still needs the authorized installation below.

Test start: **Rue du Fort**, OSM node **9663322832**, way **329836426**, `(44.5040006, 1.137021)`. This is a reproducible mapped test point, not the user's asserted starting point or an access guarantee. Seed 35, three candidates, ±10% tolerance, ordinary bounded search. All searches used **12/24** native calls, and cache accounting invariants pass.

| Profile / target | Recommended actual distance | DSM D+ / D− | Woodland | Unknown land cover |
| --- | ---: | ---: | ---: | ---: |
| trail_run / 20 km | 21.248 km | 433 / 433 m | 39.6% | 47.9% |
| trail_run / 35 km | 34.364 km | 710 / 710 m | 40.8% | 50.1% |
| trail_run / 48 km | 49.883 km | 934 / 934 m | 42.3% | 47.7% |
| hike / 20 km | 19.901 km | 539 / 539 m | 50.8% | 43.8% |
| hike / 35 km | 33.287 km | 817 / 817 m | 49.1% | 41.7% |
| hike / 48 km | 47.517 km | 1092 / 1092 m | 51.8% | 42.4% |

All **18** retained candidates pass: start error **3.88 m**, **0 m** closure gap, genuine continuous native legs, explicit profile, authoritative native distance, Nature partition sums and complete elevation coverage. Native height/HGT differences are below 0.010001 m serialization tolerance. Elevation uses existing 50 m sampling, `distance-box-v1`, 50 m smoothing radius and 100 m maximum gap. Every GPX has exactly one track/segment, no route/analysis/Nature extensions, and the returned geometry's vertices in the same order. Export issues no routing call. The four cycling profiles also return real native routes. Nature shares are mapped measurements; unknown remains unknown, exact edge repetition/path attributes remain unavailable in the mobile wrapper, and there is no repetition-free/access promise. No GPX files or private route snapshots enter Git.

## Reproduce and install privately

Large inputs, components, generated GPX and receipts live outside Git under `/home/pompote/sugarglider-coverage-2026-10-27/`. The independently usable region is `outputs/lot-documented/`. The verified staging site is `outputs/private-distribution/site/`; its `catalog.json` adds **Puy-l'Évêque et vallée du Lot** and retains the exact existing Marly/Yvelines component bytes. Their catalog host changes only in this new private copy. The Lot-only ZIP remains a separate self-contained artifact; the combined site is authoritative for the staging APK.

```sh
uv sync --frozen --group dem
uv run --group dem python -m sugarglider.offline_regions.terrain_pipeline convert \
  --pins offline-regions/sources/copernicus-2021-puy-leveque.json \
  --source /private/copernicus-originals --output /private/new-skadi \
  --bounds 0.90 44.30 1.60 44.75
uv run python -m sugarglider.offline_regions build \
  --region puy-leveque-vallee-lot --pbf /private/puy-leveque-expanded-20261025.osm.pbf \
  --elevation-sources /private/new-skadi/elevation-inputs.json
```

The original staging CA expired on **21 October**. A new private CA/server certificate is prepared through **10 November**, trusted only by the explicit staging variant for localhost. Actual HTTPS streamed all **9 files / 63,658,744 bytes**, verified every size/hash, Android-origin CORS, no redirect/content encoding and a genuine PMTiles range. No public host is used.

Installation is a separate explicitly authorized action. Exact private procedure and APK receipt are in the local `INSTALLATION.md` and `evidence/` directory: preserve the current full browser draft (including the user's 23.172 km route), verify package/signature/catalog, update only `io.github.victorgabillon.sugarglider.v2staging` if required for the new CA/catalog, use a USB reverse tunnel to loopback port **9444**, open **Regions**, and download/select **Puy-l'Évêque et vallée du Lot**. Do not remove, replace or reinstall existing regions; verify their hashes and the original route before/after. Then test Trail Run/Hike in airplane mode. No installation authorization is inferred from source PR approval.

Validation: **`make check`: Ruff, strict mypy, 1,627 tests passed / 16 external-service tests deselected**. Unit tests use no network, real data, Docker or services. Physical Fairphone timing, memory, thermal behavior and Android OPFS acceptance remain pending.
