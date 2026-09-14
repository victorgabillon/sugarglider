import { createMapPackStore } from "./map_pack_store.js";
import { createVersionedRegionComponents } from "./region_components.js";
import { selectCommittedRegion } from "./regional_planning.js";
import { RegionalDataError, freezeData, requireData } from "./regional_manifest.js";

// A read adapter for the existing offline-map runtime. One explicitly selected
// regional version supplies its shared PMTiles source; it never scans old packs.
export function createRegionalMapStore({ versions, selectedRegionId,
  components = createVersionedRegionComponents,
  probe = createMapPackStore(),
} = {}) {
  let cached = null;
  const scan = (packs = [], invalid = []) => freezeData({ packs, invalid_pack_ids: invalid, partial_pack_ids: [] });

  async function openSelected(row) {
    const manifest = row.manifest;
    const directory = await versions.committedDirectory(manifest.region_id, manifest.build_id);
    const scoped = await components({ manifest, directory });
    const opened = await scoped.openMap();
    cached = { regionId: manifest.region_id, buildId: manifest.build_id, opened };
    return opened;
  }

  async function scanInstalledPacks() {
    cached = null;
    return versions.withCommittedRegions(async (snapshot) => {
      let row;
      try { row = selectCommittedRegion(snapshot, selectedRegionId()); }
      catch (error) {
        if (["regional_required", "regional_selection_required"].includes(error.code)) return scan();
        return scan([], selectedRegionId() ? [selectedRegionId()] : []);
      }
      try { return scan([(await openSelected(row)).manifest]); }
      catch { return scan([], [row.manifest.components.map.component_id]); }
    });
  }

  async function openPackSource(packId) {
    return versions.withCommittedRegions(async (snapshot) => {
      const row = selectCommittedRegion(snapshot, selectedRegionId()), manifest = row.manifest;
      requireData(manifest.components.map.component_id === packId, "regional_version_changed");
      if (cached?.regionId === manifest.region_id && cached.buildId === manifest.build_id) return cached.opened;
      return openSelected(row);
    });
  }

  const unavailable = () => { throw new RegionalDataError("regional_use_download_screen"); };
  return Object.freeze({ capabilities: () => probe.capabilities(), scanInstalledPacks, openPackSource,
    installPack: unavailable, removePack: unavailable, cancelActiveInstalls() {}, requestPersistence: () => probe.requestPersistence() });
}
