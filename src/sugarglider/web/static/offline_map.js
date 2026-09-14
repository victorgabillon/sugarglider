import * as packagedMapLibre from "./vendor/maplibre-gl-6.4.1/maplibre-gl.mjs";
import {
  createMapPackStore,
} from "./map_pack_store.js";
import {
  selectMapPackForCoordinate,
} from "./map_pack_manifest.js";
import {
  layers as protomapsLayers,
  namedFlavor,
} from "./vendor/protomaps-basemaps-5.7.2/basemaps.js";

const LOCAL_SOURCE_ID = "sugarglider-local-map-pack";
const LOCAL_LAYER_PREFIX = "sugarglider-local-map-pack-";
const ONLINE_SOURCE_ID = "osm";
const ONLINE_LAYER_ID = "osm";
const NEUTRAL_BACKGROUND_LAYER_ID = "offline-background";

let sharedRuntime = null;

export async function initializeOfflineMaps(options = {}) {
  if (!sharedRuntime) sharedRuntime = createOfflineMapRuntime(options);
  await sharedRuntime.initialize();
  return sharedRuntime;
}

export async function attachOfflineBasemap(map, config) {
  if (!sharedRuntime) return null;
  return sharedRuntime.attachMap(map, config);
}

export function detachOfflineBasemap(map) {
  sharedRuntime?.detachMap(map);
}

export function offlineMapSnapshot() {
  return sharedRuntime?.snapshot() ?? null;
}

export function offlineMapBootstrapForConfig(config) {
  return sharedRuntime?.bootstrapForConfig(config) ?? emptyBootstrap();
}

