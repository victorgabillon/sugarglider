import { createMapPackStore } from "./map_pack_store.js";
import { loadRegionCatalog } from "./region_catalog.js";
import { freezeData, requireData } from "./regional_manifest.js";
import { verifyRegionalFile } from "./regional_integrity.js";

// This reviewed private artifact is offered only by the matching bundled staging
// distribution. Neither a user-entered URL nor a remote manifest establishes trust.
export const ILE_DE_FRANCE_MAP = freezeData({
  pack_id: "ile-de-france-map-v1", display_name: "Île-de-France",
  manifest_url: "https://localhost:9444/maps/ile-de-france-map-v1/manifest.json",
  manifest: { byte_size: 621, sha256: "cce4e686a2d8cddfb0d938c822a66d655a5a868f357f70bb9c1480c06faf098e" },
  archive: { byte_size: 243080284, sha256: "eeea1321da3641ebb867473114bcd3706cb0d9f0b6ab2692baaf51058230b7a9" },
});

export async function plannerMapOffers({ loadCatalog = loadRegionCatalog } = {}) {
  try {
    const rows = await loadCatalog();
    return rows.some((row) => row.manifest_url?.startsWith("https://localhost:9444/regions/"))
      ? Object.freeze([ILE_DE_FRANCE_MAP]) : Object.freeze([]);
  } catch { return Object.freeze([]); }
}

// Composition only: complete products keep their own version directories and
// leases; independent maps stay in the existing standalone OPFS store.
export function createPlannerMapStore({ regional, independent = createMapPackStore(), offers = [ILE_DE_FRANCE_MAP],
  loadOffers = plannerMapOffers } = {}) {
  let regionalIds = new Set();
  let availableOffers = Object.freeze([]);
  const verified = new Map();
  const offerFor = (id) => offers.find((offer) => offer.pack_id === id);

  async function openIndependent(packId) {
    const offer = offerFor(packId);
    requireData(offer, "map_pack_untrusted");
    const record = await independent.getPack(packId);
    const manifestFile = await record.manifestHandle.getFile(), archiveFile = await record.archiveHandle.getFile();
    const previous = verified.get(packId);
    if (previous && manifestFile.size === previous.manifestFile.size && manifestFile.lastModified === previous.manifestFile.lastModified
      && archiveFile.size === previous.archiveFile.size && archiveFile.lastModified === previous.archiveFile.lastModified) {
      try {
        await previous.manifestFile.slice(0, 1).arrayBuffer();
        await previous.archiveFile.slice(0, 1).arrayBuffer();
        return previous.opened;
      } catch { verified.delete(packId); }
    }
    verified.delete(packId);
    await verifyRegionalFile(manifestFile, offer.manifest);
    await verifyRegionalFile(archiveFile, offer.archive);
    const opened = await independent.openPackSource(packId, { archiveFile });
    verified.set(packId, { manifestFile, archiveFile, opened });
    return opened;
  }

  async function scanInstalledPacks() {
    // Optional independent storage must never suppress a working regional map.
    const complete = await regional.scanInstalledPacks();
    regionalIds = new Set([...complete.packs.map((pack) => pack.pack_id), ...complete.invalid_pack_ids]);
    let separate;
    try { separate = await independent.scanInstalledPacks(); }
    catch { return freezeData({ ...complete, independent_storage_unavailable: true }); }
    const packs = [...complete.packs], invalid = [...complete.invalid_pack_ids, ...separate.invalid_pack_ids];
    const retained = new Set(separate.packs.map((pack) => pack.pack_id));
    for (const id of verified.keys()) if (!retained.has(id)) verified.delete(id);
    for (const pack of separate.packs) {
      if (regionalIds.has(pack.pack_id)) continue;
      try { packs.push((await openIndependent(pack.pack_id)).manifest); }
      catch { invalid.push(pack.pack_id); }
    }
    return freezeData({ packs, invalid_pack_ids: [...new Set(invalid)].sort(),
      partial_pack_ids: separate.partial_pack_ids.filter((id) => !regionalIds.has(id)), independent_storage_unavailable: false });
  }

  async function installPack(url, options = {}) {
    const offer = availableOffers.find((entry) => entry.manifest_url === url);
    requireData(offer && !regionalIds.has(offer.pack_id), "map_pack_untrusted");
    const installed = await independent.installPack(url, { ...options,
      expectedArchive: offer.archive, expectedManifest: offer.manifest, regionalManifest: null });
    requireData(installed.pack_id === offer.pack_id, "regional_identity_mismatch");
    verified.delete(offer.pack_id);
    return installed;
  }

  async function removePack(id) {
    // Refresh protection from current committed metadata before any deletion.
    const complete = await regional.scanInstalledPacks();
    requireData(!complete.packs.some((pack) => pack.pack_id === id) && !complete.invalid_pack_ids.includes(id), "regional_use_download_screen");
    await independent.removePack(id);
    verified.delete(id);
  }

  return Object.freeze({ capabilities: () => regional.capabilities(), scanInstalledPacks,
    openPackSource: (id) => regionalIds.has(id) ? regional.openPackSource(id) : openIndependent(id),
    installPack, removePack, get installOffers() { return availableOffers; },
    loadOffers: async () => { availableOffers = Object.freeze((await loadOffers()).filter((offer) => offers.includes(offer))); return availableOffers; },
    canRemovePack: (id) => !regionalIds.has(id),
    cancelActiveInstalls: () => independent.cancelActiveInstalls(), requestPersistence: () => independent.requestPersistence() });
}
