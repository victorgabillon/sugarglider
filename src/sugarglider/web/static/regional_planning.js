import { createVersionedRegionComponents } from "./region_components.js";
import { RegionalDataError, requireData, safeRegionalId } from "./regional_manifest.js";
import { regionalRoutingReference } from "./regional_routing_reference.js";

export function selectCommittedRegion(snapshot, selected) {
  requireData(selected === null || safeRegionalId(selected), "invalid_region_id");
  const available = snapshot.filter((row) => row.status === "committed");
  let row = selected === null ? null : snapshot.find((item) => item.region_id === selected);
  if (selected === null && available.length === 1) [row] = available;
  if (!row) throw new RegionalDataError(selected === null && available.length > 1
    ? "regional_selection_required" : "regional_required");
  requireData(row.status === "committed", row.code ?? "regional_install_incomplete");
  return row;
}

// The complete callback includes search, native drain and canonical publication.
// Selection names one region, never a list from which routing may silently retry.
export function createRegionalPlanningContext({
  versions, bridge, regionClient, inspectNative,
  selectedRegionId = () => null,
  components = createVersionedRegionComponents,
} = {}) {
  return async function withRegion(run) {
    return versions.withCommittedRegions(async (snapshot) => {
      const row = selectCommittedRegion(snapshot, selectedRegionId());
      const manifest = row.manifest;
      const reference = await regionalRoutingReference(manifest);
      const directory = await versions.committedDirectory(manifest.region_id, manifest.build_id);
      const native = await inspectNative(reference);
      requireData(native?.status === "ready", native?.code ?? "regional_routing_unavailable");
      const scoped = await components({ manifest, directory });
      await scoped.verifyMap();
      const session = await regionClient.loadVersion(manifest, directory);
      requireData(session.identity.build_id === manifest.build_id
        && session.identity.region_id === manifest.region_id
        && session.identity.routing_pack_id === reference.pack_id, "regional_identity_mismatch");
      return run(Object.freeze({ reference, bridge: bridge.forRegion(reference), capabilities: native.capabilities,
        getRegionData: async (packId) => packId === reference.pack_id ? session : null }));
    });
  };
}
