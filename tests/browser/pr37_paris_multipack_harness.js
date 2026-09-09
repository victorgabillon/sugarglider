import { createOfflineMapRuntime } from "../../src/sugarglider/web/static/offline_map.js";
import { parseMapPackManifest } from "../../src/sugarglider/web/static/map_pack_manifest.js";
import { initialMapStyle } from "../../src/sugarglider/web/static/map.js";

// Real archive identities; no archive bytes or generated manifests are loaded.
const PACK_IDENTITIES = {
  "marly": {
    "pack_id": "marly-map-dev-v1",
    "bounds": [2.0, 48.8, 2.16, 48.94],
    "byte_size": 11614476,
    "build_id": "protomaps-3ea8293a2813-pbf-5e8bc36971c21776-pmtiles-da1eb88daf572190"
  },
  "paris": {
    "pack_id": "paris-map-dev-v1",
    "bounds": [2.25, 48.8, 2.42, 48.92],
    "byte_size": 29214469,
    "build_id": "protomaps-3ea8293a2813-pbf-5e8bc36971c21776-pmtiles-6791c9e03eac9a23"
  }
};
const MARLY = manifest(PACK_IDENTITIES.marly);
const PARIS = manifest(PACK_IDENTITIES.paris);
const MARLY_CENTER = [2.08, 48.87];
const GAP_CENTER = [2.205, 48.87];
const PARIS_CENTER = [2.335, 48.86];
const LOCAL_SOURCE = "sugarglider-local-map-pack";
const LOCAL_PREFIX = `${LOCAL_SOURCE}-`;
const OVERLAYS = [
  "selected-route",
  "required-point-labels-ordinary",
  "local-routing-experiment-line",
  "local-auto-tour-experiment-line",
  "planner-current-location-avatar",
  "outing-live-position-marker",
];

export async function runPr37ParisMultipackHarness() {
  const scenarios = [];
  for (const offline of [true, false]) {
    await scenarioSequence(offline);
    scenarios.push(offline ? "offline_marly_gap_paris_gap_marly" : "online_marly_gap_paris_gap_marly");
  }
  await scenarioDirectSwitch();
  scenarios.push("direct_switch_removes_old_layers_before_source_replacement");
  await scenarioSelection();
  scenarios.push("inclusive_bounds_and_order_independent_bootstrap_selection");
  await scenarioNetworkHints();
  scenarios.push("gap_connectivity_changes_preserve_overlays");
  for (const fail of [false, true]) {
    await scenarioStaleOpen(fail);
    scenarios.push(fail ? "stale_marly_rejection_cannot_clear_paris" : "stale_marly_completion_cannot_overwrite_paris");
  }
  await scenarioStaleOpenIntoGap();
  scenarios.push("stale_local_completion_cannot_replace_neutral_gap");
  await scenarioReturnToActivePack();
  scenarios.push("return_to_active_marly_invalidates_pending_paris");
  return scenarios;
}

async function scenarioSequence(offline) {
  const fixture = await setup({ offline });
  await fixture.runtime.attachMap(fixture.map, fixture.config);
  assertLocal(fixture, MARLY);
  for (const [center, pack] of [
    [GAP_CENTER, null], [PARIS_CENTER, PARIS], [GAP_CENTER, null], [MARLY_CENTER, MARLY],
  ]) {
    await fixture.map.moveTo(center);
    if (pack) assertLocal(fixture, pack);
    else assertGap(fixture, offline);
  }
  same(fixture.openCalls, [MARLY.pack_id, PARIS.pack_id, MARLY.pack_id], "only selected packs opened");
  fixture.runtime.detachMap(fixture.map);
}

async function scenarioDirectSwitch() {
  const fixture = await setup();
  await fixture.runtime.attachMap(fixture.map, fixture.config);
  assertLocal(fixture, MARLY);
  for (const [center, pack] of [[PARIS_CENTER, PARIS], [MARLY_CENTER, MARLY]]) {
    const previousSource = fixture.map.getSource(LOCAL_SOURCE);
    const previousLayers = localLayers(fixture.map);
    fixture.map.events.length = 0;
    await fixture.map.moveTo(center);
    assertLocal(fixture, pack);
    assert(fixture.map.getSource(LOCAL_SOURCE) !== previousSource, "old source object replaced");
    assert(previousLayers.every((layer) => !fixture.map.layers.includes(layer)), "old layer objects removed");
    const removedSource = fixture.map.events.indexOf(`remove-source:${LOCAL_SOURCE}`);
    const addedSource = fixture.map.events.indexOf(`add-source:${LOCAL_SOURCE}`);
    assert(removedSource >= 0 && addedSource > removedSource, "source removed before replacement");
    for (const layer of previousLayers) {
      const removedLayer = fixture.map.events.indexOf(`remove-layer:${layer.id}`);
      assert(removedLayer >= 0 && removedLayer < removedSource, "each stale layer removed before its source");
    }
  }
  fixture.runtime.detachMap(fixture.map);
}