export function createOfflineMapRuntime({
  store = createMapPackStore(),
  maplibregl = packagedMapLibre,
  browserWindow = globalThis.window,
  elements = {},
  confirmRemoval = (message) => globalThis.confirm?.(message) ?? false,
  onStatus = () => {},
} = {}) {
  let initialized = false;
  let capability = null;
  let scan = emptyScan();
  let protocol = null;
  let protocolAvailable = false;
  let currentMap = null;
  let mapConfig = null;
  let activePack = null;
  let activeSource = null;
  let mapEpoch = 0;
  let installEpoch = 0;
  let installController = null;
  let networkAvailable = globalThis.navigator?.onLine !== false;
  let moveHandler = null;
  let status = Object.freeze({ state: "map_pack_initializing", message: "Checking offline map storage…" });

  async function initialize() {
    if (initialized) return snapshot();
    initialized = true;
    capability = await store.capabilities();
    if (capability.opfs_supported) {
      try {
        scan = await store.scanInstalledPacks();
      } catch (error) {
        capability = Object.freeze({
          opfs_supported: false,
          random_access: false,
          state: "map_pack_storage_unavailable",
          persisted: null,
          reason: safeErrorMessage(error),
        });
      }
    }
    protocolAvailable = installProtocol();
    bindUi();
    bindNetworkHints();
    if (!capability.opfs_supported) {
      setStatus("map_pack_storage_unavailable", "Offline map storage is unavailable in this browser.");
    } else if (!protocolAvailable) {
      setStatus("map_pack_invalid", "The packaged PMTiles map runtime is unavailable.");
    } else if (scan.invalid_pack_ids.length) {
      setStatus("map_pack_invalid", "One or more stored map packs are invalid and will not be used.");
    } else if (scan.partial_pack_ids.length) {
      setStatus("map_pack_partial", "One or more incomplete map-pack installs were ignored.");
    } else if (scan.packs.length) {
      setStatus("map_pack_ready", `${scan.packs.length} offline map pack${scan.packs.length === 1 ? " is" : "s are"} installed.`);
    } else {
      setStatus("no_map_packs_installed", "No offline map packs are installed.");
    }
    render();
    return snapshot();
  }

  async function attachMap(map, config) {
    detachMap(currentMap);
    currentMap = map;
    mapConfig = config;
    activePack = null;
    activeSource = null;
    const epoch = ++mapEpoch;
    moveHandler = () => {
      mapEpoch += 1;
      void applyForCurrentCenter();
    };
    map.on?.("moveend", moveHandler);
    await applyForCurrentCenter(epoch);
    return snapshot();
  }

  function bootstrapForConfig(config) {
    if (!initialized || !capability?.opfs_supported || !protocolAvailable) {
      return emptyBootstrap();
    }
    const center = config?.initial_center;
    if (!Array.isArray(center) || center.length !== 2) return emptyBootstrap();
    const selected = selectMapPackForCoordinate(scan.packs, {
      lon: center[0],
      lat: center[1],
    });
    return Object.freeze({
      covering_local_pack: Boolean(selected),
      pack_id: selected?.pack_id ?? null,
      build_id: selected?.build_id ?? null,
    });
  }

  function detachMap(map) {
    if (!map || map !== currentMap) return;
    if (moveHandler) map.off?.("moveend", moveHandler);
    currentMap = null;
    mapConfig = null;
    activePack = null;
    activeSource = null;
    moveHandler = null;
    mapEpoch += 1;
    render();
  }

  async function applyForCurrentCenter(expectedEpoch = mapEpoch) {
    if (!currentMap || expectedEpoch !== mapEpoch) return null;
    const center = currentMap.getCenter?.();
    const initial = mapConfig?.initial_center ?? [0, 0];
    const coordinate = center
      ? { lon: center.lng, lat: center.lat }
      : { lon: initial[0], lat: initial[1] };
    return applyForCoordinate(coordinate, expectedEpoch);
  }

  async function applyForCoordinate(coordinate, expectedEpoch = ++mapEpoch) {
    if (!currentMap) return null;
    if (expectedEpoch !== mapEpoch) return null;
    const selected = selectMapPackForCoordinate(scan.packs, coordinate);
    if (selected && !protocolAvailable) {
      activePack = null;
      activeSource = null;
      removeLocalBasemap(currentMap);
      if (offlineMode()) removeOnlineBasemap(currentMap);
      else ensureOnlineBasemap(currentMap, mapConfig);
      setStatus("map_pack_invalid", "The packaged PMTiles map runtime is unavailable.");
      render();
      return null;
    }
    if (selected && protocolAvailable) {
      if (
        activePack?.pack_id === selected.pack_id
        && activePack?.build_id === selected.build_id
      ) {
        setStatus("local_pack_active", `Offline map pack active: ${selected.display_name}.`);
        return selected;
      }
      try {
        const opened = await store.openPackSource(selected.pack_id);
        if (!currentMap || expectedEpoch !== mapEpoch) return null;
        protocol.add(opened.archive);
        installLocalBasemap(currentMap, opened);
        activePack = opened.manifest;
        activeSource = opened.source;
        setStatus("local_pack_active", `Offline map pack active: ${opened.manifest.display_name}.`);
        render();
        return opened.manifest;
      } catch {
        if (!currentMap || expectedEpoch !== mapEpoch) return null;
        activePack = null;
        activeSource = null;
        removeLocalBasemap(currentMap);
        if (offlineMode()) removeOnlineBasemap(currentMap);
        else ensureOnlineBasemap(currentMap, mapConfig);
        setStatus("map_pack_invalid", `Installed map pack ${selected.pack_id} is invalid.`);
        render();
        return null;
      }
    }
    activePack = null;
    activeSource = null;
    removeLocalBasemap(currentMap);
    if (offlineMode()) {
      removeOnlineBasemap(currentMap);
      setStatus("no_covering_map_pack", "Offline: no installed map pack covers the current map center.");
    } else {
      ensureOnlineBasemap(currentMap, mapConfig);
      setStatus("online_map_active", "Online raster map active; no covering local pack is installed.");
    }
    render();
    return null;
  }

  async function refresh({ reopen = false } = {}) {
    if (!capability?.opfs_supported) return snapshot();
    scan = await store.scanInstalledPacks();
    if (reopen) { activePack = null; activeSource = null; }
    mapEpoch += 1;
    if (currentMap) await applyForCurrentCenter();
    else if (scan.invalid_pack_ids.length) {
      setStatus("map_pack_invalid", "One or more stored map packs are invalid and will not be used.");
    } else if (scan.partial_pack_ids.length) {
      setStatus("map_pack_partial", "One or more incomplete map-pack installs were ignored.");
    } else if (!scan.packs.length) {
      setStatus("no_map_packs_installed", "No offline map packs are installed.");
    }
    render();
    return snapshot();
  }

  async function install(manifestUrl) {
    const epoch = ++installEpoch;
    installController?.abort();
    installController = new AbortController();
    setBusy(true);
    setStatus("map_pack_installing", "Downloading map pack…");
    try {
      const persistence = await store.requestPersistence();
      if (epoch !== installEpoch) return null;
      const installed = await store.installPack(manifestUrl, {
        signal: installController.signal,
        onProgress: ({ bytes_written, byte_size }) => {
          if (epoch !== installEpoch) return;
          setStatus(
            "map_pack_installing",
            `Downloading map pack: ${formatBytes(bytes_written)} of ${formatBytes(byte_size)}.`,
          );
          render();
        },
      });
      if (epoch !== installEpoch) return null;
      scan = await store.scanInstalledPacks();
      setStatus(
        "map_pack_installed",
        `${installed.display_name} installed${persistence === true ? " in persistent storage" : ""}.`,
      );
      mapEpoch += 1;
      if (currentMap) await applyForCurrentCenter();
      return installed;
    } catch (error) {
      if (epoch !== installEpoch) return null;
      const cancelled = error?.code === "map_pack_download_cancelled";
      setStatus(
        cancelled ? "map_pack_install_cancelled" : (error?.code ?? "map_pack_install_failed"),
        cancelled ? "Map-pack installation cancelled." : safeErrorMessage(error),
      );
      return null;
    } finally {
      if (epoch === installEpoch) {
        installController = null;
        setBusy(false);
        render();
      }
    }
  }

  function cancelInstall() {
    installEpoch += 1;
    installController?.abort();
    store.cancelActiveInstalls();
    installController = null;
    setBusy(false);
    setStatus("map_pack_install_cancelled", "Map-pack installation cancelled.");
    render();
  }

  async function remove(packId) {
    if (!confirmRemoval(`Remove offline map pack ${packId}?`)) return false;
    installEpoch += 1;
    try {
      await store.removePack(packId);
      scan = await store.scanInstalledPacks();
      setStatus("map_pack_removed", `Offline map pack ${packId} removed.`);
      mapEpoch += 1;
      if (currentMap) await applyForCurrentCenter();
      render();
      return true;
    } catch (error) {
      setStatus("map_pack_remove_failed", safeErrorMessage(error));
      render();
      return false;
    }
  }

  function installProtocol() {
    const Protocol = globalThis.pmtiles?.Protocol;
    if (typeof Protocol !== "function" || typeof maplibregl?.addProtocol !== "function") return false;
    try {
      protocol = new Protocol();
      maplibregl.addProtocol("pmtiles", protocol.tile);
      return true;
    } catch {
      protocol = null;
      return false;
    }
  }

  function bindNetworkHints() {
    browserWindow?.addEventListener?.("offline", () => {
      networkAvailable = false;
      mapEpoch += 1;
      void applyForCurrentCenter();
    });
    browserWindow?.addEventListener?.("online", () => {
      networkAvailable = true;
      mapEpoch += 1;
      void applyForCurrentCenter();
    });
  }

  function bindUi() {
    elements.form?.addEventListener("submit", (event) => {
      event.preventDefault();
      void install(elements.urlInput?.value ?? "");
    });
    elements.cancelButton?.addEventListener("click", cancelInstall);
  }

  function render() {
    try { onStatus(snapshot()); } catch { /* Presentation must not change map availability. */ }
    if (elements.support) {
      elements.support.textContent = capability?.opfs_supported
        ? `OPFS random-access storage supported${capability.persisted === true ? " and persisted" : ""}.`
        : "OPFS random-access storage unavailable.";
    }
    if (elements.status) {
      elements.status.dataset.state = status.state;
      elements.status.textContent = status.message;
    }
    if (elements.active) {
      elements.active.textContent = activePack
        ? `Active local pack: ${activePack.display_name} (${activePack.pack_id}). ${activePack.attribution}`
        : "No local map pack is active.";
    }
    if (elements.form) {
      for (const control of elements.form.elements ?? []) {
        control.disabled = !capability?.opfs_supported || Boolean(installController);
      }
    }
    if (elements.cancelButton) elements.cancelButton.classList.toggle("hidden", !installController);
    if (!elements.list) return;
    elements.list.replaceChildren();
    for (const pack of scan.packs) {
      const item = document.createElement("li");
      const title = document.createElement("strong");
      title.textContent = `${pack.display_name} · ${formatBytes(pack.byte_size)}`;
      const details = document.createElement("span");
      details.textContent = `${pack.pack_id} · ${pack.bounds.join(", ")} · zoom ${pack.min_zoom}–${pack.max_zoom}`;
      const attribution = document.createElement("small");
      attribution.textContent = pack.attribution;
      const button = document.createElement("button");
      button.type = "button";
      button.className = "text-button danger";
      button.textContent = "Remove";
      button.addEventListener("click", () => {
        void remove(pack.pack_id);
      });
      item.append(title, details, attribution, button);
      elements.list.append(item);
    }
    for (const [packIds, label] of [
      [scan.invalid_pack_ids, "Invalid stored pack"],
      [scan.partial_pack_ids, "Incomplete install"],
    ]) {
      for (const packId of packIds) {
        const item = document.createElement("li");
        const title = document.createElement("strong");
        title.textContent = `${label}: ${packId}`;
        const button = document.createElement("button");
        button.type = "button";
        button.className = "text-button danger";
        button.textContent = "Remove";
        button.addEventListener("click", () => {
          void remove(packId);
        });
        item.append(title, button);
        elements.list.append(item);
      }
    }
  }

  function setStatus(state, message) {
    status = Object.freeze({ state, message });
  }

  function setBusy(busy) {
    elements.installButton?.setAttribute("aria-busy", String(busy));
  }

  function offlineMode() {
    return Boolean(mapConfig?.offline_mode) || !networkAvailable;
  }

  function snapshot() {
    return Object.freeze({
      capability,
      packs: scan.packs,
      partial_pack_ids: scan.partial_pack_ids,
      invalid_pack_ids: scan.invalid_pack_ids,
      active_pack_id: activePack?.pack_id ?? null,
      active_source_diagnostics: activeSource?.diagnostics?.() ?? null,
      status,
      protocol_available: protocolAvailable,
    });
  }

  return Object.freeze({
    initialize,
    bootstrapForConfig,
    attachMap,
    detachMap,
    applyForCoordinate,
    refresh,
    install,
    cancelInstall,
    remove,
    snapshot,
  });
}

