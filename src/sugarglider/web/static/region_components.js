import { MapPackStore, validateMapPackInstallUrl } from "./map_pack_store.js";
import { createLocalRegionStore, loadLocalRegionData } from "./local_region_store.js";
import { parseRegionalManifest, requireData } from "./regional_manifest.js";
import { verifyRegionalFile } from "./regional_integrity.js";

// The caller owns either withStagedVersion or withCommittedRegions for the
// complete operation. This is a scope adapter over the shared component formats,
// not another map reader or another index representation. Index work runs in the
// region worker when connected to the application.
export async function createVersionedRegionComponents({
  directory, manifest: value,
  storage = globalThis.navigator?.storage,
  locks = globalThis.navigator?.locks,
  fetchResource = (...args) => globalThis.fetch(...args),
  pageLocation = globalThis.location,
} = {}) {
  const manifest = await parseRegionalManifest(JSON.stringify(value));
  requireData(directory?.kind === "directory", "regional_storage_unavailable");
  const scopedStorage = {
    getDirectory: async () => directory,
    estimate: storage?.estimate ? () => storage.estimate() : undefined,
    persisted: storage?.persisted ? () => storage.persisted() : undefined,
  };
  const maps = new MapPackStore({ storageManager: scopedStorage, fetchRequest: fetchResource, pageLocation,
    probeSuffix: `region-${manifest.region_id}-${manifest.build_id}` });
  const indexes = createLocalRegionStore({ storage: scopedStorage, locks, fetchResource, pageLocation });

  async function openMap({ signal, onProgress } = {}) {
    const pack = await maps.getPack(manifest.components.map.component_id);
    requireMapIdentity(pack.manifest, manifest);
    await verifyRegionalFile(await pack.manifestHandle.getFile(), manifest.components.map.files[0], { signal });
    await verifyRegionalFile(await pack.archiveHandle.getFile(), manifest.components.map.files[1], { signal, onProgress });
    const opened = await maps.openPackSource(pack.manifest.pack_id);
    signal?.throwIfAborted();
    return opened;
  }

  async function verifyMap(options) { await openMap(options); return true; }

  async function installMap(urlText, { signal, onProgress } = {}) {
    const url = validateMapPackInstallUrl(urlText, pageLocation);
    signal?.throwIfAborted();
    const existing = await maps.scanInstalledPacks();
    if (existing.packs.some((pack) => pack.pack_id === manifest.components.map.component_id)) {
      // An interrupted installation can resume completed immutable components.
      // Corrupt completed data needs explicit cleanup, never an overwrite.
      await verifyMap({ signal });
      return;
    }
    requireData(!existing.invalid_pack_ids.includes(manifest.components.map.component_id), "regional_corrupt_remove_and_reinstall");
    await maps.installPack(new URL(manifest.components.map.files[0].path, url).href,
      { signal, onProgress, regionalManifest: manifest });
  }

  async function openIndexes() {
    const opened = await indexes.open(manifest.region_id);
    requireData(opened.manifest.build_id === manifest.build_id, "regional_identity_mismatch");
    return loadLocalRegionData(opened);
  }

  async function installIndexes(urlText, options = {}) {
    const installed = await indexes.install(urlText, { ...options, regionalManifest: manifest });
    requireData(installed.build_id === manifest.build_id, "regional_identity_mismatch");
  }

  return Object.freeze({ manifest, installMap, verifyMap, openMap, installIndexes, openIndexes });
}

function requireMapIdentity(map, region) {
  requireData(map.pack_id === region.components.map.component_id
    && map.byte_size === region.components.map.files[1].byte_size
    && map.bounds.every((coordinate, index) => coordinate === region.bounds[index]), "regional_identity_mismatch");
}