async function scenarioSelection() {
  const broad = manifest({ ...PACK_IDENTITIES.marly, pack_id: "a-broad", bounds: [1.9, 48.7, 2.5, 49] });
  const tie = manifest({ ...PACK_IDENTITIES.paris, pack_id: "z-paris-tie" });
  for (const packs of [[broad, tie, PARIS, MARLY], [MARLY, PARIS, tie, broad]]) {
    const fixture = await setup({ packs, center: PARIS_CENTER });
    same(fixture.runtime.bootstrapForConfig(fixture.config).pack_id, PARIS.pack_id, "smallest area then ID");
    assert(!fixture.map.getSource("osm"), "Paris bootstrap suppresses raster with multiple packs");
    await fixture.runtime.attachMap(fixture.map, fixture.config);
    assertLocal(fixture, PARIS);
    for (const pack of [MARLY, PARIS]) {
      const [west, south, east, north] = pack.bounds;
      for (const center of [[west, south], [east, north]]) {
        same(fixture.runtime.bootstrapForConfig({ ...fixture.config, initial_center: center }).pack_id, pack.pack_id, "inclusive bootstrap boundary");
        await fixture.map.moveTo(center);
        assertLocal(fixture, pack);
      }
    }
    fixture.runtime.detachMap(fixture.map);
  }
}

async function scenarioNetworkHints() {
  const fixture = await setup({ center: GAP_CENTER });
  await fixture.runtime.attachMap(fixture.map, fixture.config);
  assertGap(fixture, false);
  await fixture.browserWindow.emit("offline");
  assertGap(fixture, true);
  await fixture.map.moveTo(PARIS_CENTER);
  assertLocal(fixture, PARIS);
  await fixture.map.moveTo(GAP_CENTER);
  assertGap(fixture, true);
  await fixture.browserWindow.emit("online");
  assertGap(fixture, false);
  fixture.runtime.detachMap(fixture.map);
}

async function scenarioStaleOpen(fail) {
  const pending = deferred();
  const fixture = await setup({ open: (pack) => pack === MARLY ? pending.promise : Promise.resolve(opened(pack)) });
  const attaching = fixture.runtime.attachMap(fixture.map, fixture.config);
  same(fixture.openCalls, [MARLY.pack_id], "Marly open has begun");
  await fixture.map.moveTo(PARIS_CENTER);
  assertLocal(fixture, PARIS);
  const parisSource = fixture.map.getSource(LOCAL_SOURCE);
  const eventsBefore = [...fixture.map.events];
  if (fail) pending.reject(new Error("deferred Marly failure"));
  else pending.resolve(opened(MARLY));
  await attaching;
  assertLocal(fixture, PARIS);
  assert(fixture.map.getSource(LOCAL_SOURCE) === parisSource, "stale completion cannot replace source");
  same(fixture.map.events, eventsBefore, "stale success/failure cannot mutate map");
  fixture.runtime.detachMap(fixture.map);
}

async function scenarioStaleOpenIntoGap() {
  const pending = deferred();
  const fixture = await setup({ offline: true, open: () => pending.promise });
  const attaching = fixture.runtime.attachMap(fixture.map, fixture.config);
  await fixture.map.moveTo(GAP_CENTER);
  assertGap(fixture, true);
  pending.resolve(opened(MARLY));
  await attaching;
  assertGap(fixture, true);
  fixture.runtime.detachMap(fixture.map);
}

async function scenarioReturnToActivePack() {
  const pending = deferred();
  const fixture = await setup({ open: (pack) => pack === PARIS ? pending.promise : Promise.resolve(opened(pack)) });
  await fixture.runtime.attachMap(fixture.map, fixture.config);
  assertLocal(fixture, MARLY);
  const originalSource = fixture.map.getSource(LOCAL_SOURCE);
  await fixture.map.moveTo(PARIS_CENTER);
  same(fixture.openCalls, [MARLY.pack_id, PARIS.pack_id], "Paris open is pending");
  await fixture.map.moveTo(MARLY_CENTER);
  pending.resolve(opened(PARIS));
  // openPackSource returns this exact promise. Its registered runtime continuation
  // runs before this continuation; no clock delay or polling is needed.
  await pending.promise;
  assertLocal(fixture, MARLY);
  assert(fixture.map.getSource(LOCAL_SOURCE) === originalSource, "return keeps the existing Marly source");
  same(fixture.openCalls.length, 2, "active Marly is reused without reopening");
  fixture.runtime.detachMap(fixture.map);
}

