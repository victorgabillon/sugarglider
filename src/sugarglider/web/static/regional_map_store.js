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

  async function openSelected(row, directory = null) {
    const manifest = row.manifest;
    directory ??= await versions.committedDirectory(manifest.region_id, manifest.build_id);
    if (cached?.regionId === manifest.region_id && cached.buildId === manifest.build_id
      && await cached.directory.isSameEntry(directory)) {
      try { await cached.opened.checkUnchanged(); return cached.opened; }
      catch (error) { cached = null; throw error; }
    }
    cached = null;
    const scoped = await components({ manifest, directory });
    const opened = await scoped.openMap();
    cached = { regionId: manifest.region_id, buildId: manifest.build_id, directory, opened };
    return opened;
  }

  // Planning already owns the version lease. Share the map runtime's opened
  // component without acquiring another lease or maintaining a verification table.
  async function verifyMap(manifest, directory) {
    requireData(manifest.region_id === selectedRegionId(), "regional_version_changed");
    await openSelected({ manifest }, directory);
    return true;
  }

  async function scanInstalledPacks() {
    return versions.withCommittedRegions(async (snapshot) => {
      let row;
      try { row = selectCommittedRegion(snapshot, selectedRegionId()); }
      catch (error) {
        cached = null;
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
      return openSelected(row);
    });
  }

  const unavailable = () => { throw new RegionalDataError("regional_use_download_screen"); };
  return Object.freeze({ capabilities: () => probe.capabilities(), scanInstalledPacks, openPackSource, verifyMap,
    installPack: unavailable, removePack: unavailable, cancelActiveInstalls() {}, requestPersistence: () => probe.requestPersistence() });
}
