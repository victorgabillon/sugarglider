# PR33 regional routing-pack foundation

PR33 generalizes the physically validated PR32 Marly fixture into a debug-only,
multi-region routing-pack foundation. It does not add downloads, automatic
updates, a production offline-area UI, local Auto Tour, or GraphHopper parity.
GraphHopper remains the reference backend.

## Pack format and discovery

Each installed pack is an immediate child of the application's private
`files/routing-packs` directory and requires these two fixed runtime artifacts:

```text
routing-packs/
  marly-dev-v1/
    manifest.json
    valhalla_tiles.tar
  paris-dev-v1/
    manifest.json
    valhalla_tiles.tar
```

Manifest schema v1 is intentionally small:

```json
{
  "schema_version": 1,
  "pack_id": "marly-dev-v1",
  "engine": "valhalla",
  "engine_version": "3.6.3",
  "bounds": {
    "west": 2.0,
    "south": 48.8,
    "east": 2.16,
    "north": 48.94
  }
}
```

Parsing rejects extra or missing fields, unsupported schema/engine versions,
invalid or non-finite bounds, unsafe IDs, and a `pack_id` that differs from its
directory. Paths are never read from the manifest. Both the bounded manifest
and a fixed `valhalla_tiles.tar` with the expected Valhalla `index.bin` TAR
header must be present inside the pack directory.

Bounds use inclusive west, south, east, and north edges. A route is eligible
only when one installed pack contains both endpoints. Overlapping packs are
ordered deterministically by smallest rectangular bounds area, then by
lexicographic `pack_id`. Separate graphs are never stitched; no common pack
returns `no_covering_routing_pack` rather than `no_route`.

The debug engine retains one current Valhalla actor. Repeated requests using an
unchanged pack reuse it. Selecting another pack replaces the current actor;
returning to the first pack initializes it again. No unbounded actor cache is
kept. Routing remains serialized and off the UI thread. Public `hike` still
maps to experimental Valhalla `pedestrian` costing and is not claimed
equivalent to the production GraphHopper `hike` profile.

## Reproducible development packs

Both ignored development packs are derived from the configured local
Île-de-France PBF with Valhalla 3.6.3:

```sh
UV_CACHE_DIR=/tmp/sugarglider-uv-cache \
  ./scripts/build_pr33_development_packs.sh
```

The fixed regions are:

| Pack | Bounds |
| --- | --- |
| `marly-dev-v1` | `2.00,48.80,2.16,48.94` |
| `paris-dev-v1` | `2.25,48.80,2.42,48.92` |

The builder writes `manifest.json` next to the normalized tile archive and
prints both checksums and exact artifact sizes. Generated PBFs, manifests, tile
archives, and Valhalla working files remain ignored under `data/valhalla/`.
Each build completes in a clean staging directory before publication. The
publisher removes only its fixed known outputs in the validated target pack
directory, including the old PR32 `marly.osm.pbf`, `valhalla.json`, and `tiles/`
residues; it does not clear arbitrary files. There is no runtime network
download.

Install both already-built packs into Sugarglider Debug:

```sh
adb install -r android/app/build/outputs/apk/debug/app-debug.apk
for pack in marly-dev-v1 paris-dev-v1; do
  adb shell run-as io.github.victorgabillon.sugarglider.debug \
    mkdir -p "files/routing-packs/$pack"
  for file in manifest.json valhalla_tiles.tar; do
    adb push "data/valhalla/$pack/$file" "/data/local/tmp/$pack-$file"
    adb shell run-as io.github.victorgabillon.sugarglider.debug \
      cp "/data/local/tmp/$pack-$file" "files/routing-packs/$pack/$file"
    adb shell rm "/data/local/tmp/$pack-$file"
  done
done
adb shell am force-stop io.github.victorgabillon.sugarglider.debug
```

## Physical acceptance

PR33 physical acceptance passed on a physical Fairphone 6 using Sugarglider
Debug package `io.github.victorgabillon.sugarglider.debug`. Both
`marly-dev-v1` and `paris-dev-v1` were installed. The UI reported exactly:

> Installed regional packs (2): marly-dev-v1, paris-dev-v1.

FastAPI and GraphHopper were stopped, no `adb reverse` mappings remained,
`airplane_mode_on = 1`, and Wi-Fi was disabled. The app was force-stopped and
successfully relaunched while already offline. Its cached PWA shell continued
to run and the native bridge remained available.

The automated physical sequence was Marly, Marly, Paris, Paris, Marly, then
cross-pack. All successful runs used `valhalla-mobile` version
`0.5.1/valhalla-3.6.3`:

| Run | Result | Mode | Distance | Duration | Geometry | Pack | Initialization | Route | PSS before initialization | PSS after initialization | PSS after routing |
| --- | --- | --- | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: |
| Marly #1 | success | Cold local Valhalla experiment | 3.98 km | 47 min | 246 vertices | `marly-dev-v1` | 1051 ms | 916 ms | 165.5 MiB | 211.4 MiB | 221.8 MiB |
| Marly #2 | success | Warm local Valhalla experiment | 3.98 km | 47 min | 246 vertices | `marly-dev-v1` | 0 ms | 51 ms | 165.5 MiB | 211.4 MiB | 221.5 MiB |
| Paris #1 | success | Cold local Valhalla experiment | 3.94 km | 47 min | 208 vertices | `paris-dev-v1` | 49 ms | 138 ms | 222.4 MiB | 222.5 MiB | 220.0 MiB |
| Paris #2 | success | Warm local Valhalla experiment | 3.94 km | 47 min | 208 vertices | `paris-dev-v1` | 0 ms | 71 ms | 222.4 MiB | 222.5 MiB | 219.1 MiB |
| Marly #3 | success | Cold local Valhalla experiment | 3.98 km | 47 min | 246 vertices | `marly-dev-v1` | 37 ms | 72 ms | 219.4 MiB | 219.4 MiB | 220.5 MiB |

The cross-pack request failed as expected with
`no_covering_routing_pack` and displayed:

> No single installed regional pack covers both endpoints.

No graph stitching, backend, network, or straight-line fallback occurred. The
physical acceptance JSON was captured temporarily at
`/tmp/pr33-physical-acceptance.json`; it is ephemeral test evidence and is not
tracked by Git.

PR33 therefore passes physical acceptance: multiple regional packs were
discovered on-device; deterministic regional selection and same-pack actor
reuse worked; switching Marly to Paris and Paris back to Marly worked; the
single-current-actor lifecycle behaved as designed; and uncovered cross-pack
routing failed explicitly. All of this was demonstrated with the backend and
network unavailable.

The latency and PSS readings above are observations from these runs, not general
performance claims. PR33 still does not establish GraphHopper replacement,
profile or route-quality parity, alternative-route parity, round-trip or
isochrone parity, custom-model/corridor-penalty parity, edge-ID/path-attribute
parity, or full Auto Tour portability.
