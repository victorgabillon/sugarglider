import {
  MapPackManifestError,
  mapPackCoversCoordinate,
  parseMapPackManifest,
  selectMapPackForCoordinate,
} from "../../src/sugarglider/web/static/map_pack_manifest.js";
import {
  MapPackStore,
  probeOpfsMapPackStorage,
  validateMapPackInstallUrl,
} from "../../src/sugarglider/web/static/map_pack_store.js";
import {
  OpfsPmtilesSource,
  validateOpfsPmtilesArchive,
} from "../../src/sugarglider/web/static/opfs_pmtiles_source.js";
import {
  createOfflineMapRuntime,
  initializeOfflineMaps,
  offlineMapBootstrapForConfig,
} from "../../src/sugarglider/web/static/offline_map.js";
import {
  initialMapStyle,
} from "../../src/sugarglider/web/static/map.js";

const MARLY_BOUNDS = [2, 48.8, 2.16, 48.94];
const PARIS_BOUNDS = [2.25, 48.8, 2.42, 48.92];
const REQUIRED_LAYER_IDS = ["buildings", "earth", "landcover", "landuse", "roads", "water"];

export async function runPr36OfflineMapsHarness() {
  const scenarios = [];
  await scenarioRealOpfsCapability();
  scenarios.push("real_opfs_create_write_slice_read_delete");
  scenarioStrictManifest();
  scenarios.push("strict_manifest_and_unsafe_paths_rejected");
  scenarioDeterministicSelection();
  scenarios.push("inclusive_smallest_area_lexicographic_selection");
  await scenarioRandomAccess();
  scenarios.push("bounded_random_access_and_eof_handling");
  await scenarioRealPmtilesValidation();
  scenarios.push("official_pmtiles_source_validates_v3_mvt_schema");
  await scenarioCapabilityUnavailable();
  scenarios.push("opfs_capability_failure_is_explicit");
  await scenarioStoreLifecycle();
  scenarios.push("install_list_open_remove_and_reload");
  await scenarioPartialAndDuplicate();
  scenarios.push("partial_ignored_and_duplicate_install_explicit");
  await scenarioInterruptedInstall();
  scenarios.push("interrupted_install_never_becomes_active");
  await scenarioRegionalIntegrity();
  scenarios.push("regional_checksum_verified_before_map_activation");
  await scenarioRegionalCorruption();
  scenarios.push("regional_checksum_failure_never_activates_map");
  await scenarioRegionalDescriptorFailure();
  scenarios.push("regional_descriptor_and_size_failure_before_archive_download");
  scenarioInstallUrlSecurity();
  scenarios.push("install_url_policy_is_https_or_debug_private_http");
  await scenarioCoveringPackBootstrap();
  scenarios.push("covering_bootstrap_omits_online_raster_source");
  await scenarioBootstrapFallbackMatrix();
  scenarios.push("bootstrap_preserves_online_and_neutral_fallbacks");
  await scenarioFailedLocalOpenFallback();
  scenarios.push("failed_local_open_adds_only_truthful_fallback");
  await scenarioLocalMapIntegration();
  scenarios.push("offline_local_pack_and_attribution_render");
  await scenarioNoPackOfflineAndOnline();
  scenarios.push("neutral_offline_and_online_raster_states_are_explicit");
  await scenarioRegionSwitch();
  scenarios.push("region_switch_removes_stale_source_and_keeps_overlays");
  scenarioNoRemoteStyleAssets();
  scenarios.push("label_free_style_has_no_remote_glyph_or_sprite_dependency");
  return scenarios;
}

async function scenarioRealOpfsCapability() {
  const capability = await probeOpfsMapPackStorage({
    probeSuffix: "pr36-browser-harness",
  });
  assert(capability.opfs_supported, capability.reason ?? "OPFS unavailable");
  assert(capability.random_access, "OPFS random access is required");
}

