import { RegionalDataError, freezeData, parseRegionalManifest, positiveInteger, requireData, requireFields,
  safeRegionalId, validBounds, validSha256 } from "./regional_manifest.js";

export async function regionalRoutingReference(value) {
  const manifest = await parseRegionalManifest(JSON.stringify(value));
  const routing = manifest.components.routing;
  return captureRegionalRoutingReference({
    region_id: manifest.region_id, build_id: manifest.build_id,
    pack_id: routing.component_id, bounds: manifest.bounds,
    manifest: { byte_size: routing.files[0].byte_size, sha256: routing.files[0].sha256 },
    archive: { byte_size: routing.files[1].byte_size, sha256: routing.files[1].sha256 },
  });
}

// Mirrors the typed native reference boundary, without paths or participant data.
export function captureRegionalRoutingReference(value) {
  try { return captureReference(value); }
  catch { throw new RegionalDataError("invalid_regional_routing_reference"); }
}

function captureReference(value) {
  requireFields(value, ["region_id", "build_id", "pack_id", "bounds", "manifest", "archive"]);
  requireData(safeRegionalId(value.region_id) && validSha256(value.build_id)
    && safeRegionalId(value.pack_id) && validBounds(value.bounds), "invalid_regional_routing_reference");
  for (const [kind, maximum] of [["manifest", 16_384], ["archive", 2 ** 31]]) {
    requireFields(value[kind], ["byte_size", "sha256"]);
    requireData(positiveInteger(value[kind].byte_size) && value[kind].byte_size <= maximum
      && validSha256(value[kind].sha256), "invalid_regional_routing_reference");
  }
  requireData(value.archive.byte_size % 512 === 0, "invalid_regional_routing_reference");
  return freezeData(structuredClone(value));
}
