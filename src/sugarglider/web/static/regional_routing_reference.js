import { RegionalDataError, freezeData, parseRegionalManifest, positiveInteger, requireData, requireFields,
  safeRegionalId, validBounds, validSha256, regionalElevationPaths } from "./regional_manifest.js";

export async function regionalRoutingReference(value) {
  const manifest = await parseRegionalManifest(JSON.stringify(value));
  const routing = manifest.components.routing;
  return captureRegionalRoutingReference({
    region_id: manifest.region_id, build_id: manifest.build_id,
    pack_id: routing.component_id, bounds: manifest.bounds,
    manifest: { byte_size: routing.files[0].byte_size, sha256: routing.files[0].sha256 },
    archive: { byte_size: routing.files[1].byte_size, sha256: routing.files[1].sha256 },
    elevation: { component_id: manifest.components.elevation.component_id,
      manifest: { byte_size: manifest.components.elevation.files[0].byte_size,
        sha256: manifest.components.elevation.files[0].sha256 },
      tiles: manifest.components.elevation.files.slice(1).map((file) => ({
        path: file.path.slice("elevation/".length), byte_size: file.byte_size, sha256: file.sha256,
      })) },
  });
}

// Mirrors the typed native reference boundary, without paths or participant data.
export function captureRegionalRoutingReference(value) {
  try { return captureReference(value); }
  catch { throw new RegionalDataError("invalid_regional_routing_reference"); }
}

function captureReference(value) {
  requireFields(value, ["region_id", "build_id", "pack_id", "bounds", "manifest", "archive", "elevation"]);
  requireData(safeRegionalId(value.region_id) && validSha256(value.build_id)
    && safeRegionalId(value.pack_id) && validBounds(value.bounds), "invalid_regional_routing_reference");
  for (const [kind, maximum] of [["manifest", 16_384], ["archive", 2 ** 31]]) {
    requireFields(value[kind], ["byte_size", "sha256"]);
    requireData(positiveInteger(value[kind].byte_size) && value[kind].byte_size <= maximum
      && validSha256(value[kind].sha256), "invalid_regional_routing_reference");
  }
  requireData(value.archive.byte_size % 512 === 0, "invalid_regional_routing_reference");
  requireFields(value.elevation, ["component_id", "manifest", "tiles"]);
  requireData(safeRegionalId(value.elevation.component_id), "invalid_regional_routing_reference");
  requireFields(value.elevation.manifest, ["byte_size", "sha256"]);
  requireData(positiveInteger(value.elevation.manifest.byte_size) && value.elevation.manifest.byte_size <= 65_536
    && validSha256(value.elevation.manifest.sha256), "invalid_regional_routing_reference");
  const paths = regionalElevationPaths(value.bounds).map((path) => path.slice("elevation/".length));
  requireData(Array.isArray(value.elevation.tiles) && value.elevation.tiles.length === paths.length);
  value.elevation.tiles.forEach((tile, index) => {
    requireFields(tile, ["path", "byte_size", "sha256"]);
    requireData(tile.path === paths[index] && positiveInteger(tile.byte_size) && tile.byte_size <= 26_982_978
      && validSha256(tile.sha256), "invalid_regional_routing_reference");
  });
  return freezeData(structuredClone(value));
}
