// Shared PR39 distribution contract. Component payloads keep their own formats.
export class RegionalDataError extends Error {
  constructor(code) {
    super(code);
    this.name = "RegionalDataError";
    this.code = code;
  }
}

export const REGIONAL_MANIFEST_MAX_BYTES = 32 * 1024;
export const REGIONAL_INDEX_MAX_BYTES = 32 * 1024 * 1024;
export const REGIONAL_INDEX_MAX_EXPANDED_BYTES = 128 * 1024 * 1024;
const FILES = Object.freeze({
  map: [["map/manifest.json", "map-manifest-v1"], ["map/basemap.pmtiles", "pmtiles-v3-mvt"]],
  routing: [["routing/manifest.json", "routing-manifest-v2"], ["routing/valhalla_tiles.tar", "valhalla-3.6.3-tar"]],
  pois: [["pois/index.json.gz", "poi-index-v2-gzip-json"]],
  nature: [["nature/index.json.gz", "nature-index-v1-gzip-json"]],
});
const TOOLS = Object.freeze({
  pipeline_version: 1,
  protomaps_revision: "3ea8293a28131c3dc63f1bb20827bdb8a76df06f",
  protomaps_archive_sha256: "7b8e71f18627754af756923f6613a9008b5f1ff82377fff4e617157d053fc807",
  map_build_image: "maven:3.9.13-eclipse-temurin-21-alpine@sha256:194053d8f204a39710e564b49ba4d22188159fd29f073b8da1715aac61503132",
  valhalla_image: "ghcr.io/valhalla/valhalla:3.6.3",
  poi_index_schema: 2,
  poi_classifier: "1",
  nature_index_schema: 1,
});

export async function parseRegionalManifest(text) {
  requireData(typeof text === "string"
    && new TextEncoder().encode(text).length <= REGIONAL_MANIFEST_MAX_BYTES, "invalid_regional_manifest");
  let value;
  try { value = JSON.parse(text); } catch { throw new RegionalDataError("invalid_regional_manifest"); }
  requireFields(value, ["schema_version", "region_id", "display_name", "bounds", "source", "tools", "components", "build_id"]);
  requireData(value.schema_version === 1 && safeRegionalId(value.region_id)
    && boundedText(value.display_name, 120) && validBounds(value.bounds)
    && validSha256(value.build_id), "invalid_regional_manifest");
  requireFields(value.source, ["basename", "byte_size", "sha256", "header_bounds", "coverage_evidence", "source_url"]);
  const source = value.source;
  requireData(typeof source.basename === "string" && /^[a-zA-Z0-9][a-zA-Z0-9._-]*$/u.test(source.basename)
    && !source.basename.includes("..") && positiveInteger(source.byte_size)
    && validSha256(source.sha256) && validBounds(source.header_bounds, 90)
    && coversBounds(source.header_bounds, value.bounds)
    && source.coverage_evidence === "osm-header-bounds"
    && (source.source_url === null || boundedText(source.source_url, 2048)
      && /^https?:\/\/[^\s]+$/u.test(source.source_url)), "invalid_regional_source");
  requireFields(value.tools, [...Object.keys(TOOLS), "python_version", "osmium_version", "shapely_version"]);
  requireData(Object.entries(TOOLS).every(([key, expected]) => key === "poi_classifier"
    ? ["1", "2"].includes(value.tools[key]) : value.tools[key] === expected)
    && ["python_version", "osmium_version", "shapely_version"].every((key) => boundedText(value.tools[key], 80)),
  "unsupported_regional_toolchain");
  requireFields(value.components, Object.keys(FILES));
  const ids = new Set();
  for (const [kind, expected] of Object.entries(FILES)) {
    const component = value.components[kind];
    requireFields(component, ["component_id", "files"]);
    requireData(safeRegionalId(component.component_id) && !ids.has(component.component_id)
      && Array.isArray(component.files) && component.files.length === expected.length, "invalid_regional_component");
    ids.add(component.component_id);
    component.files.forEach((file, index) => {
      requireFields(file, ["path", "byte_size", "sha256", "format"]);
      const maximum = kind === "pois" || kind === "nature" ? REGIONAL_INDEX_MAX_BYTES : 2 ** 31;
      requireData(file.path === expected[index][0] && file.format === expected[index][1]
        && positiveInteger(file.byte_size) && file.byte_size <= maximum
        && validSha256(file.sha256), "invalid_regional_file");
    });
  }
  requireData(await regionalBuildIdentity(value) === value.build_id, "regional_build_identity_mismatch");
  return freezeData(value);
}