function scenarioStrictManifest() {
  const valid = manifest("marly-map-dev-v1", MARLY_BOUNDS, 512);
  equal(parseMapPackManifest(valid).pack_id, "marly-map-dev-v1", "valid manifest");
  for (const mutation of [
    (value) => { value.unknown = true; },
    (value) => { value.pack_id = "../marly"; },
    (value) => { value.archive_filename = "../basemap.pmtiles"; },
    (value) => { value.archive_filename = "https://packs.test/map.pmtiles"; },
    (value) => { value.bounds = [2, 48.8, 2, 48.94]; },
    (value) => { value.bounds = [2, Number.NaN, 2.16, 48.94]; },
    (value) => { value.min_zoom = 23; },
    (value) => { value.max_zoom = -1; },
    (value) => { value.byte_size = 0; },
    (value) => { value.attribution = ""; },
    (value) => { value.schema_version = 2; },
  ]) {
    const candidate = structuredClone(valid);
    mutation(candidate);
    throws(() => parseMapPackManifest(candidate), MapPackManifestError);
  }
}

function scenarioDeterministicSelection() {
  const broad = parseMapPackManifest(manifest("z-broad", [1.9, 48.7, 2.3, 49], 100));
  const tieB = parseMapPackManifest(manifest("b-local", MARLY_BOUNDS, 100));
  const tieA = parseMapPackManifest(manifest("a-local", MARLY_BOUNDS, 100));
  assert(mapPackCoversCoordinate(tieA, { lon: 2, lat: 48.8 }), "west/south inclusive");
  assert(mapPackCoversCoordinate(tieA, { lon: 2.16, lat: 48.94 }), "east/north inclusive");
  equal(
    selectMapPackForCoordinate([broad, tieB, tieA], { lon: 2.1, lat: 48.9 }).pack_id,
    "a-local",
    "smallest then lexicographic",
  );
  equal(selectMapPackForCoordinate([tieA], { lon: 3, lat: 49 }), null, "no covering pack");
}

async function scenarioRandomAccess() {
  const handle = new MemoryFileHandle("basemap.pmtiles", new Uint8Array([3, 5, 7, 11, 13]));
  const source = new OpfsPmtilesSource({
    fileHandle: handle,
    key: "sugarglider-map-pack/range/build",
    expectedSize: 5,
  });
  bytesEqual(new Uint8Array((await source.getBytes(1, 3)).data), [5, 7, 11], "exact range");
  bytesEqual(new Uint8Array((await source.getBytes(3, 8)).data), [11, 13], "EOF-clamped range");
  await rejects(() => source.getBytes(5, 1), "beyond EOF");
  await rejects(() => source.getBytes(0, 64 * 1024 * 1024), "oversized read");
  equal(source.diagnostics().read_count, 2, "read count");
  equal(source.diagnostics().bytes_read, 5, "only sliced bytes counted");
}

async function scenarioRealPmtilesValidation() {
  const bytes = tinyPmtiles(MARLY_BOUNDS, 0, 14);
  const pack = parseMapPackManifest(manifest("real-pmtiles", MARLY_BOUNDS, bytes.length));
  const source = new OpfsPmtilesSource({
    fileHandle: new MemoryFileHandle("basemap.pmtiles", bytes),
    key: "sugarglider-map-pack/real-pmtiles/build",
    expectedSize: bytes.length,
  });
  const validated = await validateOpfsPmtilesArchive({ source, manifest: pack });
  equal(validated.header.specVersion, 3, "PMTiles spec version");
  equal(validated.header.tileType, 1, "MVT tile type");
  assert(source.diagnostics().bytes_read < bytes.length * 2, "validator uses bounded range reads");
  const wrong = parseMapPackManifest({ ...manifest("wrong", MARLY_BOUNDS, bytes.length), max_zoom: 13 });
  await rejects(
    () => validateOpfsPmtilesArchive({ source: new OpfsPmtilesSource({
      fileHandle: new MemoryFileHandle("basemap.pmtiles", bytes),
      key: "sugarglider-map-pack/wrong/build",
      expectedSize: bytes.length,
    }), manifest: wrong }),
    "header mismatch",
  );
}

async function scenarioCapabilityUnavailable() {
  const capability = await probeOpfsMapPackStorage({ storageManager: {} });
  equal(capability.opfs_supported, false, "unsupported OPFS");
  equal(capability.state, "map_pack_storage_unavailable", "explicit unsupported state");
}

