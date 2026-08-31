# PR32 on-device routing spike

PR32 asks one narrow question: can the arm64 Fairphone calculate a graph-derived
OSM A-to-B route with FastAPI and GraphHopper unavailable? It does not replace
Generate, implement Auto Tour locally, or establish equivalence between
Sugarglider's server `hike` profile and Valhalla pedestrian costing.

## Feasibility decision

The spike uses `io.github.rallista:valhalla-mobile:0.5.1`, which pins Valhalla
3.6.3. Its Android library has minSdk 26, Java 17 bytecode, an arm64-v8a native
library, and a 16 KiB-compatible ELF load alignment. That fits Sugarglider's
minSdk 26, target/compile SDK 36, Java 17, and the target Fairphone. The same
upstream release also ships a Swift package, so an iOS route-only path is
credible but remains untested here.

The published AAR is 139,496,319 bytes and its unstripped arm64 native library
is 138,225,776 bytes. For this reason the dependency, ABI filter, engine adapter,
and browser capability are debug-only. Release builds use an unavailable engine
without linking Valhalla. No routing pack is embedded in the APK.

Valhalla requires a prebuilt graph tile archive and config. The route-only
mobile fixture works with a tile archive and does not require an admins or
timezone database. The pack builder therefore disables admin enrichment and
elevation; it does not download runtime data.

Measured local build artifacts on 2026-08-28:

| Artifact | Bytes |
| --- | ---: |
| Baseline debug APK at `c485a6f` | 7,713,759 |
| PR32 arm64 debug APK, without a routing pack | 144,107,100 |
| APK increase | 136,393,341 |
| Clipped Marly OSM PBF | 10,270,225 |
| Marly Valhalla tile archive | 11,653,120 |

The normalized archive SHA-256 is
`6ee0d833c288ec941ab6e23aa01640b59629ae8ac3c5c58c0a10c1ddf0ae6bc4`.
Two clean output-directory builds produced that same checksum. The nominal
181 km² bounding box implies about 64 kB/km² for this dense development area,
but tile boundaries and retained reference-complete ways mean this is not yet a
general regional-pack density claim.

## Boundaries

`NativeRouteEngine` owns the versioned coordinate/profile/result boundary.
Only `hike` is accepted and it maps explicitly to Valhalla `pedestrian` without
an equivalence claim. Failures are explicit; there is no straight-line or
network fallback. Geometry is limited to 20,000 vertices and the serialized
bridge response to 512 KiB.

The existing exact-origin, main-frame, current-WebView message listener is
extended with `get_local_route_capabilities` and `local_route`. Requests retain
the page nonce, ledger, replay, and navigation-epoch ownership. Calculation is
off the UI thread and a stale page cannot receive its result. Local requests
contain no outing capability, live position, or tracking state and require no
Android permission.

The browser surface is named **Local routing experiment** and remains hidden
unless the debug native capability is present. Its self-contained Marly smoke
test routes fixed fixture coordinates without reading normal planner points;
the optional A-to-B action still uses the first two planner points. Neither
action invokes the backend or changes Generate.

## Reproducible development pack

The ignored pack is derived from the existing local Île-de-France PBF with the
buffered bounds `2.00,48.80,2.16,48.94`, covering Marly-le-Roi, Versailles, and
Saint-Germain-en-Laye. It is built with exactly Valhalla 3.6.3:

```sh
UV_CACHE_DIR=/tmp/sugarglider-uv-cache \
  ./scripts/build_pr32_marly_valhalla_pack.sh
```

The script prints exact PBF/archive sizes and the archive SHA-256. Generated
files remain under ignored `data/valhalla/marly-dev-v1`. The final step
normalizes only fixed-size TAR header metadata in place, preserving the tile
offsets used by Valhalla's `index.bin`, so repeated builds do not differ merely
because of build time or container user names. Do not commit the pack without
first reviewing the printed measurements.

Install an already-built pack and debug APK without adding storage permission:

