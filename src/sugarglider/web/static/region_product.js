import { createVersionedRegionComponents } from "./region_components.js";
import { RegionalDataError, requireData } from "./regional_manifest.js";
import { fetchRegionalManifest, regionalDownloadBytes } from "./regional_distribution.js";
import { regionalRoutingReference } from "./regional_routing_reference.js";

const OPERATION_LOCK = "sugarglider-region-product-operation";

// The product operation coordinates four independent component formats. Only
// the version store's final commit changes availability to planners and maps.
export function createRegionProduct({ versions, native, installerClient,
  locks = globalThis.navigator?.locks,
  components = createVersionedRegionComponents,
  readManifest = fetchRegionalManifest,
} = {}) {
  let controller = null;

  async function own(action) {
    requireData(!controller, "regional_operation_busy");
    requireData(typeof locks?.request === "function", "regional_storage_unavailable");
    const owned = new AbortController();
    controller = owned;
    try {
      return await locks.request(OPERATION_LOCK, { ifAvailable: true }, async (lock) => {
        requireData(lock, "regional_operation_busy");
        return action(owned.signal);
      });
    } finally { if (controller === owned) controller = null; }
  }

  function cancel() {
    controller?.abort();
    installerClient.cancelInstall();
  }

  async function install(url, { expectedRegionId = null, expectedBuildId = null, expectedDownloadBytes = null,
    onProgress = () => {} } = {}) {
    return own(async (userSignal) => {
      const deadline = AbortSignal.timeout(30 * 60 * 1_000);
      const signal = AbortSignal.any([userSignal, deadline]);
      const report = (component, received = null, total = null) => {
        try { onProgress({ component, received_bytes: received, total_bytes: total }); } catch { /* Presentation only. */ }
      };
      try {
        report("checking");
        const manifest = await readManifest(url, { signal });
        requireData((expectedRegionId === null || manifest.region_id === expectedRegionId)
          && (expectedBuildId === null || manifest.build_id === expectedBuildId)
          && (expectedDownloadBytes === null || regionalDownloadBytes(manifest) === expectedDownloadBytes), "regional_catalog_changed");
        const reference = await regionalRoutingReference(manifest);
        const ticket = await versions.stage(JSON.stringify(manifest), { signal });
        if (ticket.previous_build_id !== manifest.build_id) {
          // Serialize component transfers to bound memory and make cancellation
          // outcomes definite. Existing committed planning remains independent.
          await versions.withStagedVersion(ticket, async ({ directory }) => {
            const scoped = await components({ manifest, directory });
            report("map");
            await scoped.installMap(url, { signal, onProgress: ({ bytes_written, byte_size }) => report("map", bytes_written, byte_size) });
            signal.throwIfAborted();
            report("routing");
            await native.install(reference, url, { signal, onProgress: (bytes, total) => report("routing", bytes, total) });
            signal.throwIfAborted();
            report("places_nature");
            signal.throwIfAborted();
            const abortIndexes = () => installerClient.cancelInstall();
            signal.addEventListener("abort", abortIndexes, { once: true });
            try { await installerClient.installVersion(url, manifest, directory); }
            finally { signal.removeEventListener("abort", abortIndexes); }
            signal.throwIfAborted();
          });
        }
        report("verifying");
        let scoped, indexesVerified = false;
        const activated = await versions.activate(ticket, { signal,
          verifyComponent: async (kind, captured, directory) => {
            scoped ??= await components({ manifest: captured, directory });
            if (kind === "map") return scoped.verifyMap({ signal });
            if (kind === "routing") return (await native.inspect(reference, { signal })).status === "ready";
            if (!indexesVerified) indexesVerified = await scoped.verifyIndexes();
            return indexesVerified;
          } });
        // A confirmed commit wins even if Cancel arrived during pointer close.
        report("ready");
        return activated;
      } catch (error) {
        if (error.code?.endsWith("_uncertain")) throw error;
        if (userSignal.aborted) throw new RegionalDataError("regional_install_cancelled");
        if (deadline.aborted) throw new RegionalDataError("regional_transfer_timeout");
        throw error;
      }
    });
  }

  async function remove(regionId) {
    return own(() => versions.removeRegion(regionId, { beforeRemove: () => native.removeRegion(regionId) }));
  }

  async function discardUpdate(regionId, buildId) {
    return own(async () => {
      const entry = (await versions.inspectVersions(regionId)).find((item) => item.build_id === buildId);
      if (!entry) return;
      await versions.removeInactiveVersion(regionId, buildId,
        { beforeRemove: async () => { await native.removeVersion({ region_id: regionId, build_id: buildId }); } });
      await versions.removeEmptyRegion(regionId).catch((error) => {
        if (!(error instanceof RegionalDataError) || !["regional_version_in_use", "regional_staging_in_use"].includes(error.code)) throw error;
      });
    });
  }

  return Object.freeze({ install, cancel, remove, discardUpdate, busy: () => controller !== null });
}