async function scenarioStoreLifecycle() {
  const storageManager = createMemoryStorageManager();
  const archive = new Uint8Array([1, 2, 3, 4]);
  const fetchLog = [];
  const store = createTestStore({ storageManager, archive, fetchLog });
  const installed = await store.installPack("https://packs.test/marly/manifest.json");
  equal(installed.pack_id, "marly-map-dev-v1", "installed pack identity");
  equal((await store.listInstalledPacks()).length, 1, "installed list");
  const reopened = createTestStore({ storageManager, archive, fetchLog: [] });
  equal((await reopened.listInstalledPacks())[0].pack_id, installed.pack_id, "process reload reopens pack");
  equal((await reopened.openPackSource(installed.pack_id)).source.expectedSize, 4, "source reopened");
  assert(fetchLog.every((entry) => entry.options.credentials === "omit"), "credentials omitted");
  assert(fetchLog.every((entry) => entry.options.cache === "no-store"), "downloads bypass HTTP cache");
  await reopened.removePack(installed.pack_id);
  equal((await reopened.listInstalledPacks()).length, 0, "explicit remove");
}

async function scenarioPartialAndDuplicate() {
  const storageManager = createMemoryStorageManager();
  const root = await storageManager.getDirectory();
  const packRoot = await root.getDirectoryHandle("sugarglider-map-packs", { create: true });
  const partial = await packRoot.getDirectoryHandle("partial-pack", { create: true });
  await partial.getFileHandle("basemap.pmtiles", { create: true });
  const store = createTestStore({ storageManager, archive: new Uint8Array([1, 2, 3]) });
  const scan = await store.scanInstalledPacks();
  equal(scan.packs.length, 0, "partial omitted");
  equal(scan.partial_pack_ids[0], "partial-pack", "partial reported");
  await store.installPack("https://packs.test/marly/manifest.json");
  await rejectsCode(
    () => store.installPack("https://packs.test/marly/manifest.json"),
    "map_pack_already_installed",
  );
}

async function scenarioInterruptedInstall() {
  const storageManager = createMemoryStorageManager();
  const controller = new AbortController();
  const archive = new Uint8Array([1, 2, 3, 4, 5, 6]);
  const store = createTestStore({ storageManager, archive, archiveChunks: 3 });
  await rejectsCode(
    () => store.installPack("https://packs.test/marly/manifest.json", {
      signal: controller.signal,
      onProgress: () => controller.abort(),
    }),
    "map_pack_download_cancelled",
  );
  const scan = await store.scanInstalledPacks();
  equal(scan.packs.length, 0, "cancelled pack absent");
  equal(scan.partial_pack_ids.length, 0, "owned partial cleaned");
}

async function scenarioRegionalIntegrity() {
  const archive = new Uint8Array([1, 2, 3, 4, 5]);
  const digest = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", archive)), (byte) => byte.toString(16).padStart(2, "0")).join("");
  const expectedArchive = { byte_size: archive.length, sha256: digest };
  const store = createTestStore({ storageManager: createMemoryStorageManager(), archive });
  await store.installPack("https://packs.test/marly/manifest.json", {
    expectedArchive,
    onProgress: () => { expectedArchive.sha256 = "0".repeat(64); },
  });
  equal((await store.listInstalledPacks()).length, 1, "verified map installed with captured descriptor");
}

async function scenarioRegionalCorruption() {
  const archive = new Uint8Array([1, 2, 3, 4, 5]), fetchLog = [];
  const store = createTestStore({ storageManager: createMemoryStorageManager(), archive, fetchLog });
  await rejectsCode(() => store.installPack("https://packs.test/marly/manifest.json", {
    expectedArchive: { byte_size: archive.length, sha256: "0".repeat(64) },
  }), "regional_checksum_mismatch");
  const scan = await store.scanInstalledPacks();
  equal(scan.packs.length, 0, "mismatching bytes never active");
  equal(scan.partial_pack_ids.length, 0, "failed owned directory removed");
  equal(fetchLog.length, 2, "one manifest and archive request, no retry");
}

