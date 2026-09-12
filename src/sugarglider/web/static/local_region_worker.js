import { createLocalRegionStore, loadLocalRegionData } from "./local_region_store.js";
import { createVersionedRegionComponents } from "./region_components.js";

const store = createLocalRegionStore();
let data = null;
let pendingInstall = null;
let installGeneration = 0;
let queue = Promise.resolve();

self.onmessage = ({ data: message }) => {
  if (message.type === "cancel_install") { installGeneration += 1; pendingInstall?.abort(); return; }
  const ownedInstallGeneration = installGeneration;
  // Parsing/indexing/analysis is serialized in a worker and never blocks the map.
  queue = queue.then(async () => {
    try {
      let result;
      switch (message.type) {
        case "list": result = await store.list(); break;
        case "install": {
          if (ownedInstallGeneration !== installGeneration) throw new DOMException("Cancelled", "AbortError");
          pendingInstall = new AbortController();
          try { result = await store.install(message.value.url, { signal: pendingInstall.signal }); }
          finally { pendingInstall = null; }
          data = null;
          break;
        }
        case "install_version": {
          if (ownedInstallGeneration !== installGeneration) throw new DOMException("Cancelled", "AbortError");
          pendingInstall = new AbortController();
          try {
            const scoped = await createVersionedRegionComponents(message.value);
            await scoped.installIndexes(message.value.url, { signal: pendingInstall.signal });
            result = scoped.manifest;
          } finally { pendingInstall = null; }
          // Staging must not replace an already loaded committed analysis session.
          break;
        }
        case "remove":
          await store.remove(message.value.region_id);
          data = null;
          result = null;
          break;
        case "load": {
          const opened = await store.open(message.value.region_id);
          if (data?.identity.build_id !== opened.manifest.build_id) data = await loadLocalRegionData(opened);
          result = data.identity;
          break;
        }
        case "load_version": {
          // The caller owns the region lease while this directory is in use.
          // Do not reacquire its lock from this worker and deadlock the caller.
          const scoped = await createVersionedRegionComponents(message.value);
          if (data?.identity.build_id !== scoped.manifest.build_id) data = await scoped.openIndexes();
          else await scoped.verifyIndexes();
          result = data.identity;
          break;
        }
        case "query_pois":
        case "analyze_nature":
          if (!data || data.identity.build_id !== message.value.build_id) throw new Error("regional_data_changed");
          result = message.type === "query_pois" ? data.queryPois(message.value.query) : data.analyzeNature(message.value.candidate);
          break;
        default: throw new Error("invalid_regional_operation");
      }
      self.postMessage({ id: message.id, result });
    } catch (error) {
      // Never return URLs, local paths, coordinates or arbitrary exception text.
      const code = error.name === "AbortError" ? "regional_install_cancelled" : error.code ?? "regional_data_unavailable";
      self.postMessage({ id: message.id, error: code });
    }
  });
};