function installLocalBasemap(map, opened) {
  removeLocalBasemap(map);
  const manifest = opened.manifest;
  map.addSource(LOCAL_SOURCE_ID, {
    type: "vector",
    url: `pmtiles://${opened.source.getKey()}`,
    attribution: escapeAttribution(manifest.attribution),
    bounds: manifest.bounds,
    minzoom: manifest.min_zoom,
    maxzoom: manifest.max_zoom,
  });
  const beforeId = firstOverlayLayerId(map);
  for (const original of protomapsLayers(LOCAL_SOURCE_ID, namedFlavor("light"))) {
    if (original.type === "symbol" || original.type === "background") continue;
    const layer = {
      ...original,
      id: `${LOCAL_LAYER_PREFIX}${original.id}`,
      source: LOCAL_SOURCE_ID,
    };
    map.addLayer(layer, beforeId);
  }
  removeOnlineBasemap(map);
}

function removeLocalBasemap(map) {
  for (const layer of [...(map.getStyle?.()?.layers ?? [])].reverse()) {
    if (layer.id.startsWith(LOCAL_LAYER_PREFIX) && map.getLayer?.(layer.id)) {
      map.removeLayer(layer.id);
    }
  }
  if (map.getSource?.(LOCAL_SOURCE_ID)) map.removeSource(LOCAL_SOURCE_ID);
}