async function scenarioRegionalDescriptorFailure() {
  const archive = new Uint8Array([1, 2, 3]), fetchLog = [];
  const store = createTestStore({ storageManager: createMemoryStorageManager(), archive, fetchLog });
  await rejectsCode(() => store.installPack("https://packs.test/marly/manifest.json", {
    expectedArchive: { byte_size: archive.length, sha256: "invalid" },
  }), "invalid_regional_file");
  equal(fetchLog.length, 0, "invalid identity does not fetch");
  await rejectsCode(() => store.installPack("https://packs.test/marly/manifest.json", {
    expectedArchive: { byte_size: archive.length + 1, sha256: "0".repeat(64) },
  }), "regional_size_mismatch");
  equal(fetchLog.length, 1, "cross-manifest size mismatch never downloads archive");
  equal((await store.listInstalledPacks()).length, 0, "no partial activation");
}

function scenarioInstallUrlSecurity() {
  const production = { href: "https://app.test/" };
  equal(validateMapPackInstallUrl("https://packs.test/manifest.json", production).protocol, "https:", "HTTPS accepted");
  equal(
    validateMapPackInstallUrl("http://192.168.1.20/map/manifest.json", { href: "http://192.168.1.10:8000/" }).protocol,
    "http:",
    "private debug HTTP accepted",
  );
  for (const url of [
    "http://packs.test/manifest.json",
    "file:///tmp/manifest.json",
    "data:application/json,{}",
    "javascript:alert(1)",
    "https://user:pass@packs.test/manifest.json",
    "https://packs.test/manifest.json?token=secret",
    "https://packs.test/manifest.json#fragment",
  ]) throws(() => validateMapPackInstallUrl(url, production));
}

async function scenarioCoveringPackBootstrap() {
  const marly = parseMapPackManifest(manifest("marly-map-dev-v1", MARLY_BOUNDS, 4));
  const runtime = await initializeOfflineMaps({
    store: mapStoreStub([marly]),
    maplibregl: protocolStub(),
    browserWindow: eventTargetStub(),
  });
  const config = onlineConfig();
  const bootstrap = offlineMapBootstrapForConfig(config);
  equal(bootstrap.covering_local_pack, true, "covering pack known before map creation");
  equal(bootstrap.pack_id, marly.pack_id, "deterministic bootstrap selection");
  const style = initialMapStyle(config);
  assert(!Object.hasOwn(style.sources, "osm"), "initial style omits online source");
  assert(!style.layers.some((layer) => layer.id === "osm"), "initial style omits online layer");
  assert(
    !JSON.stringify(style).includes("tile.openstreetmap.org"),
    "initial style cannot initiate an OSM request",
  );
  const map = createFakeMap({ lon: 2.09, lat: 48.88 }, style);
  await runtime.attachMap(map, config);
  equal(runtime.snapshot().status.state, "local_pack_active", "local pack activates");
  assert(!map.sources.has("osm"), "online source remains absent after local activation");
}

async function scenarioBootstrapFallbackMatrix() {
  const noPackRuntime = createOfflineMapRuntime({
    store: mapStoreStub([]),
    maplibregl: protocolStub(),
    browserWindow: eventTargetStub(),
  });
  await noPackRuntime.initialize();
  const online = onlineConfig();
  const noPackStyle = initialMapStyle(online, noPackRuntime.bootstrapForConfig(online));
  assert(Object.hasOwn(noPackStyle.sources, "osm"), "online no-pack source retained");
  assert(noPackStyle.layers.some((layer) => layer.id === "osm"), "online no-pack layer retained");

  const marly = parseMapPackManifest(manifest("marly-map-dev-v1", MARLY_BOUNDS, 4));
  const nonCoveringRuntime = createOfflineMapRuntime({
    store: mapStoreStub([marly]),
    maplibregl: protocolStub(),
    browserWindow: eventTargetStub(),
  });
  await nonCoveringRuntime.initialize();
  const outside = onlineConfig([7, 46]);
  const outsideBootstrap = nonCoveringRuntime.bootstrapForConfig(outside);
  equal(outsideBootstrap.covering_local_pack, false, "non-covering pack not selected");
  const outsideStyle = initialMapStyle(outside, outsideBootstrap);
  assert(Object.hasOwn(outsideStyle.sources, "osm"), "non-covering online source retained");

  const offline = { ...online, offline_mode: true };
  const offlineStyle = initialMapStyle(offline, noPackRuntime.bootstrapForConfig(offline));
  equal(Object.keys(offlineStyle.sources).length, 0, "offline no-pack source remains neutral");
  equal(offlineStyle.layers.length, 1, "offline no-pack style has only its background");
  equal(offlineStyle.layers[0].id, "offline-background", "neutral background retained");
}