async function setup({ offline = false, center = MARLY_CENTER, packs = [PARIS, MARLY], open = (pack) => Promise.resolve(opened(pack)) } = {}) {
  const browserWindow = eventHub();
  const elements = { status: { dataset: {}, textContent: "" }, active: { textContent: "" } };
  const openCalls = [];
  const runtime = createOfflineMapRuntime({
    store: {
      capabilities: async () => ({ opfs_supported: true, random_access: true }),
      scanInstalledPacks: async () => ({ packs, partial_pack_ids: [], invalid_pack_ids: [] }),
      openPackSource(packId) {
        openCalls.push(packId);
        const pack = packs.find((candidate) => candidate.pack_id === packId);
        assert(pack, "only an installed pack may be opened");
        return open(pack);
      },
    },
    maplibregl: { addProtocol(name, handler) { same(name, "pmtiles", "shared PMTiles protocol"); assert(typeof handler === "function", "protocol registered"); } },
    browserWindow,
    elements,
  });
  await runtime.initialize();
  assert(runtime.snapshot().protocol_available, "vendored PMTiles protocol available");
  // Explicitly drive the network policy so the harness does not depend on its host.
  await browserWindow.emit(offline ? "offline" : "online");
  const config = {
    offline_mode: offline,
    initial_center: center,
    tile_url_template: "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    tile_attribution: "© OpenStreetMap contributors",
  };
  const map = fakeMap(center, initialMapStyle(config, runtime.bootstrapForConfig(config)));
  return { runtime, map, config, browserWindow, elements, openCalls };
}

function assertLocal(fixture, pack) {
  const { runtime, map, elements } = fixture;
  same(runtime.snapshot().active_pack_id, pack.pack_id, "active pack identity");
  same(runtime.snapshot().status.state, "local_pack_active", "local status");
  same(elements.status.dataset.state, "local_pack_active", "displayed status");
  same([...map.sources.keys()].filter((id) => !OVERLAYS.includes(id)), [LOCAL_SOURCE], "only one basemap source");
  const source = map.getSource(LOCAL_SOURCE);
  same(source.url, `pmtiles://${sourceKey(pack)}`, "opened source identity");
  same(source.bounds, pack.bounds, "only selected region is rendered");
  same(source.attribution, pack.attribution, "active source attribution");
  assert(elements.active.textContent.includes(pack.attribution), "active attribution displayed");
  const layers = localLayers(map);
  assert(layers.length > 0, "local layers installed");
  same(new Set(layers.map((layer) => layer.id)).size, layers.length, "no duplicate local layers");
  assert(layers.every((layer) => layer.source === LOCAL_SOURCE), "all local layers use selected source");
  assert(!map.getLayer("osm") && !map.getSource("osm"), "raster absent during local rendering");
  assertOverlays(map);
}

function assertGap(fixture, offline) {
  const { runtime, map, elements, config } = fixture;
  same(runtime.snapshot().active_pack_id, null, "gap has no active pack");
  same(runtime.snapshot().active_source_diagnostics, null, "gap has no active local reader");
  const expected = offline ? "no_covering_map_pack" : "online_map_active";
  same(runtime.snapshot().status.state, expected, "truthful gap state");
  same(elements.status.dataset.state, expected, "displayed gap state");
  same(localLayers(map).length, 0, "stale local layers gone");
  assert(!map.getSource(LOCAL_SOURCE), "local source removed");
  same([...map.sources.keys()].filter((id) => !OVERLAYS.includes(id)), offline ? [] : ["osm"], "only allowed gap source");
  if (offline) assert(!map.getLayer("osm"), "offline gap has no raster layer");
  else {
    same(map.getSource("osm").tiles, [config.tile_url_template], "configured online raster");
    same(map.getSource("osm").attribution, config.tile_attribution, "online attribution");
    same(map.getLayer("osm").source, "osm", "online layer source");
  }
  assertOverlays(map);
}

