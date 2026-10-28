import { RegionalDataError, freezeData, requireData, requireFields, verifyRegionalBytes, validBounds } from "./regional_manifest.js";
import { createLocalRegionData, decodeRegionalIndex, prepareLocalNaturePartition,
  createNatureIntervalAccumulator, createWoodlandAccumulator, unavailableNature } from "./local_region_data.js";

export const NATURE_PARTITION_MAX_BYTES = 16 * 1024 * 1024;
export const NATURE_PARTITION_MAX_POSITIONS = 500_000;
export const isPartitionedNature = manifest => manifest.components.nature.files[0].format === "nature-partitions-v1-json";

export async function decodeNatureDirectory(bytes, manifest) {
  requireData(bytes.byteLength <= 32_768, "regional_index_too_large");
  await verifyRegionalBytes(bytes, manifest.components.nature.files[0]);
  let value;
  try { value = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes)); }
  catch { throw new RegionalDataError("invalid_regional_index"); }
  requireFields(value, ["schema_version", "source_sha256", "source_basename", "source_size_bytes", "bounds",
    "reference_latitude", "feature_count", "position_count", "partitions"]);
  requireData(value.schema_version === 1 && value.source_sha256 === manifest.source.sha256
    && value.source_basename === manifest.source.basename && value.source_size_bytes === manifest.source.byte_size
    && JSON.stringify(value.bounds) === JSON.stringify(manifest.bounds)
    && Number.isFinite(value.reference_latitude) && value.reference_latitude >= manifest.bounds[1]
    && value.reference_latitude <= manifest.bounds[3] && Array.isArray(value.partitions)
    && value.partitions.length >= 1 && value.partitions.length <= 64
    && value.partitions.length === manifest.components.nature.files.length - 1);
  let features = 0, positions = 0;
  value.partitions.forEach((part, index) => {
    requireFields(part, ["path", "bounds", "feature_count", "position_count"]);
    requireData(part.path === manifest.components.nature.files[index + 1].path && validBounds(part.bounds)
      && Number.isSafeInteger(part.feature_count) && part.feature_count > 0 && part.feature_count <= 250_000
      && Number.isSafeInteger(part.position_count) && part.position_count > 0 && part.position_count <= NATURE_PARTITION_MAX_POSITIONS);
    features += part.feature_count; positions += part.position_count;
  });
  requireData(value.feature_count === features && features <= 250_000 && value.position_count === positions);
  return freezeData(value);
}

export async function decodeNaturePartition(bytes, descriptor, part, directory, manifest) {
  const document = await decodeRegionalIndex(bytes, descriptor, NATURE_PARTITION_MAX_BYTES);
  requireData(document?.metadata?.feature_count === part.feature_count
    && document.metadata.reference_latitude === directory.reference_latitude
    && Array.isArray(document.features));
  let positions = 0;
  const bounds = [Infinity, Infinity, -Infinity, -Infinity];
  for (const feature of document.features) {
    const geometry = feature.geometry;
    requireData(geometry && ["Polygon", "MultiPolygon"].includes(geometry.type) && Array.isArray(geometry.coordinates));
    const polygons = geometry.type === "Polygon" ? [geometry.coordinates] : geometry.coordinates;
    for (const polygon of polygons) {
      requireData(Array.isArray(polygon));
      for (const ring of polygon) {
        requireData(Array.isArray(ring));
        positions += ring.length;
        requireData(positions <= NATURE_PARTITION_MAX_POSITIONS, "regional_index_too_large");
        for (const point of ring) {
          requireData(Array.isArray(point) && point.length === 2 && point.every(Number.isFinite));
          bounds[0] = Math.min(bounds[0], point[0]); bounds[1] = Math.min(bounds[1], point[1]);
          bounds[2] = Math.max(bounds[2], point[0]); bounds[3] = Math.max(bounds[3], point[1]);
        }
      }
    }
  }
  requireData(positions === part.position_count && bounds.every((value, index) => value === part.bounds[index]));
  // This shared preparation validates source identity, sorted feature IDs,
  // classifications, rings, holes and polygon topology under the existing caps.
  const tree = prepareLocalNaturePartition(manifest, document);
  return { tree, featureIds: document.features.map(feature => feature.feature_id) };
}

export function createPartitionedRegionData(manifest, pois, directory, readPartition) {
  const base = createLocalRegionData(manifest, { pois, natureInfo: directory });
  let cached = null;
  async function visit(bounds, accumulator) {
    for (let index = 0; index < directory.partitions.length; index++) {
      const part = directory.partitions[index];
      if (!overlaps(bounds, part.bounds)) continue;
      const descriptor = manifest.components.nature.files[index + 1];
      if (cached?.path !== part.path) {
        cached = null;
        const prepared = await decodeNaturePartition(await readPartition(descriptor), descriptor, part, directory, manifest);
        cached = { path: part.path, tree: prepared.tree };
      }
      accumulator.add(cached.tree);
    }
    return accumulator.finish();
  }
  async function analyzeNature(candidate) {
    if (candidate.pack_id !== base.identity.routing_pack_id) return unavailableNature(candidate.distance_m, "nature_routing_pack_mismatch");
    let accumulator;
    try { accumulator = createNatureIntervalAccumulator(manifest, candidate, base.identity, directory.reference_latitude); }
    catch (error) {
      if (error instanceof RegionalDataError && error.code === "nature_degenerate_geometry") return unavailableNature(candidate.distance_m, error.code);
      throw error;
    }
    try { return await visit(queryBounds(candidate.geometry, directory.reference_latitude), accumulator); }
    catch (error) {
      if (!(error instanceof RegionalDataError)) throw error;
      return unavailableNature(candidate.distance_m, error.code, accumulator.operations());
    }
  }
  async function queryWoodlandPoints(query) {
    const accumulator = createWoodlandAccumulator(manifest, query, base.identity, directory.reference_latitude);
    try { return await visit(queryBounds(query.points.map(p => [p.lon, p.lat]), directory.reference_latitude), accumulator); }
    catch (error) {
      if (!(error instanceof RegionalDataError)) throw error;
      return freezeData({ available: false, woodland: query.points.map(() => null), identity: base.identity, operation_count: null });
    }
  }
  return Object.freeze({ ...base, analyzeNature, queryWoodlandPoints });
}

function queryBounds(points, reference) {
  const result = [Infinity, Infinity, -Infinity, -Infinity];
  for (const [lon, lat] of points) {
    result[0] = Math.min(result[0], lon); result[1] = Math.min(result[1], lat);
    result[2] = Math.max(result[2], lon); result[3] = Math.max(result[3], lat);
  }
  // The same local metric projection and 100 m near-water buffer as the kernel.
  const latitudePadding = 100.001 / (6_371_008.8 * Math.PI / 180);
  const longitudePadding = latitudePadding / Math.cos(reference * Math.PI / 180);
  return [result[0] - longitudePadding, result[1] - latitudePadding, result[2] + longitudePadding, result[3] + latitudePadding];
}
const overlaps = (a, b) => a[0] <= b[2] && a[2] >= b[0] && a[1] <= b[3] && a[3] >= b[1];