async function scenarioFailedLocalOpenFallback() {
  const marly = parseMapPackManifest(manifest("marly-map-dev-v1", MARLY_BOUNDS, 4));
  const failingStore = {
    ...mapStoreStub([marly]),
    openPackSource: async () => { throw new Error("fixture open failure"); },
  };
  const runtime = createOfflineMapRuntime({
    store: failingStore,
    maplibregl: protocolStub(),
    browserWindow: eventTargetStub(),
  });
  await runtime.initialize();

  const online = onlineConfig();
  const bootstrap = runtime.bootstrapForConfig(online);
  const onlineMap = createFakeMap(
    { lon: 2.09, lat: 48.88 },
    initialMapStyle(online, bootstrap),
  );
  assert(!onlineMap.sources.has("osm"), "selected pack suppresses initial online source");
  await runtime.attachMap(onlineMap, online);
  equal(runtime.snapshot().status.state, "map_pack_invalid", "failed pack is explicit");
  assert(onlineMap.sources.has("osm"), "online raster added only after open failure");

  const offline = { ...online, offline_mode: true };
  const offlineMap = createFakeMap(
    { lon: 2.09, lat: 48.88 },
    initialMapStyle(offline, runtime.bootstrapForConfig(offline)),
  );
  await runtime.attachMap(offlineMap, offline);
  equal(runtime.snapshot().status.state, "map_pack_invalid", "offline failure remains explicit");
  assert(!offlineMap.sources.has("osm"), "offline open failure remains neutral");
}

async function scenarioLocalMapIntegration() {
  const marly = parseMapPackManifest(manifest("marly-map-dev-v1", MARLY_BOUNDS, 4));
  const store = mapStoreStub([marly]);
  const map = createFakeMap({ lon: 2.09, lat: 48.88 });
  const maplibregl = protocolStub();
  const runtime = createOfflineMapRuntime({ store, maplibregl, browserWindow: eventTargetStub() });
  await runtime.initialize();
  await runtime.attachMap(map, offlineConfig());
  equal(runtime.snapshot().status.state, "local_pack_active", "local pack active");
  equal(runtime.snapshot().active_pack_id, marly.pack_id, "active identity");
  equal(runtime.snapshot().active_source_diagnostics.read_count, 0, "read diagnostics exposed");
  const source = map.sources.get("sugarglider-local-map-pack");
  assert(source.url.startsWith("pmtiles://sugarglider-map-pack/"), "PMTiles protocol source");
  assert(source.attribution.includes("OpenStreetMap"), "visible attribution");
  assert(!map.sources.has("osm"), "remote raster removed");
  assert(map.layers.some((layer) => layer.id.includes("roads_minor")), "road/path-capable layers present");
  assert(
    map.layers
      .filter((layer) => layer.id.startsWith("sugarglider-local-map-pack-"))
      .every((layer) => layer.type !== "background"),
    "vector source is never attached to a background layer",
  );
}

