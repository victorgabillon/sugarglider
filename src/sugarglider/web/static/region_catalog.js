import { RegionalDataError, boundedText, freezeData, positiveInteger, requireData, requireFields,
  safeRegionalId, validBounds, validSha256 } from "./regional_manifest.js";
import { regionalDistributionUrl, readRegionalText } from "./regional_distribution.js";

export function parseRegionCatalog(value, pageLocation = globalThis.location) {
  try {
    requireFields(value, ["schema_version", "regions"]);
    requireData(value.schema_version === 1 && Array.isArray(value.regions) && value.regions.length <= 8);
    const ids = new Set();
    for (const row of value.regions) {
      requireFields(row, ["region_id", "display_name", "description", "build_id", "bounds", "download_bytes", "manifest_url"]);
      requireData(safeRegionalId(row.region_id) && !ids.has(row.region_id) && boundedText(row.display_name, 120)
        && boundedText(row.description, 500) && validSha256(row.build_id) && validBounds(row.bounds)
        && positiveInteger(row.download_bytes) && row.download_bytes <= 2 ** 33);
      if (row.manifest_url !== null) regionalDistributionUrl(row.manifest_url, pageLocation);
      ids.add(row.region_id);
    }
    return freezeData(structuredClone(value.regions));
  } catch { throw new RegionalDataError("regional_catalog_unavailable"); }
}

export async function loadRegionCatalog({ fetchResource = (...args) => globalThis.fetch(...args) } = {}) {
  try {
    const signal = AbortSignal.timeout(10_000);
    const response = await fetchResource("/static/offline_region_catalog.json", { credentials: "omit", redirect: "error", signal });
    requireData(response.status === 200 && !response.redirected, "regional_catalog_unavailable");
    const text = await readRegionalText(response, 16_384, signal);
    return parseRegionCatalog(JSON.parse(text));
  } catch { throw new RegionalDataError("regional_catalog_unavailable"); }
}