function removeOnlineBasemap(map) {
  if (map.getLayer?.(ONLINE_LAYER_ID)) map.removeLayer(ONLINE_LAYER_ID);
  if (map.getSource?.(ONLINE_SOURCE_ID)) map.removeSource(ONLINE_SOURCE_ID);
}

function ensureOnlineBasemap(map, config) {
  if (!config?.tile_url_template || config.tile_url_template === "about:blank") return;
  if (!map.getSource?.(ONLINE_SOURCE_ID)) {
    map.addSource(ONLINE_SOURCE_ID, {
      type: "raster",
      tiles: [config.tile_url_template],
      tileSize: 256,
      attribution: config.tile_attribution,
    });
  }
  if (!map.getLayer?.(ONLINE_LAYER_ID)) {
    map.addLayer(
      { id: ONLINE_LAYER_ID, type: "raster", source: ONLINE_SOURCE_ID },
      firstOverlayLayerId(map),
    );
  }
}

function firstOverlayLayerId(map) {
  return (map.getStyle?.()?.layers ?? []).find((layer) => (
    layer.id !== NEUTRAL_BACKGROUND_LAYER_ID
    && layer.id !== ONLINE_LAYER_ID
    && !layer.id.startsWith(LOCAL_LAYER_PREFIX)
  ))?.id;
}

function escapeAttribution(value) {
  return value.replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function formatBytes(value) {
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KiB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MiB`;
}

function safeErrorMessage(error) {
  return typeof error?.message === "string" && error.message.length <= 240
    ? error.message
    : "Map-pack operation failed.";
}

function emptyScan() {
  return Object.freeze({
    packs: Object.freeze([]),
    partial_pack_ids: Object.freeze([]),
    invalid_pack_ids: Object.freeze([]),
  });
}

function emptyBootstrap() {
  return Object.freeze({
    covering_local_pack: false,
    pack_id: null,
    build_id: null,
  });
}