async function scenarioNoPackOfflineAndOnline() {
  const offlineMap = createFakeMap({ lon: 7, lat: 46 });
  const offlineRuntime = createOfflineMapRuntime({
    store: mapStoreStub([]),
    maplibregl: protocolStub(),
    browserWindow: eventTargetStub(),
  });
  await offlineRuntime.initialize();
  await offlineRuntime.attachMap(offlineMap, offlineConfig());
  equal(offlineRuntime.snapshot().status.state, "no_covering_map_pack", "truthful offline state");
  assert(offlineMap.layers.some((layer) => layer.id === "offline-background"), "neutral background retained");
  assert(!offlineMap.sources.has("osm"), "offline does not attempt raster source");

  const onlineMap = createFakeMap({ lon: 7, lat: 46 });
  const onlineRuntime = createOfflineMapRuntime({
    store: mapStoreStub([]),
    maplibregl: protocolStub(),
    browserWindow: eventTargetStub(),
  });
  await onlineRuntime.initialize();
  await onlineRuntime.attachMap(onlineMap, { ...offlineConfig(), offline_mode: false });
  equal(onlineRuntime.snapshot().status.state, "online_map_active", "online fallback explicit");
  assert(onlineMap.sources.has("osm"), "configured online raster remains available");
}

async function scenarioRegionSwitch() {
  const marly = parseMapPackManifest(manifest("marly-map-dev-v1", MARLY_BOUNDS, 4));
  const paris = parseMapPackManifest(manifest("paris-map-dev-v1", PARIS_BOUNDS, 4));
  const map = createFakeMap({ lon: 2.09, lat: 48.88 });
  const overlays = [
    "planner-required-points",
    "local-routing-experiment-line",
    "local-auto-tour-experiment-line",
    "planner-current-location-avatar",
  ];
  for (const id of overlays) map.layers.push({ id, type: "line" });
  const runtime = createOfflineMapRuntime({
    store: mapStoreStub([paris, marly]),
    maplibregl: protocolStub(),
    browserWindow: eventTargetStub(),
  });
  await runtime.initialize();
  await runtime.attachMap(map, offlineConfig());
  equal(runtime.snapshot().active_pack_id, marly.pack_id, "Marly initially selected");
  await runtime.applyForCoordinate({ lon: 2.33, lat: 48.86 });
  equal(runtime.snapshot().active_pack_id, paris.pack_id, "Paris selected after region switch");
  equal(map.sources.size, 1, "single local vector source retained");
  for (const id of overlays) assert(map.layers.some((layer) => layer.id === id), `${id} survives`);
  assert(map.events.includes("remove-source:sugarglider-local-map-pack"), "old source removed");
}

function scenarioNoRemoteStyleAssets() {
  const source = document.documentElement.outerHTML;
  assert(!source.includes("unpkg.com"), "no runtime CDN");
  assert(!source.includes("protomaps.github.io/basemaps-assets"), "no remote style assets");
}

function createTestStore({ storageManager, archive, fetchLog = [], archiveChunks = 1 }) {
  const pack = manifest("marly-map-dev-v1", MARLY_BOUNDS, archive.length);
  const manifestUrl = "https://packs.test/marly/manifest.json";
  const archiveUrl = "https://packs.test/marly/basemap.pmtiles";
  const fetchRequest = async (url, options) => {
    fetchLog.push({ url, options });
    if (url === manifestUrl) return new Response(JSON.stringify(pack));
    if (url === archiveUrl) {
      return new Response(chunkedStream(archive, archiveChunks), {
        headers: { "Content-Length": String(archive.length) },
      });
    }
    return new Response("missing", { status: 404 });
  };
  return new MapPackStore({
    storageManager,
    fetchRequest,
    pageLocation: { href: "https://app.test/" },
    probeSuffix: "test",
    archiveValidator: async ({ source }) => ({
      archive: { source },
      header: { specVersion: 3 },
      metadata: { vector_layers: [] },
    }),
  });
}

function mapStoreStub(packs) {
  const sorted = [...packs].sort((left, right) => (
    left.pack_id < right.pack_id ? -1 : left.pack_id > right.pack_id ? 1 : 0
  ));
  return {
    capabilities: async () => ({ opfs_supported: true, random_access: true, persisted: true }),
    scanInstalledPacks: async () => ({
      packs: sorted,
      partial_pack_ids: [],
      invalid_pack_ids: [],
    }),
    openPackSource: async (packId) => {
      const selected = sorted.find((pack) => pack.pack_id === packId);
      const source = {
        getKey: () => `sugarglider-map-pack/${selected.pack_id}/${selected.build_id}`,
        diagnostics: () => ({ read_count: 0, bytes_read: 0 }),
      };
      return {
        manifest: selected,
        source,
        archive: { source },
      };
    },
    requestPersistence: async () => true,
    cancelActiveInstalls() {},
  };
}