function assertOverlays(map) {
  assert(map.getLayer("offline-background"), "neutral background survives");
  same(map.errors, [], "MapLibre mutation preconditions respected");
  const firstOverlay = map.layers.findIndex((layer) => layer.id === OVERLAYS[0]);
  for (const layer of map.layers) {
    if (layer.id.startsWith(LOCAL_PREFIX) || layer.id === "osm") {
      assert(map.layers.indexOf(layer) < firstOverlay, "basemap stays below overlays");
    }
  }
  same(map.layers.filter((layer) => OVERLAYS.includes(layer.id)).map((layer) => layer.id), OVERLAYS, "overlay order preserved");
  for (const original of map.originalOverlays) {
    assert(map.getLayer(original.layer.id) === original.layer, "overlay layer identity preserved");
    assert(map.getSource(original.layer.source) === original.source, "overlay data identity preserved");
  }
}

function fakeMap(initialCenter, style) {
  let center = initialCenter;
  const hub = eventHub();
  const sources = new Map(Object.entries(style.sources));
  const layers = [...style.layers];
  const errors = [];
  const events = [];
  const originalOverlays = OVERLAYS.map((id) => {
    const source = { type: "geojson", data: { type: "FeatureCollection", features: [] } };
    const layer = { id, type: "line", source: id };
    sources.set(id, source);
    layers.push(layer);
    return { layer, source };
  });
  function require(condition, message) {
    if (!condition) { errors.push(message); throw new Error(message); }
  }
  return {
    sources, layers, events, errors, originalOverlays,
    getCenter: () => ({ lng: center[0], lat: center[1] }),
    moveTo(value) { center = value; return hub.emit("moveend"); },
    on: hub.addEventListener,
    off: hub.removeEventListener,
    getStyle: () => ({ layers, sources: Object.fromEntries(sources) }),
    getLayer: (id) => layers.find((layer) => layer.id === id),
    getSource: (id) => sources.get(id),
    addSource(id, source) {
      require(!sources.has(id), `duplicate source ${id}`);
      sources.set(id, source);
      events.push(`add-source:${id}`);
    },
    removeSource(id) {
      require(sources.has(id), `missing source ${id}`);
      require(!layers.some((layer) => layer.source === id), `source ${id} still has layers`);
      sources.delete(id);
      events.push(`remove-source:${id}`);
    },
    addLayer(layer, beforeId) {
      require(!layers.some((existing) => existing.id === layer.id), `duplicate layer ${layer.id}`);
      require(!layer.source || sources.has(layer.source), `missing source for ${layer.id}`);
      const index = beforeId ? layers.findIndex((existing) => existing.id === beforeId) : layers.length;
      require(index >= 0, `missing insertion layer ${beforeId}`);
      layers.splice(index, 0, layer);
      events.push(`add-layer:${layer.id}`);
    },
    removeLayer(id) {
      const index = layers.findIndex((layer) => layer.id === id);
      require(index >= 0, `missing layer ${id}`);
      layers.splice(index, 1);
      events.push(`remove-layer:${id}`);
    },
  };
}

function eventHub() {
  const listeners = new Map();
  return {
    addEventListener(name, handler) {
      if (!listeners.has(name)) listeners.set(name, new Set());
      listeners.get(name).add(handler);
    },
    removeEventListener(name, handler) { listeners.get(name)?.delete(handler); },
    emit(name) {
      // Immediate fake opens queue their runtime continuation before Promise.all
      // settles. Deferred opens remain controlled by each race scenario.
      return Promise.all([...(listeners.get(name) ?? [])].map((handler) => handler()));
    },
  };
}

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

function manifest(identity) {
  return parseMapPackManifest({
    schema_version: 1,
    display_name: identity.pack_id,
    min_zoom: 0,
    max_zoom: 15,
    format: "pmtiles-v3",
    tile_type: "mvt",
    archive_filename: "basemap.pmtiles",
    // Distinct test labels expose stale attribution despite identical real credits.
    attribution: `© OpenStreetMap contributors · ${identity.pack_id} fixture`,
    data_source: "PR37 deterministic fixture",
    ...identity,
  });
}

function sourceKey(pack) {
  return `sugarglider-map-pack/${pack.pack_id}/${pack.build_id}`;
}

function opened(pack) {
  const source = { getKey: () => sourceKey(pack), diagnostics: () => ({ read_count: 0, bytes_read: 0 }) };
  return { manifest: pack, source, archive: { source } };
}

function localLayers(map) {
  return map.layers.filter((layer) => layer.id.startsWith(LOCAL_PREFIX));
}

function same(actual, expected, message) {
  assert(JSON.stringify(actual) === JSON.stringify(expected), `${message}: ${JSON.stringify(actual)} !== ${JSON.stringify(expected)}`);
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}
