import { selectCommittedRegion } from "./regional_planning.js";
import { requireData } from "./regional_manifest.js";

// Discovery holds the same committed-version lease as other regional readers.
// No route capability, routing call, network POI request or map read is needed.
export function createLocalPlaceSearch({ versions, regionClient, selectedRegionId }) {
  return leasedSearch({ versions, regionClient, selectedRegionId }, "searchPois");
}
export function createLocalPlaceNameSearch(options) {
  return leasedSearch(options, "searchPlaceNames");
}
function leasedSearch({ versions, regionClient, selectedRegionId }, operation) {
  return async (query, signal) => {
    const requireCurrent = () => {
      if (signal?.aborted) throw new DOMException("Place search cancelled.", "AbortError");
    };
    requireCurrent();
    return versions.withCommittedRegions(async (rows) => {
      requireCurrent();
      const row = selectCommittedRegion(rows, selectedRegionId());
      const directory = await versions.committedDirectory(row.region_id, row.manifest.build_id);
      const session = await regionClient.loadVersion(row.manifest, directory);
      requireCurrent();
      requireData(session.identity.build_id === row.manifest.build_id
        && session.identity.region_id === row.region_id, "regional_identity_mismatch");
      const response = await session[operation](query);
      requireCurrent();
      return response;
    });
  };
}