function protocolStub() {
  const registrations = [];
  return {
    registrations,
    addProtocol(name, handler) {
      registrations.push({ name, handler });
    },
  };
}

function eventTargetStub() {
  return { addEventListener() {} };
}

function createFakeMap(center, style = null) {
  const sources = new Map(Object.entries(style?.sources ?? { osm: { type: "raster" } }));
  const layers = (style?.layers ?? [
    { id: "offline-background", type: "background" },
    { id: "osm", type: "raster", source: "osm" },
  ]).map((layer) => ({ ...layer }));
  const events = [];
  return {
    sources,
    layers,
    events,
    getCenter: () => ({ lng: center.lon, lat: center.lat }),
    on() {},
    off() {},
    getStyle: () => ({ layers, sources: Object.fromEntries(sources) }),
    getLayer: (id) => layers.find((layer) => layer.id === id),
    getSource: (id) => sources.get(id),
    addSource(id, source) {
      sources.set(id, source);
      events.push(`add-source:${id}`);
    },
    removeSource(id) {
      sources.delete(id);
      events.push(`remove-source:${id}`);
    },
    addLayer(layer, beforeId) {
      const index = beforeId ? layers.findIndex((candidate) => candidate.id === beforeId) : -1;
      if (index < 0) layers.push(layer);
      else layers.splice(index, 0, layer);
      events.push(`add-layer:${layer.id}`);
    },
    removeLayer(id) {
      const index = layers.findIndex((layer) => layer.id === id);
      if (index >= 0) layers.splice(index, 1);
      events.push(`remove-layer:${id}`);
    },
  };
}

function offlineConfig() {
  return {
    offline_mode: true,
    initial_center: [2.09, 48.88],
    tile_url_template: "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    tile_attribution: "© OpenStreetMap contributors",
  };
}

function onlineConfig(initialCenter = [2.09, 48.88]) {
  return {
    ...offlineConfig(),
    offline_mode: false,
    initial_center: initialCenter,
  };
}

export function manifest(packId, bounds, byteSize) {
  return {
    schema_version: 1,
    pack_id: packId,
    display_name: packId,
    bounds,
    min_zoom: 0,
    max_zoom: 14,
    format: "pmtiles-v3",
    tile_type: "mvt",
    archive_filename: "basemap.pmtiles",
    byte_size: byteSize,
    attribution: "© OpenStreetMap contributors · Protomaps",
    data_source: "OpenStreetMap-derived / Protomaps Basemaps",
    build_id: "fixture-build-v1",
  };
}

export function tinyPmtiles(bounds, minZoom, maxZoom) {
  const metadata = new TextEncoder().encode(JSON.stringify({
    vector_layers: REQUIRED_LAYER_IDS.map((id) => ({ id })),
  }));
  const metadataOffset = 128;
  const total = metadataOffset + metadata.length;
  const bytes = new Uint8Array(total);
  bytes.set(new TextEncoder().encode("PMTiles"), 0);
  bytes[7] = 3;
  const view = new DataView(bytes.buffer);
  setUint64(view, 8, 127);
  setUint64(view, 16, 1);
  setUint64(view, 24, metadataOffset);
  setUint64(view, 32, metadata.length);
  setUint64(view, 40, total);
  setUint64(view, 48, 0);
  setUint64(view, 56, total);
  setUint64(view, 64, 0);
  bytes[96] = 1;
  bytes[97] = 1;
  bytes[98] = 1;
  bytes[99] = 1;
  bytes[100] = minZoom;
  bytes[101] = maxZoom;
  view.setInt32(102, Math.round(bounds[0] * 10_000_000), true);
  view.setInt32(106, Math.round(bounds[1] * 10_000_000), true);
  view.setInt32(110, Math.round(bounds[2] * 10_000_000), true);
  view.setInt32(114, Math.round(bounds[3] * 10_000_000), true);
  bytes[118] = 10;
  view.setInt32(119, Math.round(((bounds[0] + bounds[2]) / 2) * 10_000_000), true);
  view.setInt32(123, Math.round(((bounds[1] + bounds[3]) / 2) * 10_000_000), true);
  bytes[127] = 0;
  bytes.set(metadata, metadataOffset);
  return bytes;
}