```sh
adb install -r android/app/build/outputs/apk/debug/app-debug.apk
adb push data/valhalla/marly-dev-v1/valhalla_tiles.tar /data/local/tmp/valhalla_tiles.tar
adb shell run-as io.github.victorgabillon.sugarglider.debug mkdir -p files/routing-packs/marly-dev-v1
adb shell run-as io.github.victorgabillon.sugarglider.debug cp /data/local/tmp/valhalla_tiles.tar files/routing-packs/marly-dev-v1/valhalla_tiles.tar
adb shell rm /data/local/tmp/valhalla_tiles.tar
adb shell am force-stop io.github.victorgabillon.sugarglider.debug
```

For physical offline acceptance:

1. Install the routing pack with the commands above.
2. Open **Sugarglider Debug** once while the application shell is available.
3. Stop both server processes on the development host:
   `docker compose stop api graphhopper`.
4. Remove reverse port mappings with `adb reverse --remove-all`.
5. Optionally enable airplane mode on the Fairphone.
6. Open **Layers → Local routing experiment**.
7. Press **Run Marly offline smoke test**. It routes directly from Marly-le-Roi
   (`48.8715, 2.0965`) to the Château de Saint-Germain-en-Laye
   (`48.8983, 2.0969`) without reading planner points.
8. Record the displayed cold distance, vertex count, engine/version,
   initialization and route latencies, and all three PSS observations.
9. Press **Run Marly offline smoke test** again.
10. Record the corresponding warm metrics.

If the debug WebView exposes its native bridge but the capability handshake
does not complete, the experiment remains visible with **Native routing
handshake unavailable.** and disabled actions. A release capability response
with `enabled=false` remains hidden.

The returned line is graph-derived local Valhalla geometry and is fitted on the
existing map. The last PSS value is only an approximate after-route memory
observation, not a sampled peak. These are diagnostics, not performance claims;
the physical observations below do not establish broader performance or route
quality parity.

## Physical Fairphone 6 acceptance

Physical acceptance succeeded with the following components:

- device: Fairphone 6;
- application: Sugarglider Debug,
  `io.github.victorgabillon.sugarglider.debug`;
- routing pack: `marly-dev-v1`;
- Valhalla Mobile: 0.5.1, using Valhalla engine 3.6.3;
- public profile: `hike`, mapped to experimental Valhalla `pedestrian` costing.
  This is explicitly not claimed equivalent to the production `hike` profile.

The fixed fixture was A `48.8715, 2.0965` to B `48.8983, 2.0969`.
FastAPI and GraphHopper were stopped and all `adb reverse` mappings were
removed. The phone was also in airplane mode for the warm run. The UI visibly
reported **Server features are unavailable**, while the local Marly smoke test
still succeeded.

| Observation | Cold run | Warm run |
| --- | ---: | ---: |
| Result | Success | Success |
| Distance | 3.98 km | 3.98 km |
| Estimated duration | 47 min | 47 min |
| Geometry | 246 vertices | 246 vertices |
| Engine | `valhalla-mobile` | `valhalla-mobile` |
| Engine version | `0.5.1/valhalla-3.6.3` | `0.5.1/valhalla-3.6.3` |
| Initialization | 1,061 ms | 0 ms |
| Route | 923 ms | 48 ms |
| PSS before initialization | 167.7 MiB | 180.4 MiB |
| PSS after initialization | 236.6 MiB | 207.3 MiB |
| PSS after routing | Unknown; not clearly exposed in the screenshot | Unknown; not clearly exposed in the screenshot |

### Conclusion

**PR32 PASS:** real graph-derived routing ran entirely on-device without a
FastAPI, GraphHopper, or network fallback. The cold and warm runs produced the
same 3.98 km, 246-vertex route. The on-device routing foundation is viable
enough to continue evaluation.

PR32 does not establish:

- GraphHopper replacement;
- profile or route-quality parity;
- alternative-route or round-trip support parity;
- isochrone parity;
- custom-model or corridor-penalty parity;
- edge-ID or path-attribute parity;
- full Auto Tour portability.

Valhalla remains candidate #1 for the next local-routing work. GraphHopper
remains the reference backend until those capabilities are demonstrated.

### Physical-test engineering findings

- A Play release/debug signing conflict required the side-by-side debug
  application ID.
- A stale PWA shell/cache affected physical testing.
- Raw WebView source-origin normalization required correction.
- Two JavaScript owners independently controlled `sugargliderNative`, the page
  nonce, and `onmessage`; the shared `native_bridge_transport` architecture
  fixed that ownership bug.