export async function regionalBuildIdentity(manifest) {
  const { build_id: ignoredBuild, ...content } = manifest;
  const { source_url: ignoredUrl, ...source } = content.source;
  return sha256Bytes(new TextEncoder().encode(canonicalJson({ ...content, source }) + "\n"));
}

// PR39's Python canonical JSON represents bound coordinates as doubles, including
// integral values (2.0). Preserve that representation instead of hashing JS JSON.
function canonicalJson(value, floats = false) {
  if (Array.isArray(value)) return `[${value.map((item) => canonicalJson(item, floats)).join(",")}]`;
  if (value !== null && typeof value === "object") {
    return `{${Object.keys(value).sort().map((key) => (
      `${JSON.stringify(key)}:${canonicalJson(value[key], key === "bounds" || key === "header_bounds")}`
    )).join(",")}}`;
  }
  if (floats && typeof value === "number") {
    if (Object.is(value, -0)) return "-0.0";
    if (Number.isInteger(value)) return `${value}.0`;
    if (Math.abs(value) < 0.0001) {
      return value.toExponential().replace(/e([+-])(\d)$/u, "e$10$2");
    }
  }
  return JSON.stringify(value);
}

export async function sha256Bytes(bytes) {
  const digest = await globalThis.crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest), (value) => value.toString(16).padStart(2, "0")).join("");
}

export async function verifyRegionalBytes(bytes, descriptor) {
  requireData(bytes.byteLength === descriptor.byte_size, "regional_size_mismatch");
  requireData(await sha256Bytes(bytes) === descriptor.sha256, "regional_checksum_mismatch");
}

export function validBounds(value, latitudeLimit = 85.0511287798066) {
  return Array.isArray(value) && value.length === 4 && value.every(Number.isFinite)
    && -180 <= value[0] && value[0] < value[2] && value[2] <= 180
    && -latitudeLimit <= value[1] && value[1] < value[3] && value[3] <= latitudeLimit;
}

export function coversBounds(outer, inner) {
  return outer[0] <= inner[0] && outer[1] <= inner[1] && outer[2] >= inner[2] && outer[3] >= inner[3];
}

export function containsPosition(bounds, point) {
  return point[0] >= bounds[0] && point[0] <= bounds[2] && point[1] >= bounds[1] && point[1] <= bounds[3];
}

export function safeRegionalId(value) {
  return typeof value === "string" && /^[a-z0-9][a-z0-9._-]{0,63}$/u.test(value) && !value.includes("..");
}

export function validSha256(value) { return typeof value === "string" && /^[0-9a-f]{64}$/u.test(value); }
export function positiveInteger(value) { return Number.isSafeInteger(value) && value > 0; }
export function boundedText(value, maximum) { return typeof value === "string" && value.length > 0 && value.length <= maximum; }
export function requireData(condition, code = "invalid_regional_index") { if (!condition) throw new RegionalDataError(code); }
export function requireFields(value, fields) {
  requireData(value !== null && typeof value === "object" && !Array.isArray(value)
    && Object.keys(value).length === fields.length && fields.every((key) => Object.hasOwn(value, key)));
}
export function freezeData(value) {
  if (value !== null && typeof value === "object" && !Object.isFrozen(value)) {
    Object.values(value).forEach(freezeData);
    Object.freeze(value);
  }
  return value;
}