function setUint64(view, offset, value) {
  view.setUint32(offset, value, true);
  view.setUint32(offset + 4, 0, true);
}

function chunkedStream(bytes, chunkCount) {
  const chunkSize = Math.ceil(bytes.length / chunkCount);
  let offset = 0;
  return new ReadableStream({
    pull(controller) {
      if (offset >= bytes.length) {
        controller.close();
        return;
      }
      const end = Math.min(bytes.length, offset + chunkSize);
      controller.enqueue(bytes.slice(offset, end));
      offset = end;
    },
  });
}

function createMemoryStorageManager() {
  const root = new MemoryDirectoryHandle("root");
  return {
    root,
    getDirectory: async () => root,
    persisted: async () => true,
    persist: async () => true,
  };
}

class MemoryDirectoryHandle {
  constructor(name) {
    this.kind = "directory";
    this.name = name;
    this.children = new Map();
  }

  async getDirectoryHandle(name, options = {}) {
    const existing = this.children.get(name);
    if (existing?.kind === "directory") return existing;
    if (existing || !options.create) throw notFound();
    const directory = new MemoryDirectoryHandle(name);
    this.children.set(name, directory);
    return directory;
  }

  async getFileHandle(name, options = {}) {
    const existing = this.children.get(name);
    if (existing?.kind === "file") return existing;
    if (existing || !options.create) throw notFound();
    const file = new MemoryFileHandle(name, new Uint8Array());
    this.children.set(name, file);
    return file;
  }

  async removeEntry(name, options = {}) {
    const existing = this.children.get(name);
    if (!existing) throw notFound();
    if (existing.kind === "directory" && existing.children.size && !options.recursive) {
      throw new DOMException("Directory is not empty.", "InvalidModificationError");
    }
    this.children.delete(name);
  }

  async *entries() {
    for (const entry of this.children.entries()) yield entry;
  }
}

class MemoryFileHandle {
  constructor(name, bytes) {
    this.kind = "file";
    this.name = name;
    this.bytes = bytes;
  }

  async getFile() {
    return new File([this.bytes], this.name);
  }

  async createWritable() {
    const chunks = [];
    return {
      write: async (value) => {
        if (typeof value === "string") chunks.push(new TextEncoder().encode(value));
        else if (value instanceof Uint8Array) chunks.push(value.slice());
        else if (value instanceof ArrayBuffer) chunks.push(new Uint8Array(value.slice(0)));
        else throw new Error("Unsupported fake write");
      },
      close: async () => {
        const size = chunks.reduce((total, chunk) => total + chunk.length, 0);
        const combined = new Uint8Array(size);
        let offset = 0;
        for (const chunk of chunks) {
          combined.set(chunk, offset);
          offset += chunk.length;
        }
        this.bytes = combined;
      },
      abort: async () => {},
    };
  }
}

function notFound() {
  return new DOMException("Entry not found.", "NotFoundError");
}

function bytesEqual(actual, expected, message) {
  equal([...actual].join(","), expected.join(","), message);
}

async function rejects(action, message) {
  try {
    await action();
  } catch {
    return;
  }
  throw new Error(`Expected rejection: ${message}`);
}

async function rejectsCode(action, code) {
  try {
    await action();
  } catch (error) {
    equal(error.code, code, "rejection code");
    return;
  }
  throw new Error(`Expected rejection code ${code}`);
}

function throws(action, ErrorType = Error) {
  try {
    action();
  } catch (error) {
    assert(error instanceof ErrorType, "expected error type");
    return;
  }
  throw new Error("Expected synchronous rejection");
}

function equal(actual, expected, message) {
  if (actual !== expected) throw new Error(`${message}: ${actual} !== ${expected}`);
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}
