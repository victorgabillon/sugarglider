import { PWA_STORES } from "./pwa_store.js";
import { safeRegionalId } from "./regional_manifest.js";

const PREFERENCE_KEY = "planner-region-id";

// A hint only: committed OPFS metadata and the normal component checks remain
// authoritative. Use the existing optional store; retain no regional data here.
export function createRegionPreference(store) {
  let pending = Promise.resolve();
  function remember(regionId) {
    if (regionId !== null && !safeRegionalId(regionId)) return Promise.resolve(false);
    // Deletion shares the queue so an older write cannot undo a clear/switch.
    pending = pending.then(async () => {
      try {
        if (regionId === null) await store.remove(PWA_STORES.publicRuntime, PREFERENCE_KEY);
        else await store.put(PWA_STORES.publicRuntime, PREFERENCE_KEY, regionId);
        return Boolean(store.durable);
      } catch { return false; }
    });
    return pending;
  }
  return Object.freeze({
    async restore(versions) {
      try {
        const regionId = await store.get(PWA_STORES.publicRuntime, PREFERENCE_KEY);
        if (regionId === undefined) return null;
        if (safeRegionalId(regionId) && (await versions.list()).some(row => row.region_id === regionId && row.status === "committed")) {
          return regionId;
        }
        void remember(null);
      } catch { /* Optional preference failures must not hide installed regions. */ }
      return null;
    },
    remember,
  });
}
