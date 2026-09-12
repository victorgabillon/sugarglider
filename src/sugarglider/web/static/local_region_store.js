import { validateMapPackInstallUrl } from "./map_pack_store.js";
import {
  REGIONAL_MANIFEST_MAX_BYTES, RegionalDataError, parseRegionalManifest,
  requireData, safeRegionalId, validSha256, verifyRegionalBytes,
} from "./regional_manifest.js";
import { createLocalRegionData, decodeRegionalIndex } from "./local_region_data.js";

const DIRECTORY = "sugarglider-region-components";
const LOCK = "sugarglider-region-components-mutation";
const MAX_REGIONS = 8;

// Only places/nature live here. Maps remain in the shared random-read map store;
// Valhalla archives remain native. PR42 can coordinate these independent stores.
export function createLocalRegionStore({
  storage = globalThis.navigator?.storage,
  locks = globalThis.navigator?.locks,
  fetchResource = (...args) => globalThis.fetch(...args),
  pageLocation = globalThis.location,
} = {}) {
  async function root() {
    try { return await (await storage.getDirectory()).getDirectoryHandle(DIRECTORY, { create: true }); }
    catch { throw new RegionalDataError("regional_storage_unavailable"); }
  }

  async function mutate(action) {
    requireData(typeof locks?.request === "function", "regional_storage_unavailable");
    return locks.request(LOCK, action);
  }

  async function list() {
    const directory = await root();
    const entries = [];
    for await (const [id, handle] of directory.entries()) {
      if (safeRegionalId(id) && handle.kind === "directory") entries.push(id);
      requireData(entries.length <= MAX_REGIONS, "regional_storage_limit");
    }
    const results = [];
    for (const regionId of entries.sort()) {
      try {
        const installed = await open(regionId);
        results.push({ region_id: regionId, status: "installed", manifest: installed.manifest });
      } catch (error) {
        results.push({ region_id: regionId, status: "unavailable", code: error.code ?? "regional_install_incomplete" });
      }
    }
    return results;
  }

  async function open(regionId) {
    requireData(safeRegionalId(regionId), "invalid_region_id");
    try {
      const region = await (await root()).getDirectoryHandle(regionId);
      const pointer = JSON.parse(await readText(region, "active.json", 256));
      requireData(Object.keys(pointer).length === 1 && validSha256(pointer.build_id), "regional_install_incomplete");
      const version = await region.getDirectoryHandle(pointer.build_id);
      const manifest = await parseRegionalManifest(await readText(version, "manifest.json", REGIONAL_MANIFEST_MAX_BYTES));
      requireData(manifest.region_id === regionId && manifest.build_id === pointer.build_id, "regional_install_incomplete");
      const files = {};
      for (const kind of ["pois", "nature"]) {
        const file = await (await (await version.getDirectoryHandle(kind)).getFileHandle("index.json.gz")).getFile();
        requireData(file.size === manifest.components[kind].files[0].byte_size, "regional_size_mismatch");
        files[kind] = file;
      }
      return { manifest, files };
    } catch (error) {
      if (error instanceof RegionalDataError) throw error;
      throw new RegionalDataError("regional_install_incomplete");
    }
  }

  async function install(urlText, { signal, onProgress = () => {}, regionalManifest = null } = {}) {
    const url = validateMapPackInstallUrl(urlText, pageLocation);
    // PR42 supplies its captured manifest; do not refetch a possibly newer one
    // while other components are being staged for the original build.
    const suppliedManifest = regionalManifest === null ? null : await parseRegionalManifest(JSON.stringify(regionalManifest));
    return mutate(async () => {
      const manifest = suppliedManifest ?? await parseRegionalManifest(new TextDecoder("utf-8", { fatal: true }).decode(
        await download(url, REGIONAL_MANIFEST_MAX_BYTES, signal, false),
      ));
      const existing = await list();
      requireData(existing.some((item) => item.region_id === manifest.region_id) || existing.length < MAX_REGIONS, "regional_storage_limit");
      const required = ["pois", "nature"].reduce((sum, kind) => sum + manifest.components[kind].files[0].byte_size, 0);
      // Quota estimates are advisory; write failures still fail before activation.
      try {
        const estimate = await storage.estimate?.();
        if (Number.isFinite(estimate?.quota) && Number.isFinite(estimate?.usage)) {
          requireData(estimate.quota - estimate.usage >= required + REGIONAL_MANIFEST_MAX_BYTES, "regional_insufficient_storage");
        }
      } catch (error) { if (error instanceof RegionalDataError) throw error; }
      const directory = await root();
      const region = await directory.getDirectoryHandle(manifest.region_id, { create: true });
      let activeBuild = null;
      try { activeBuild = JSON.parse(await readText(region, "active.json", 256)).build_id; } catch { /* First or interrupted installation. */ }
      // Never overwrite active bytes, even if the incoming manifest has the same ID.
      if (activeBuild === manifest.build_id) {
        try { await loadLocalRegionData(await open(manifest.region_id)); }
        catch { throw new RegionalDataError("regional_corrupt_remove_and_reinstall"); }
        return manifest;
      }
      const version = await region.getDirectoryHandle(manifest.build_id, { create: true });
      try {
        const documents = {};
        for (const kind of ["pois", "nature"]) {
          signal?.throwIfAborted();
          const descriptor = manifest.components[kind].files[0];
          onProgress({ component: kind, status: "downloading", byte_size: descriptor.byte_size });
          const bytes = await download(new URL(descriptor.path, url), descriptor.byte_size, signal, true);
          await verifyRegionalBytes(bytes, descriptor);
          documents[kind] = await decodeRegionalIndex(bytes, descriptor);
          const component = await version.getDirectoryHandle(kind, { create: true });
          await writeFile(component, "index.json.gz", bytes);
        }
        // Full structural validation before the completion marker and active switch.
        createLocalRegionData(manifest, documents);
        signal?.throwIfAborted();
        await writeFile(version, "manifest.json", JSON.stringify(manifest));
        signal?.throwIfAborted();
        await writeFile(region, "active.json", JSON.stringify({ build_id: manifest.build_id }));
      } catch (error) {
        await region.removeEntry(manifest.build_id, { recursive: true }).catch(() => {});
        if (error?.name === "QuotaExceededError") throw new RegionalDataError("regional_insufficient_storage");
        throw error;
      }
      // Stale/incomplete versions are owned by this store. Cleanup failure does not
      // invalidate a completed active version; list/open remain authoritative.
      try {
        for await (const [name, handle] of region.entries()) {
          if (handle.kind === "directory" && validSha256(name) && name !== manifest.build_id) {
            await region.removeEntry(name, { recursive: true }).catch(() => {});
          }
        }
      } catch { /* Optional cleanup cannot turn a committed install into failure. */ }
      onProgress({ component: null, status: "installed", byte_size: required });
      return manifest;
    });
  }

  async function remove(regionId) {
    requireData(safeRegionalId(regionId), "invalid_region_id");
    return mutate(async () => (await root()).removeEntry(regionId, { recursive: true }));
  }

  async function download(url, maximum, signal, exact) {
    signal?.throwIfAborted();
    const response = await fetchResource(url.href, { method: "GET", credentials: "omit", redirect: "error",
      cache: "no-store", referrerPolicy: "no-referrer", signal });
    requireData(response.ok && (!response.url || response.url === url.href) && !response.redirected, "regional_download_failed");
    const encoding = response.headers?.get("Content-Encoding");
    requireData(!exact || !encoding || encoding.toLowerCase() === "identity", "regional_encoded_download");
    const reader = response.body?.getReader();
    requireData(reader, "regional_download_failed");
    const chunks = [];
    let total = 0;
    try {
      while (true) {
        signal?.throwIfAborted();
        const { done, value } = await reader.read();
        if (done) break;
        total += value.byteLength;
        requireData(total <= maximum, "regional_size_mismatch");
        chunks.push(value);
      }
      requireData(!exact || total === maximum, "regional_size_mismatch");
      const bytes = new Uint8Array(total);
      let offset = 0;
      for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
      return bytes;
    } catch (error) { await reader.cancel().catch(() => {}); throw error; }
    finally { reader.releaseLock(); }
  }

  return Object.freeze({ list, open, install, remove });
}

export async function loadLocalRegionData({ manifest, files }) {
  const documents = {};
  for (const kind of ["pois", "nature"]) {
    documents[kind] = await decodeRegionalIndex(await files[kind].arrayBuffer(), manifest.components[kind].files[0]);
  }
  return createLocalRegionData(manifest, documents);
}

async function readText(directory, name, maximum) {
  const file = await (await directory.getFileHandle(name)).getFile();
  requireData(file.size > 0 && file.size <= maximum, "regional_install_incomplete");
  return file.text();
}

async function writeFile(directory, name, data) {
  const writable = await (await directory.getFileHandle(name, { create: true })).createWritable();
  try { await writable.write(data); await writable.close(); }
  catch (error) { await writable.abort().catch(() => {}); throw error; }
}
