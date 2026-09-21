import { RegionalDataError, freezeData } from "./regional_manifest.js";

export function createLocalRegionClient({
  worker = new Worker(new URL("./local_region_worker.js", import.meta.url), { type: "module" }),
} = {}) {
  let sequence = 0;
  let closed = false;
  const pending = new Map();
  worker.onmessage = ({ data }) => {
    const operation = pending.get(data.id);
    if (!operation) return;
    pending.delete(data.id);
    if (data.error) operation.reject(new RegionalDataError(data.error));
    else operation.resolve(freezeData(data.result));
  };
  worker.onerror = () => close();
  worker.onmessageerror = () => close();
  function request(type, value = {}) {
    if (closed) return Promise.reject(new RegionalDataError("regional_worker_unavailable"));
    if (pending.size >= 8) return Promise.reject(new RegionalDataError("regional_worker_busy"));
    const id = ++sequence;
    return new Promise((resolve, reject) => {
      pending.set(id, { resolve, reject });
      try { worker.postMessage({ id, type, value }); }
      catch { pending.delete(id); reject(new RegionalDataError("regional_worker_unavailable")); }
    });
  }
  function close() {
    closed = true;
    worker.terminate();
    for (const operation of pending.values()) operation.reject(new RegionalDataError("regional_worker_unavailable"));
    pending.clear();
  }
  async function load(regionId) {
    const identity = await request("load", { region_id: regionId });
    return session(identity);
  }
  async function loadVersion(manifest, directory) {
    const identity = await request("load_version", { manifest, directory });
    return session(identity);
  }
  function session(identity) {
    return Object.freeze({ identity,
      queryPois: (query) => request("query_pois", { build_id: identity.build_id, query }),
      searchPois: (query) => request("search_pois", { build_id: identity.build_id, query }),
      analyzeNature: (candidate) => request("analyze_nature", { build_id: identity.build_id,
        candidate: { geometry: candidate.geometry, distance_m: candidate.distance_m, pack_id: candidate.pack_id } }),
    });
  }
  return Object.freeze({
    list: () => request("list"),
    install: (url) => request("install", { url }),
    installVersion: (url, manifest, directory) => request("install_version", { url, manifest, directory }),
    cancelInstall: () => worker.postMessage({ type: "cancel_install" }),
    remove: (regionId) => request("remove", { region_id: regionId }),
    load, loadVersion, close,
  });
}
