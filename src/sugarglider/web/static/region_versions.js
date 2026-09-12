import {
  REGIONAL_MANIFEST_MAX_BYTES, RegionalDataError, freezeData, parseRegionalManifest,
  requireData, safeRegionalId, validSha256,
} from "./regional_manifest.js";

const ROOT_DIRECTORY = "sugarglider-installed-regions";
const MUTATION_LOCK = "sugarglider-region-version-mutation";
const COMPONENTS = Object.freeze(["map", "routing", "pois", "nature"]);
const MAX_REGIONS = 8;
const MAX_VERSIONS = 2;

// A single active record selects the regional version. Component writers use
// the inactive version directory; native archives remain in native storage.
export function createRegionVersionStore({
  storage = globalThis.navigator?.storage,
  locks = globalThis.navigator?.locks,
} = {}) {
  async function root() {
    try {
      return await (await storage.getDirectory()).getDirectoryHandle(ROOT_DIRECTORY, { create: true });
    } catch { throw new RegionalDataError("regional_storage_unavailable"); }
  }

  async function mutate(action) {
    requireData(typeof locks?.request === "function", "regional_storage_unavailable");
    return locks.request(MUTATION_LOCK, action);
  }

  async function ownVersion(regionId, buildId, action) {
    requireData(safeRegionalId(regionId) && validSha256(buildId), "invalid_regional_version");
    requireData(typeof locks?.request === "function", "regional_storage_unavailable");
    return locks.request(`${MUTATION_LOCK}/${regionId}/${buildId}`, action);
  }

  async function region(regionId, create = false) {
    requireData(safeRegionalId(regionId), "invalid_region_id");
    const directory = await root();
    const entries = await names(directory, safeRegionalId, MAX_REGIONS);
    if (create && !entries.includes(regionId)) {
      requireData(entries.length < MAX_REGIONS, "regional_storage_limit");
    }
    try { return await directory.getDirectoryHandle(regionId, { create }); }
    catch (error) { if (!create && error?.name === "NotFoundError") return null; throw error; }
  }

  async function activeBuild(directory) {
    let file;
    try { file = await (await directory.getFileHandle("active.json")).getFile(); }
    catch (error) { if (error?.name === "NotFoundError") return null; throw error; }
    try {
      requireData(file.size > 0 && file.size <= 256, "regional_active_record_invalid");
      const value = JSON.parse(await file.text());
      requireData(value !== null && typeof value === "object" && !Array.isArray(value)
        && Object.keys(value).length === 2 && value.schema_version === 1
        && (value.build_id === null || validSha256(value.build_id)), "regional_active_record_invalid");
      return value.build_id;
    } catch { throw new RegionalDataError("regional_active_record_invalid"); }
  }

  async function openVersion(directory, regionId, buildId) {
    requireData(validSha256(buildId), "invalid_regional_version");
    try {
      const version = await directory.getDirectoryHandle(buildId);
      const file = await (await version.getFileHandle("manifest.json")).getFile();
      requireData(file.size > 0 && file.size <= REGIONAL_MANIFEST_MAX_BYTES, "regional_install_incomplete");
      const manifest = await parseRegionalManifest(await file.text());
      requireData(manifest.region_id === regionId && manifest.build_id === buildId, "regional_install_incomplete");
      return { manifest, directory: version };
    } catch { throw new RegionalDataError("regional_install_incomplete"); }
  }

  async function read(regionId) {
    const directory = await region(regionId);
    if (!directory) return null;
    const buildId = await activeBuild(directory);
    if (buildId === null) return null;
    return (await openVersion(directory, regionId, buildId)).manifest;
  }

  async function list() {
    const directory = await root();
    const result = [];
    for (const regionId of await names(directory, safeRegionalId, MAX_REGIONS)) {
      try {
        const entry = await directory.getDirectoryHandle(regionId);
        const manifest = await read(regionId);
        const versions = await names(entry, validSha256, MAX_VERSIONS);
        // Component readiness remains a separate check by the coordinator.
        result.push({ region_id: regionId, status: manifest ? "committed" : "not_installed",
          manifest, inactive_build_ids: versions.filter((id) => id !== manifest?.build_id) });
      } catch (error) {
        result.push({ region_id: regionId, status: "unavailable",
          code: error instanceof RegionalDataError ? error.code : "regional_storage_unavailable" });
      }
    }
    return freezeData(result);
  }

  async function stage(manifestText, { signal } = {}) {
    const proposed = await parseRegionalManifest(manifestText);
    return mutate(async () => {
      signal?.throwIfAborted();
      const directory = await region(proposed.region_id, true);
      const previousBuildId = await activeBuild(directory);
      const versions = await names(directory, validSha256, MAX_VERSIONS);
      let manifest = proposed;
      if (versions.includes(proposed.build_id)) {
        manifest = (await openVersion(directory, proposed.region_id, proposed.build_id)).manifest;
      } else {
        requireData(versions.length < MAX_VERSIONS, "regional_staging_limit");
        const version = await directory.getDirectoryHandle(proposed.build_id, { create: true });
        await writeJson(version, "manifest.json", proposed, signal);
      }
      signal?.throwIfAborted();
      return freezeData({ manifest, previous_build_id: previousBuildId });
    });
  }

  async function stagedDirectory(regionId, buildId) {
    const directory = await region(regionId);
    requireData(directory, "regional_install_incomplete");
    requireData(await activeBuild(directory) !== buildId, "regional_version_in_use");
    return (await openVersion(directory, regionId, buildId)).directory;
  }

  // Component writers own this version until all asynchronous/native work drains.
  // Other committed versions remain usable while a download is in progress.
  async function withStagedVersion(ticket, action) {
    requireData(typeof action === "function", "invalid_regional_operation");
    const manifest = await parseRegionalManifest(JSON.stringify(ticket?.manifest));
    return ownVersion(manifest.region_id, manifest.build_id, async () => {
      const directory = await mutate(() => stagedDirectory(manifest.region_id, manifest.build_id));
      return action({ manifest, directory });
    });
  }

  // Read callers retain withCommittedRegions ownership through their operation.
  async function committedDirectory(regionId, buildId) {
    requireData(validSha256(buildId), "invalid_regional_version");
    const directory = await region(regionId);
    requireData(directory && await activeBuild(directory) === buildId, "regional_version_changed");
    return (await openVersion(directory, regionId, buildId)).directory;
  }

  async function activate(ticket, { verifyComponent, signal } = {}) {
    requireData(typeof verifyComponent === "function", "regional_components_unavailable");
    const manifest = await parseRegionalManifest(JSON.stringify(ticket?.manifest));
    const previous = ticket.previous_build_id;
    requireData(previous === null || validSha256(previous), "invalid_regional_version");
    return ownVersion(manifest.region_id, manifest.build_id, () => mutate(async () => {
      signal?.throwIfAborted();
      const directory = await region(manifest.region_id);
      requireData(directory, "regional_install_incomplete");
      const active = await activeBuild(directory);
      requireData(active === previous || active === manifest.build_id, "regional_version_changed");
      const staged = await openVersion(directory, manifest.region_id, manifest.build_id);
      for (const component of COMPONENTS) {
        signal?.throwIfAborted();
        requireData(await verifyComponent(component, staged.manifest, staged.directory) === true, "regional_components_unavailable");
      }
      signal?.throwIfAborted();
      if (active !== manifest.build_id) {
        try {
          await writeJson(directory, "active.json", { schema_version: 1, build_id: manifest.build_id }, signal);
        } catch (error) {
          // Once close starts, transport/storage failure is not proof of rollback.
          // A confirmed new pointer wins; uncertain state retains both versions.
          let observed;
          try { observed = await activeBuild(directory); }
          catch { throw new RegionalDataError("regional_commit_uncertain"); }
          if (observed !== manifest.build_id) throw error;
        }
      }
      return staged.manifest;
    }));
  }

  async function deactivate(regionId, expectedBuildId) {
    requireData(validSha256(expectedBuildId), "invalid_regional_version");
    return mutate(async () => {
      const directory = await region(regionId);
      if (!directory) return;
      const active = await activeBuild(directory);
      requireData(active === null || active === expectedBuildId, "regional_version_changed");
      if (active !== null) await writeJson(directory, "active.json", { schema_version: 1, build_id: null });
    });
  }

  async function removeInactiveVersion(regionId, buildId) {
    requireData(validSha256(buildId), "invalid_regional_version");
    return ownVersion(regionId, buildId, () => mutate(async () => {
      const directory = await region(regionId);
      if (!directory) return;
      requireData(await activeBuild(directory) !== buildId, "regional_version_in_use");
      try { await directory.removeEntry(buildId, { recursive: true }); }
      catch (error) { if (error?.name !== "NotFoundError") throw error; }
    }));
  }

  async function removeEmptyRegion(regionId) {
    return mutate(async () => {
      const directory = await region(regionId);
      if (!directory) return;
      requireData(await activeBuild(directory) === null, "regional_version_in_use");
      requireData((await names(directory, validSha256, MAX_VERSIONS)).length === 0, "regional_staging_in_use");
      await (await root()).removeEntry(regionId, { recursive: true });
    });
  }

  // Explicit recovery makes a corrupt pointer unavailable without deleting any
  // component. It cannot clear a valid newer commit or infer a previous version.
  async function recoverCorruptRecord(regionId) {
    return mutate(async () => {
      const directory = await region(regionId);
      requireData(directory, "regional_recovery_not_needed");
      let corrupt = false;
      try { await activeBuild(directory); }
      catch (error) { corrupt = error instanceof RegionalDataError && error.code === "regional_active_record_invalid"; }
      requireData(corrupt, "regional_recovery_not_needed");
      await writeJson(directory, "active.json", { schema_version: 1, build_id: null });
    });
  }

  // Hold the same lock through the complete planning promise, including its
  // native drain. The callback reads components but must not mutate this store.
  async function withCommittedRegions(action) {
    requireData(typeof action === "function", "invalid_regional_operation");
    return mutate(async () => action(await list()));
  }

  return Object.freeze({ list, read, stage, activate, deactivate,
    removeInactiveVersion, removeEmptyRegion, recoverCorruptRecord, withCommittedRegions,
    withStagedVersion, committedDirectory });
}

async function names(directory, valid, maximum) {
  const result = [];
  let scanned = 0;
  for await (const [name, handle] of directory.entries()) {
    requireData(++scanned <= 64, "regional_storage_limit");
    if (handle.kind === "directory" && valid(name)) result.push(name);
    requireData(result.length <= maximum, "regional_storage_limit");
  }
  return result.sort();
}

async function writeJson(directory, name, value, signal) {
  signal?.throwIfAborted();
  const writable = await (await directory.getFileHandle(name, { create: true })).createWritable();
  try {
    await writable.write(JSON.stringify(value));
    signal?.throwIfAborted();
    await writable.close();
  } catch (error) {
    await writable.abort().catch(() => {});
    if (error?.name === "AbortError") throw error;
    throw new RegionalDataError(error?.name === "QuotaExceededError" ? "regional_insufficient_storage" : "regional_write_failed");
  }
}
