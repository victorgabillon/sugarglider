import { createOfflineMapRuntime } from "../../src/sugarglider/web/static/offline_map.js";
import { parseMapPackManifest } from "../../src/sugarglider/web/static/map_pack_manifest.js";
import { manifest, mapStoreStub, createFakeMap } from "./pr36_offline_maps_harness.js";

const assert = (value, message) => { if (!value) throw Error(message); };
export async function run() {
  const original = globalThis.pmtiles, protocol = new original.Protocol();
  // Use the real pinned upstream registry, with synthetic archive handles.
  globalThis.pmtiles = { ...original, Protocol: class { constructor() { return protocol; } } };
  const bounds = [2, 48.8, 2.16, 48.94];
  let pack = parseMapPackManifest(manifest("marly-map-dev-v1", bounds, 4)), handler;
  const store = { ...mapStoreStub([pack]),
    scanInstalledPacks: () => mapStoreStub([pack]).scanInstalledPacks(),
    openPackSource: async id => {
      const opened = await mapStoreStub([pack]).openPackSource(id);
      opened.archive.getHeader = async () => ({ minLon: 2, minLat: 48.8, maxLon: 2.16, maxLat: 48.94, minZoom: 0, maxZoom: 0 });
      opened.archive.getZxy = async () => ({ data: new Uint8Array([1, 2, 3]).buffer });
      return opened;
    },
  };
  const map = createFakeMap({ lon: 2.09, lat: 48.88 });
  const runtime = createOfflineMapRuntime({ store, browserWindow: new EventTarget(),
    maplibregl: { addProtocol: (name, callback) => { handler = callback; } } });
  try {
    await runtime.initialize();
    await runtime.attachMap(map, { offline_mode: true });
    const retired = `pmtiles://${protocol.tiles.keys().next().value}`;
    for (let index = 0; index < 25; index++) {
      pack = parseMapPackManifest({ ...pack, build_id: `revision-${index}` });
      await runtime.refresh({ reopen: true });
      assert(protocol.tiles.size === 1, `Retired archives retained: ${protocol.tiles.size}`);
    }
    const active = `pmtiles://${protocol.tiles.keys().next().value}`;
    const header = await handler({ url: active, type: "json" }, new AbortController());
    assert(header.data.tiles[0] === `${active}/{z}/{x}/{y}`, "Active archive header remains available");
    const tile = await handler({ url: `${active}/0/0/0`, type: "arrayBuffer" }, new AbortController());
    assert(tile.data.join() === "1,2,3", "Active archive tiles remain local");
    let fetches = 0;
    const originalFetch = globalThis.fetch;
    globalThis.fetch = async () => { fetches++; throw Error("Unexpected network fallback"); };
    try {
      for (const [url, type] of [[retired, "json"], [`${retired}/0/0/0`, "arrayBuffer"],
        ["pmtiles://https://invalid.example/terrain", "json"], ["pmtiles://unknown/0/0/0", "arrayBuffer"]]) {
        let rejected = false;
        try { await handler({ url, type }, new AbortController()); }
        catch { rejected = true; }
        assert(rejected, "Unavailable archive must fail explicitly");
      }
      assert(fetches === 0, "No implicit upstream FetchSource fallback");
    } finally { globalThis.fetch = originalFetch; }
    runtime.detachMap(map);
    assert(protocol.tiles.size === 0, "Detached map retains archive registry");
    await runtime.attachMap(map, { offline_mode: true });
    assert(protocol.tiles.size === 1, "Map can reattach its current archive");
    map.remove();
    assert(protocol.tiles.size === 0 && runtime.snapshot().active_pack_id === null, "Map removal must release archives");
    return ["25_replaced_versions_keep_one_archive", "active_header_and_tiles_remain_available", "retired_and_unknown_sources_fail_without_fetch", "detach_remove_and_reattach_release_archive_registry"];
  } finally { runtime.detachMap(map); globalThis.pmtiles = original; }
}
