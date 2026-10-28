import { createVersionedRegionComponents } from "./region_components.js";
import { RegionalDataError, requireData, safeRegionalId, containsPosition } from "./regional_manifest.js";
import { regionalRoutingReference } from "./regional_routing_reference.js";

export function selectCommittedRegion(snapshot, selected, request = null) {
  requireData(selected === null || safeRegionalId(selected), "invalid_region_id");
  const available = snapshot.filter((row) => row.status === "committed");
  if (request?.start) {
    const points = [request.start, ...(request.end ? [request.end] : []),
      ...(request.waypoints ?? request.hard_waypoints ?? [])
        .filter(point => (point.constraint_strength ?? "exact") === "exact")
        .map(point => point.coordinate ?? point)];
    requireData(points.every(point => Number.isFinite(point?.lon) && Number.isFinite(point?.lat)), "invalid_request");
    const covering = available.filter(row => points.every(point => containsPosition(row.manifest.bounds, [point.lon, point.lat])));
    // A covering user preference remains stable. Otherwise choose one complete
    // graph deterministically, before the first route call; never retry graphs.
    const preferred = covering.find(row => row.region_id === selected);
    if (preferred) return preferred;
    covering.sort((a, b) => area(a.manifest.bounds) - area(b.manifest.bounds)
      || (a.region_id < b.region_id ? -1 : a.region_id > b.region_id ? 1 : 0));
    if (covering.length) return covering[0];
    throw new RegionalDataError(available.length ? "no_covering_routing_pack" : "regional_required");
  }
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
  verifyMap = async (manifest, directory) => (await components({ manifest, directory })).verifyMap(),
} = {}) {
  return async function withRegion(run, request = null) {
    return versions.withCommittedRegions(async (snapshot) => {
      const row = selectCommittedRegion(snapshot, selectedRegionId(), request);
      const manifest = row.manifest;
      const reference = await regionalRoutingReference(manifest);
      const directory = await versions.committedDirectory(manifest.region_id, manifest.build_id);
      // Independent native/index verification can overlap. Drain both outcomes
      // before releasing the version lease, including when either check fails.
      const [nativeCheck, indexCheck] = await Promise.allSettled([
        inspectNative(reference),
        (async () => { await verifyMap(manifest, directory); return regionClient.loadVersion(manifest, directory); })(),
      ]);
      if (nativeCheck.status === "rejected") throw nativeCheck.reason;
      const native = nativeCheck.value;
      requireData(native?.status === "ready", native?.code ?? "regional_routing_unavailable");
      if (indexCheck.status === "rejected") throw indexCheck.reason;
      const session = indexCheck.value;
      requireData(session.identity.build_id === manifest.build_id
        && session.identity.region_id === manifest.region_id
        && session.identity.routing_pack_id === reference.pack_id, "regional_identity_mismatch");
      return run(Object.freeze({ reference, bridge: bridge.forRegion(reference), capabilities: native.capabilities,
        getRegionData: async (packId) => packId === reference.pack_id ? session : null }));
    });
  };
}

const area = bounds => (bounds[2] - bounds[0]) * (bounds[3] - bounds[1]);
