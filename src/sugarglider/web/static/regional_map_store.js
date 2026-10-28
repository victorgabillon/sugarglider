import { createMapPackStore } from "./map_pack_store.js";
import { createVersionedRegionComponents } from "./region_components.js";
import { selectCommittedRegion } from "./regional_planning.js";
import { RegionalDataError, freezeData, requireData } from "./regional_manifest.js";

// Maps may display any committed region. Planning still verifies only its
// explicitly selected version, under the unchanged version lease.
export function createRegionalMapStore({ versions, selectedRegionId,
  components = createVersionedRegionComponents,
  probe = createMapPackStore(),
  includeAllCommittedMaps = false,
} = {}) {
  const cached = new Map();
  let selectedBounds = null;
  const scan = (packs = [], invalid = []) => freezeData({ packs, invalid_pack_ids: invalid, partial_pack_ids: [] });

  async function openSelected(row, directory = null) {
    const manifest = row.manifest;
    directory ??= await versions.committedDirectory(manifest.region_id, manifest.build_id);
    const previous = cached.get(manifest.region_id);
    if (previous?.buildId === manifest.build_id && await previous.directory.isSameEntry(directory)) {
      try { await previous.opened.checkUnchanged(); return previous.opened; }
      catch (error) { cached.delete(manifest.region_id); throw error; }
    }
    cached.delete(manifest.region_id);
    const scoped = await components({ manifest, directory });
    const opened = await scoped.openMap();
    cached.set(manifest.region_id, { buildId: manifest.build_id, directory, opened });
    return opened;
  }

  // Planning already owns the version lease. Share the map runtime's opened
  // component without acquiring another lease or maintaining a verification table.
  async function verifyMap(manifest, directory) {
    await openSelected({ manifest }, directory);
    return true;
  }

  async function scanInstalledPacks() {
    return versions.withCommittedRegions(async (snapshot) => {
      let row;
      selectedBounds = null;
      try { row = selectCommittedRegion(snapshot, selectedRegionId()); }
      catch (error) {
        if (!includeAllCommittedMaps) {
          cached.clear();
          if (["regional_required", "regional_selection_required"].includes(error.code)) return scan();
          return scan([], selectedRegionId() ? [selectedRegionId()] : []);
        }
      }
      selectedBounds = row?.manifest.bounds ?? null;
      const rows = includeAllCommittedMaps ? snapshot.filter((entry) => entry.status === "committed") : [row];
      // Keep startup verification of the selected routing version first. Map
      // display selection still uses the shared smallest-area/ID ordering.
      rows.sort((a, b) => Number(b === row) - Number(a === row));
      const retained = new Set(rows.map((entry) => entry.manifest.region_id));
      for (const id of cached.keys()) if (!retained.has(id)) cached.delete(id);
      const packs = [], invalid = [];
      for (const entry of rows) {
        try { packs.push((await openSelected(entry)).manifest); }
        catch { invalid.push(entry.manifest.components.map.component_id); }
      }
      return scan(packs, invalid);
    });
  }

  async function openPackSource(packId) {
    return versions.withCommittedRegions(async (snapshot) => {
      const row = includeAllCommittedMaps
        ? snapshot.find((entry) => entry.status === "committed" && entry.manifest.components.map.component_id === packId)
        : selectCommittedRegion(snapshot, selectedRegionId());
      requireData(row, "regional_version_changed");
      const manifest = row.manifest;
      requireData(manifest.components.map.component_id === packId, "regional_version_changed");
      return openSelected(row);
    });
  }

  const unavailable = () => { throw new RegionalDataError("regional_use_download_screen"); };
  return Object.freeze({ capabilities: () => probe.capabilities(), scanInstalledPacks, openPackSource, verifyMap,
    selectedMapBounds: () => selectedBounds,
    installPack: unavailable, removePack: unavailable, cancelActiveInstalls() {}, requestPersistence: () => probe.requestPersistence() });
}
